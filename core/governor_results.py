"""Governor results 2006-2024 from Wikipedia's yearly summary pages ("YYYY United States gubernatorial
elections", the table listing each state's incumbent, result and candidates with vote shares).

    .venv/Scripts/python.exe core/governor_results.py

Gives the backtest each governor's previous race (their personal vote) and the governor races of every
test year, 2010-2024. 2018 and 2022 are checked against our county data (median gap 0.04 points).

Output: data/processed/governor_results.csv, one row per regular election: year, state_po, the leading
Democrat and Republican with their shares, margin (D-R, two-party), incumbent, whether the incumbent
ran, incumbent_side (+1 D, -1 R, 0 open or other).
"""
from pathlib import Path
import io
import re
import sys

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "wikipedia_governors"
PROC = ROOT / "data" / "processed"
sys.path.insert(0, str(ROOT / "midterms_2026"))
from build_races import STATE_PO  # noqa: E402

HEADERS = {"User-Agent": "politics-forecast-research/0.1 (personal project; kurtawirth)"}
YEARS = (2006, 2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024)
CAND = re.compile(r"([^▌]+?)\s*\(([^)]+)\)\s*([\d.]+)%")


def page(year: int) -> str:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"{year}_United_States_gubernatorial_elections.html"
    if not path.exists():
        r = requests.get(f"https://en.wikipedia.org/wiki/{year}_United_States_gubernatorial_elections",
                         headers=HEADERS, timeout=60)
        r.raise_for_status()
        path.write_text(r.text, encoding="utf-8")
    return path.read_text(encoding="utf-8")


def results(year: int) -> pd.DataFrame:
    alias = {"States": "State", "Governor": "Incumbent", "Status": "Result"}
    tables = [t.rename(columns=lambda c: alias.get(re.sub(r"\[.*?\]", "", str(c)).strip(),
                                                   re.sub(r"\[.*?\]", "", str(c)).strip()))
              for t in pd.read_html(io.StringIO(page(year)))]
    t = next(t for t in tables if {"State", "Incumbent", "Result", "Candidates"} <= {str(c) for c in t.columns})
    rows = []
    for _, r in t.iterrows():
        state = re.sub(r"\[.*?\]|\(.*?\)", "", str(r["State"])).strip()
        if state not in STATE_PO:
            continue
        cands = [(re.sub(r"\[.*?\]", "", n).strip(), p, float(s)) for n, p, s in CAND.findall(str(r["Candidates"]))]
        # the Democratic slot: Minnesota's DFL; Vermont's Progressive/Democratic fusion nominee (2020)
        dem = next((c for c in cands if c[1].startswith(("Democratic", "DFL")) or "Farmer" in c[1]), None) \
            or next((c for c in cands if c[1].startswith("Progressive")), None)
        rep = next((c for c in cands if c[1].startswith("Republican")), None)
        inc = re.sub(r"\[.*?\]", "", str(r["Incumbent"])).strip()
        party = str(r.get("Party", ""))
        # the incumbent ran if they are one of the two nominees (lost a primary = didn't run)
        surname = lambda n: re.sub(r"\b(Jr|Sr|II|III)\.?$", "", str(n)).strip().split()[-1].lower() if n else ""
        side = 1 if dem and surname(dem[0]) == surname(inc) else -1 if rep and surname(rep[0]) == surname(inc) else 0
        ran = side != 0
        rows.append({"year": year, "state_po": STATE_PO[state], "incumbent": inc, "incumbent_party": party,
                     "incumbent_ran": ran, "incumbent_side": side,
                     "dem": dem[0] if dem else None, "dem_pct": dem[2] if dem else None,
                     "rep": rep[0] if rep else None, "rep_pct": rep[2] if rep else None})
    d = pd.DataFrame(rows)
    d["margin"] = 100 * (d.dem_pct - d.rep_pct) / (d.dem_pct + d.rep_pct)
    return d


def main() -> None:
    d = pd.concat([results(y) for y in YEARS], ignore_index=True)
    d.to_csv(PROC / "governor_results.csv", index=False)
    print(d.groupby("year").agg(races=("state_po", "size"), with_both=("margin", "count"),
                                incumbents=("incumbent_ran", "sum")))
    # check against the county data where both exist
    c = pd.read_parquet(PROC / "county_results.parquet")
    g = c[c["office"] == "GOV"].groupby(["year", "state_po"])[["dem", "rep"]].sum().reset_index()
    g["county_margin"] = 100 * (g.dem - g.rep) / (g.dem + g.rep)
    j = d.merge(g[["year", "state_po", "county_margin"]], on=["year", "state_po"])
    j["diff"] = (j.margin - j.county_margin).abs()
    print(f"vs county data: {len(j)} races, median gap {j['diff'].median():.2f}, largest:")
    print(j.sort_values("diff").tail(5)[["year", "state_po", "margin", "county_margin"]].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
