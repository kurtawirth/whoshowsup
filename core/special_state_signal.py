"""State-level special elections: does a state's own special-election overperformance predict its races?

    .venv/Scripts/python.exe core/special_state_signal.py

The model reads special elections nationally (their average overperformance -> the national environment).
This asks whether each state's specials (mostly state-legislative) also tell us where that state lands
relative to the nation: the state's average overperformance minus the national average over the cycle
(Nov 15 two years before through Sept 22), shrunk toward zero by k specials' worth:

    x = (sum(overperformance) - n * national average) / (n + k)

Scored against the backtest model's House misses (Sept 22, each year's average miss removed), with the
slope fitted on the other years (leave-one-year-out). 2024 has no specials data for 2023-24.

Findings (2026-09-27): averaged by state, it helps in 2018 and 2022 but not 2020. In the competitive
races that decide seats (model margin within 15), it hurts 2018 (error 5.07 -> 5.11, wrong calls
16 -> 19) and 2020 (4.98 -> 5.07), and helps only 2022 (5.30 -> 5.08, 16 -> 14), for any k. Statewide
races (which have polls) get worse every year. Not in the model.

Writes data/processed/special_state_signal.csv.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
YEARS = (2018, 2020, 2022)


def state_signal(specials: pd.DataFrame, year: int, k: float) -> pd.Series:
    c = specials[(specials.date >= f"{year - 2}-11-15") & (specials.date <= f"{year}-09-22")]
    g = c.groupby("state_po").overperformance.agg(["sum", "size"])
    return (g["sum"] - g["size"] * c.overperformance.mean()) / (g["size"] + k)


def main() -> None:
    s = pd.read_csv(PROC / "special_elections.csv", parse_dates=["date"])
    r = pd.read_csv(ROOT / "midterms_2026" / "outputs" / "backtest_race_forecasts.csv")
    r["res"] = r.actual - r.margin_median
    rows = []
    for office, sub in [("HOUSE", r[r.office == "HOUSE"]), ("statewide", r[r.office != "HOUSE"])]:
        for k in (3, 8, 15):
            J = []
            for y in YEARS:
                d = sub[sub.year == y].copy()
                d["x"] = d.state_po.map(state_signal(s, y, k)).fillna(0.0)
                d["res"] -= d.res.mean()
                J.append(d)
            J = pd.concat(J)
            for y in YEARS:
                tr, te = J[J.year != y], J[J.year == y]
                b = float((tr.x * tr.res).sum() / (tr.x ** 2).sum())
                for label, t in [("all", te), ("competitive", te[te.margin_median.abs() < 15])]:
                    rows.append({"office": office, "k": k, "year": y, "races": label, "n": len(t), "slope": b,
                                 "rmse_before": float(np.sqrt((t.res ** 2).mean())),
                                 "rmse_after": float(np.sqrt(((t.res - b * t.x) ** 2).mean())),
                                 "wrong_before": int(((t.margin_median > 0) != (t.actual > 0)).sum()),
                                 "wrong_after": int(((t.margin_median + b * t.x > 0) != (t.actual > 0)).sum())})
    out = pd.DataFrame(rows)
    out.to_csv(PROC / "special_state_signal.csv", index=False)
    pd.set_option("display.width", 200)
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
