"""Does the turnout layer actually help? An out-of-sample test on 2018 and 2022.

Question: given the STATEWIDE result of a midterm Senate/Governor race, can we
predict how it distributes across counties better with turnout betas than
with a uniform swing?

For each test midterm Y (2018, 2022), starting from each county's previous
presidential result (Y-2), predict county D and R votes three ways:

  margin_swing the conventional approach: county margin + the state's margin swing
  uniform      every county's D and R VOTE COUNTS change like its state's
               (log change = state log change)
  total_beta   party-blind turnout sensitivity:
               dlog(D_c) = dlog(D_state) + (beta_total_c - 1) * dlog(T_state), same for R
  party_beta   party-specific sensitivity:
               dlog(P_c) = beta_P_c * dlog(P_state)  (then rescaled so the state total matches)

Every variant is rescaled so county votes add up to the actual state totals --
we are only testing the DISTRIBUTION across counties, which is exactly the
turnout layer's job. Betas are estimated with the test year (and the
following transition) excluded, so nothing leaks from the answer.

Score: vote-weighted RMSE of county two-party margins, and the same for the
margin SWING (county swing vs its state's swing), by method.
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import turnout_sensitivity as ts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed" / "turnout_layer_test.csv"


def predict_year(panel: pd.DataFrame, y: int) -> pd.DataFrame:
    sens = ts.compute(panel, exclude_years=(y,), min_transitions=3)
    base = panel[panel["year"] == y - 2][["county_fips", "state_po", "dem", "rep", "total"]]
    act = panel[panel["year"] == y][["county_fips", "dem", "rep", "total"]]
    d = base.merge(act, on="county_fips", suffixes=("_0", "_1")).merge(sens, on=["county_fips", "state_po"])
    d = d.dropna(subset=["dem_beta", "rep_beta", "total_beta", "dem_1", "rep_1"])
    st = d.groupby("state_po")[["dem_0", "rep_0", "total_0", "dem_1", "rep_1", "total_1"]].transform("sum")
    dlog = {p: np.log(st[f"{p}_1"] / st[f"{p}_0"]) for p in ("dem", "rep", "total")}

    preds = {
        "uniform": {p: d[f"{p}_0"] * np.exp(dlog[p]) for p in ("dem", "rep")},
        "total_beta": {p: d[f"{p}_0"] * np.exp(dlog[p] + (d["total_beta"] - 1) * dlog["total"]) for p in ("dem", "rep")},
        "party_beta": {p: d[f"{p}_0"] * np.exp(d[f"{p}_beta"] * dlog[p]) for p in ("dem", "rep")},
    }
    two = lambda D, R: 100 * (D - R) / (D + R)
    d["m0"], d["m1"] = two(d["dem_0"], d["rep_0"]), two(d["dem_1"], d["rep_1"])
    st_m1 = two(st["dem_1"], st["rep_1"])
    st_m0 = two(st["dem_0"], st["rep_0"])
    d["actual_rel_swing"] = (d["m1"] - d["m0"]) - (st_m1 - st_m0)
    # The conventional approach: every county's MARGIN moves by the state's margin swing.
    d["pred_margin_swing"] = d["m0"] + (st_m1 - st_m0)
    for name, pr in preds.items():
        D, R = pr["dem"], pr["rep"]
        # Rescale so each state's predicted D and R totals equal the actual ones.
        D = D * d.groupby("state_po")["dem_1"].transform("sum") / D.groupby(d["state_po"]).transform("sum")
        R = R * d.groupby("state_po")["rep_1"].transform("sum") / R.groupby(d["state_po"]).transform("sum")
        d[f"pred_{name}"] = two(D, R)
    d["year"] = y
    return d


def main() -> None:
    panel = ts.county_panel()
    rows, parts = [], []
    for y in (2018, 2022):
        d = predict_year(panel, y)
        parts.append(d)
        ok = d["m1"].notna()  # a county with zero D and R votes has no margin
        w = d.loc[ok, "total_1"]
        for name in ("margin_swing", "uniform", "total_beta", "party_beta"):
            err = (d[f"pred_{name}"] - d["m1"])[ok]
            rows.append({"year": y, "method": name, "counties": len(d),
                         "rmse_margin": np.sqrt(np.average(err ** 2, weights=w)),
                         "mean_abs_err": np.average(err.abs(), weights=w)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT, index=False)
    pd.set_option("display.width", 200)
    print(res.round(2).to_string(index=False))
    piv = res.pivot(index="year", columns="method", values="rmse_margin")
    for m in ("uniform", "total_beta", "party_beta"):
        print(f"{m}: RMSE change vs conventional margin swing: " + ", ".join(
            f"{y}: {100 * (piv.loc[y, m] / piv.loc[y, 'margin_swing'] - 1):+.1f}%" for y in piv.index))


if __name__ == "__main__":
    main()
