"""How early voters lean: party identification by how people voted, 2008-2022.

    .venv/Scripts/python.exe core/early_vote_history.py

Source: MIT Election Data + Science Lab's Survey of the Performance of American Elections (Harvard
Dataverse, CC0; data/raw/spae/), about 10,000 voters per election, 200 per state. Each voter says how
they voted (in person on Election Day, in person before it, or by mail) and their party. Weighted.
The 2018 survey isn't on the Dataverse and 2024's download requires a guestbook form, so both are absent.

Findings (2026-09-28): early voters leaned Democratic in every year (party ID, D minus R): early in
person D+8 to D+19 before 2020, mail D+1 to D+13, Election Day about even. In 2020 mail voting became
D+26 (and stayed there in 2022) while Election Day voters turned Republican (R+21 in 2020, R+9 in 2022).

Output: data/processed/early_vote_by_mode.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "spae"
OUT = ROOT / "data" / "processed" / "early_vote_by_mode.csv"
# year: (voted question, mode question, weight); "voted" = 6 ("I definitely voted"); mode 1/2/3
SPEC = {2008: ("q1", "q5", "weight"), 2012: ("q1", "q4", "weight"), 2014: ("Q1", "Q4", "weight"),
        2016: ("Q1", "Q4", "weight"), 2020: ("Q1", "Q4", "weight"), 2022: ("Q1", "Q4", "weight_final")}
MODES = {1: "Election Day", 2: "Early in person", 3: "Mail"}


def main() -> pd.DataFrame:
    rows = []
    for year, (voted, mode, weight) in SPEC.items():
        d = pd.read_csv(RAW / f"spae_{year}.tab", sep="\t", low_memory=False)
        d = d[(d[voted] == 6) & d[mode].isin(MODES)]
        total = d[weight].astype(float).sum()
        for m, g in d.groupby(mode):
            w = g[weight].astype(float)
            rows.append({"year": year, "mode": MODES[m], "respondents": len(g), "share_of_voters": w.sum() / total,
                         "dem": float(np.average(g["pid3"] == 1, weights=w)),
                         "rep": float(np.average(g["pid3"] == 2, weights=w))})
    out = pd.DataFrame(rows)
    out["gap"] = 100 * (out["dem"] - out["rep"])
    out.to_csv(OUT, index=False)
    print(out.round(3).to_string(index=False))
    return out


if __name__ == "__main__":
    main()
