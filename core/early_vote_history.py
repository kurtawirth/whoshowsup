"""How early voters vote: U.S. House vote and party by how people voted, 2008-2024.

    .venv/Scripts/python.exe core/early_vote_history.py

Source: the Cooperative Election Study's yearly Common Content (Harvard Dataverse, CC0), about 30,000-60,000
people per year. After the election each is asked whether and how they voted (in person on Election Day,
in person before it, or by mail) and whom they voted for for the U.S. House. Weighted.

The yearly files are large (60-560 MB each); only the columns used here are kept, in
data/processed/ces_vote_mode.csv (one row per voter), so the downloads in data/raw/ces_yearly/ can be
deleted. Rerunning from that extract needs no downloads.

Findings (2026-09-28), U.S. House vote margin (D minus R) by how people voted:
  mail voters were more Democratic than Election Day voters in all nine elections (2008 D+10 vs D+2,
  2010 R+4 vs R+10, 2014 R+1 vs R+9, 2018 D+20 vs D+8), and far more since 2020 (2020 D+38 vs R+33,
  2022 D+26 vs R+20, 2024 D+25 vs R+17). Early in-person voters vote much like Election Day voters
  (2024 R+15). The 2018 file stores answer labels instead of codes (_codes() handles it).

Output: data/processed/early_vote_by_mode.csv (one row per year and voting method)
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "ces_yearly"
PROC = ROOT / "data" / "processed"
EXTRACT = PROC / "ces_vote_mode.csv"
OUT = PROC / "early_vote_by_mode.csv"
MODES = {1: "Election Day", 2: "Early in person", 3: "Mail"}

# year: file, voted question (5 = "I definitely voted"), mode question, House vote, party ID, weight.
# 2008 and 2010 code the House vote 1 = Democrat, 2 = Republican; from 2012 it is the order of the
# candidates on the respondent's ballot, whose parties are in HouseCand{1,2,3}Party_post.
SPEC = {
    2008: ("ces_2008.tab", "CC403", "CC405", "CC412", "CC307", "V201"),
    2010: ("ces_2010.dta", "CC401", "CC403", "CC412", "V212a", "V101"),
    2012: ("ces_2012.tab", "CC401", "CC403", "CC412", "pid3", "V103"),
    2014: ("ces_2014.dta", "CC401", "CC403", "CC412", "pid3", "weight"),
    2016: ("ces_2016.tab", "CC16_401", "CC16_403", "CC16_412", "pid3", "commonweight_post"),
    2018: ("ces_2018.csv", "CC18_401", "CC18_403", "CC18_412", "pid3", "commonpostweight"),
    2020: ("ces_2020.csv", "CC20_401", "CC20_403", "CC20_412", "pid3", "commonpostweight"),
    2022: ("ces_2022.csv", "CC22_401", "CC22_403", "CC22_412", "pid3", "commonpostweight"),
    2024: ("ces_2024.csv", "CC24_401", "CC24_403", "CC24_412", "pid3", "commonpostweight"),
}
CAND_PARTY = [f"HouseCand{k}Party_post" for k in (1, 2, 3)]


def _read(path: Path, cols: list[str]) -> pd.DataFrame:
    if path.suffix == ".dta":
        return pd.read_stata(path, columns=cols, convert_categoricals=False)
    return pd.read_csv(path, sep="\t" if path.suffix == ".tab" else ",", usecols=cols, low_memory=False)


def _side(party) -> str:
    p = str(party).lower()
    return "D" if p.startswith("dem") else "R" if p.startswith("rep") else ""


def _codes(d: pd.DataFrame, voted: str, mode: str, house: str, pid: str) -> pd.DataFrame:
    """The 2018 file stores answer labels instead of codes: turn them back into the codes used above."""
    if pd.api.types.is_numeric_dtype(d[voted]):
        return d
    d = d.copy()
    d[voted] = np.where(d[voted].astype(str).str.startswith("I definitely voted"), 5, 0)
    m = d[mode].astype(str)
    d[mode] = np.select([m.str.startswith("In person on election day"), m.str.startswith("In person before"),
                         m.str.startswith("Voted by mail")], [1, 2, 3], 0)
    d[house] = pd.to_numeric(d[house].astype(str).str.extract(r"HouseCand(\d)Name")[0], errors="coerce")
    d[pid] = d[pid].astype(str).map({"Democrat": 1, "Republican": 2, "Independent": 3, "Other": 4, "Not sure": 5})
    return d


def extract() -> pd.DataFrame:
    parts = []
    for year, (f, voted, mode, house, pid, weight) in SPEC.items():
        cand = CAND_PARTY if year >= 2012 else []
        d = _codes(_read(RAW / f, [voted, mode, house, pid, weight] + cand), voted, mode, house, pid)
        d = d[pd.to_numeric(d[voted], errors="coerce") == 5]
        m = pd.to_numeric(d[mode], errors="coerce")
        h = pd.to_numeric(d[house], errors="coerce")
        if year >= 2012:
            party = np.select([h == k for k in (1, 2, 3)], [d[c].map(_side) for c in CAND_PARTY], "")
        else:
            party = np.where(h == 1, "D", np.where(h == 2, "R", ""))
        parts.append(pd.DataFrame({"year": year, "weight": pd.to_numeric(d[weight], errors="coerce"),
                                   "mode": m.map(MODES), "pid3": pd.to_numeric(d[pid], errors="coerce"),
                                   "house": party}))
    out = pd.concat(parts, ignore_index=True)
    out = out[out["mode"].notna() & (out["weight"] > 0)]
    out.to_csv(EXTRACT, index=False)
    return out


def main() -> pd.DataFrame:
    d = pd.read_csv(EXTRACT) if EXTRACT.exists() and not RAW.exists() else extract()
    d["house"] = d["house"].fillna("")
    rows = []
    for (year, mode), g in d.groupby(["year", "mode"]):
        two = g[g["house"].isin(["D", "R"])]
        rows.append({"year": year, "mode": mode, "respondents": len(g),
                     "share_of_voters": g["weight"].sum() / d.loc[d["year"] == year, "weight"].sum(),
                     "house_d": float(np.average(two["house"] == "D", weights=two["weight"])), "house_n": len(two),
                     "pid_gap": 100 * float(np.average(g["pid3"] == 1, weights=g["weight"])
                                            - np.average(g["pid3"] == 2, weights=g["weight"]))})
    out = pd.DataFrame(rows)
    out["gap"] = 100 * (2 * out["house_d"] - 1)  # House vote margin, D minus R (two-party)
    out.to_csv(OUT, index=False)
    print(out.round(3).to_string(index=False))
    return out


if __name__ == "__main__":
    main()
