"""Senators' and governors' personal vote: does running ahead of the state last time carry over?

    .venv/Scripts/python.exe core/statewide_personal_vote.py

From data/processed/statewide_calibration.csv (Senate 1994-2024, MEDSL; governors 2006-2024, Wikipedia):
each race's residual = margin - (state presidential lean + that year's national House margin). For an
incumbent running again, turned toward the incumbent's party:

    edge = intercept + rho * previous edge + noise(sd)

where the previous edge is the incumbent's own last race for the same office (found by name; within 6
years for senators, 4 for governors). The race model uses this in place of a flat incumbency bonus
(race_model.PERSONAL). Writes data/processed/statewide_personal_pairs.csv and prints the fits by
office, by era and leaving each year out.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
WINDOW = {"SEN": 6, "GOV": 4}


def pairs() -> pd.DataFrame:
    cal = pd.read_csv(PROC / "statewide_calibration.csv")
    out = []
    for office, window in WINDOW.items():
        c = cal[cal.office == office]
        for r in c[c.incumbent_side.fillna(0) != 0].itertuples():
            k = r.dem_key if r.incumbent_side == 1 else r.rep_key
            prev = c[(c.state_po == r.state_po) & (c.year < r.year) & (c.year >= r.year - window)
                     & ((c.dem_key == k) | (c.rep_key == k))].sort_values("year")
            if prev.empty:
                continue
            p = prev.iloc[-1]
            won_as = 1 if p.winner_side == "D" else -1
            if won_as != r.incumbent_side:
                continue  # party switcher, or the incumbent's last race was a loss
            out.append({"office": office, "year": r.year, "state_po": r.state_po, "special": r.special,
                        "incumbent": k, "side": r.incumbent_side, "prev_year": p.year,
                        "edge": r.incumbent_side * r.resid, "prev_edge": r.incumbent_side * p.resid})
    return pd.DataFrame(out)


def fit(pr: pd.DataFrame, robust: bool = False) -> dict:
    """OLS; robust=True: Huber regression for the line (a few extreme incumbents -- Vermont's Phil Scott
    ran 50-86 points ahead of his state four times -- otherwise set the slope), OLS residual sd kept."""
    m = smf.ols("edge ~ prev_edge", data=pr).fit()
    line = smf.rlm("edge ~ prev_edge", data=pr).fit().params if robust else m.params
    return {"intercept": float(line["Intercept"]), "rho": float(line["prev_edge"]),
            "sd": float(np.sqrt(m.scale)), "n": int(m.nobs), "se_rho": float(m.bse["prev_edge"])}


def main() -> None:
    pr = pairs()
    pr.to_csv(PROC / "statewide_personal_pairs.csv", index=False)
    pd.set_option("display.width", 200)
    for office in WINDOW:
        x = pr[pr.office == office]
        f = fit(x)
        print(f"\n{office}: all years (n={f['n']}, {x.year.min()}-{x.year.max()}): edge = {f['intercept']:.2f} + "
              f"{f['rho']:.2f} x previous (se {f['se_rho']:.2f}); sd {f['sd']:.2f}")
        for lo, hi in [(1996, 2004), (2006, 2010), (2012, 2016), (2018, 2024), (2012, 2024), (2016, 2024)]:
            y = x[x.year.between(lo, hi)]
            if len(y) >= 10:
                g = fit(y)
                print(f"   {lo}-{hi}: n={g['n']:3d}  intercept {g['intercept']:5.2f}  rho {g['rho']:.2f}  sd {g['sd']:.2f}")
        for yr in sorted(x.year.unique()):
            if yr >= 2010:
                g = fit(x[x.year != yr])
                print(f"   without {yr}: intercept {g['intercept']:.2f}, rho {g['rho']:.2f}, sd {g['sd']:.2f}")


if __name__ == "__main__":
    main()
