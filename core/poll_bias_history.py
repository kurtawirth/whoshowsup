"""How biased and how noisy are partisan (internal/sponsored) polls, historically?

Data: FiveThirtyEight's raw_polls.csv -- every poll used in their pollster
ratings, 1998-2022, matched to the actual result, with a `partisan` flag
(DEM/REP = released by or for that party's side).

For each general-election poll of a Democrat vs a Republican:
    error = poll margin (D-R) - actual margin (D-R)

Comparing a partisan poll to the nonpartisan polls of the SAME race (a race
fixed effect) removes whatever made that race's polls miss overall, leaving
the partisan effect itself:

    error[p] = race_effect[race] + b_D * is_dem_poll + b_R * is_rep_poll + noise

  b_D > 0  Democratic-sponsored polls overstate Democrats by b_D points
  b_R < 0  Republican-sponsored polls overstate Republicans by |b_R| points

We also compare the spread of the residual noise, which sets how much less
weight a partisan poll should get than a nonpartisan one.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed" / "poll_bias_history.csv"
MAX_DAYS = 90  # polls taken within 90 days of the election (the forecast window we care about)


def load() -> pd.DataFrame:
    d = pd.read_csv(ROOT / "data" / "raw" / "fte" / "raw_polls.csv", low_memory=False)
    d = d[d["type_simple"].isin(["Sen-G", "Gov-G", "House-G"])]
    d = d[(d["cand1_party"].isin(["DEM", "REP"])) & (d["cand2_party"].isin(["DEM", "REP"]))
          & (d["cand1_party"] != d["cand2_party"])]
    sign = np.where(d["cand1_party"] == "DEM", 1, -1)  # express everything as D minus R
    d = d.assign(poll_margin=sign * d["margin_poll"], actual_margin=sign * d["margin_actual"])
    d["error"] = d["poll_margin"] - d["actual_margin"]
    d["side"] = d["partisan"].map({"DEM": "D", "REP": "R"}).fillna("none")
    d = d[d["partisan"].isna() | d["partisan"].isin(["DEM", "REP"])]
    return d[d["time_to_election"] <= MAX_DAYS]


def fit(d: pd.DataFrame) -> dict:
    # Only races that have at least one nonpartisan poll to compare against.
    has_np = d.groupby("race")["side"].transform(lambda s: (s == "none").any())
    d = d[has_np]
    m = smf.ols("error ~ C(race) + C(side, Treatment('none'))", data=d).fit(cov_type="cluster",
                                                                            cov_kwds={"groups": d["race"]})
    resid_sd = d.assign(r=m.resid).groupby("side")["r"].std()
    get = lambda k: next(v for n, v in m.params.items() if n.endswith(f"[T.{k}]"))
    se = lambda k: next(v for n, v in m.bse.items() if n.endswith(f"[T.{k}]"))
    return {"n_polls": len(d), "n_dem_polls": (d["side"] == "D").sum(), "n_rep_polls": (d["side"] == "R").sum(),
            "bias_dem_polls": get("D"), "se_dem": se("D"), "bias_rep_polls": get("R"), "se_rep": se("R"),
            "noise_sd_nonpartisan": resid_sd.get("none"), "noise_sd_dem": resid_sd.get("D"),
            "noise_sd_rep": resid_sd.get("R")}


def main() -> None:
    d = load()
    rows = [{"period": "all 1998-2022", **fit(d)}]
    for label, yrs in [("1998-2010", range(1998, 2011)), ("2012-2016", range(2012, 2017)),
                       ("2018-2022", range(2018, 2023))]:
        rows.append({"period": label, **fit(d[d["cycle"].isin(yrs)])})
    for office in ["Sen-G", "Gov-G", "House-G"]:
        rows.append({"period": f"all, {office}", **fit(d[d["type_simple"] == office])})
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    pd.set_option("display.width", 220)
    print(out.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
