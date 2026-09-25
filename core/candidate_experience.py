"""Candidate experience (prior elected office) for every D and R nominee, 2018-2026.

    .venv/Scripts/python.exe core/candidate_experience.py

The 2026 forecast already gives Senate and Governor nominees an experience tier
(midterms_2026/build_candidate_quality.py) but its weight, 1 point per tier, was a guess:
we had no coded candidates for past years to estimate it from. This script codes them.

  3  current/former U.S. senator or governor
  2  U.S. representative, statewide elected office, or mayor
  1  state legislator or other local elected office
  0  no elected office

Sources: each race's Wikipedia page (the same pages and tier rules as the 2026 coding).
Nominee names come from official results (House, Senate: MIT Election Lab) or the page's
infobox (Governor). Descriptions come from the page's candidate lists ("Kyrsten Sinema,
U.S. Representative for AZ-9 ..."), matched by name; House pages are read district by
district. Incumbents get their office's tier directly (House 2, Senate/Governor 3).
Pages describe candidates as of that election, so no later office leaks in.

Writes data/processed/candidate_experience.csv (one row per nominee, with the matched
description so each tier can be checked).
"""
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
for sub in ("core", "midterms_2026", "midterms_2026/polls"):
    sys.path.insert(0, str(ROOT / sub))
from build_candidate_quality import classify, OVERRIDES  # noqa: E402
from scrape_wikipedia_polls import fetch, PO_STATE  # noqa: E402
from build_races import clean  # noqa: E402
import fec_money  # noqa: E402  (nominee lists and name handling)

PROC = ROOT / "data" / "processed"
YEARS = [2018, 2020, 2022, 2024, 2026]
OFFICE_TIER = {"HOUSE": 2, "SEN": 3, "GOV": 3}
NOT_CONTENT = {"reflist", "toc", "vector-toc", "navbox", "references", "mw-references-wrap", "infobox"}
SKIP_HEADINGS = re.compile(r"endorse|declined|withdr|potential|publicly expressed|failed to|removed|disqualified", re.I)


def page_title(year: int, office: str, st: str, special: bool = False) -> str:
    s = PO_STATE[st].replace(" ", "_")
    if office == "SEN":
        return f"{year}_United_States_Senate_{'special_' if special else ''}election_in_{s}"
    if office == "GOV":
        return f"{year}_{s}_gubernatorial_election"
    return f"{year}_United_States_House_of_Representatives_elections_in_{s}"


def district_of(text: str):
    if re.search(r"at[- ]large", text, re.I):
        return 0
    m = re.search(r"District (\d+)|(\d+)(?:st|nd|rd|th) (?:congressional )?district", text, re.I)
    return int(m.group(1) or m.group(2)) if m else None


def candidate_lines(html: str, by_district: bool) -> list[tuple]:
    """(district or None, description) for every candidate bullet, skipping declined/withdrawn lists."""
    soup = BeautifulSoup(html, "lxml")
    out, district, skip = [], None, False
    for el in soup.find_all(["h2", "h3", "h4", "h5", "li"]):
        if el.name in ("h2", "h3", "h4", "h5"):
            t = el.get_text(" ", strip=True)
            if el.name == "h2" and by_district:
                d = district_of(t)
                district = d if d is not None else (None if not re.search(r"district", t, re.I) else district)
            skip = bool(SKIP_HEADINGS.search(t)) if el.name in ("h3", "h4", "h5") else False
            continue
        if skip or el.find_parent(["table", "nav"]) or el.find_parent(lambda t: bool(set(t.get("class") or []) & NOT_CONTENT)):
            continue
        txt = clean(el.get_text(" ", strip=True))
        if "," in txt[:80]:
            out.append((district, re.split(r"Running mate", txt)[0]))
    return out


def find_description(name: str, lines: list[tuple], district=None) -> str:
    ks = fec_money.keys_plain(name)
    pool = [d for dist, d in lines if district is None or dist == district]
    hits = [d for d in pool if fec_money.keys_plain(d.split(",")[0]) & ks]
    if not hits:  # nickname (Bob vs. Robert): surname alone, if only one person has it
        sur = {k.split()[0] for k in ks}
        hits = [d for d in pool if {k.split()[0] for k in fec_money.keys_plain(d.split(",")[0])} & sur]
        if len({h.split(",")[0] for h in hits}) != 1:
            hits = []
    return max(hits, key=len) if hits else ""


def infobox_nominees(html: str) -> dict:
    """{'D': name, 'R': name} from the election infobox's Nominee / Party rows."""
    soup = BeautifulSoup(html, "lxml")
    box = soup.find("table", class_=re.compile("infobox"))
    if box is None:
        return {}
    rows = {tr.find("th").get_text(" ", strip=True): tr.find_all("td") for tr in box.find_all("tr") if tr.find("th")}
    noms, parties = rows.get("Nominee", []), rows.get("Party", [])
    out = {}
    for n, p in zip(noms, parties):
        pt = p.get_text(" ", strip=True)
        side = "D" if re.search(r"Democratic|DFL", pt) else "R" if "Republican" in pt else None
        if side and side not in out:
            out[side] = clean(n.get_text(" ", strip=True))
    return out


def nominees(year: int) -> pd.DataFrame:
    """House + Senate from results (or the 2026 race files); Governor from infoboxes."""
    nom = fec_money.nominees(year)
    nom = nom[nom["name"].notna() & (nom["name"].astype(str).str.len() > 0) & nom["state_po"].isin(PO_STATE)]
    rows = []
    if year == 2026:
        g = pd.read_csv(PROC / "races_2026_governor.csv")
        for _, r in g.iterrows():
            for side, col in (("D", "dem_candidate"), ("R", "rep_candidate")):
                if isinstance(r[col], str):
                    rows.append({"office": "GOV", "state_po": r["state_po"], "district": 0, "special": False,
                                 "side": side, "name": r[col].split("; ")[0]})
    else:
        cal = pd.read_csv(PROC / "statewide_calibration.csv")
        for st in cal.loc[(cal["office"] == "GOV") & (cal["year"] == year), "state_po"]:
            html = fetch(page_title(year, "GOV", st))
            for side, name in (infobox_nominees(html) if html else {}).items():
                rows.append({"office": "GOV", "state_po": st, "district": 0, "special": False, "side": side, "name": name})
    return pd.concat([nom, pd.DataFrame(rows)], ignore_index=True)


def incumbents(year: int) -> pd.DataFrame:
    """Which nominees are incumbents: from the backtest race files (past) or the 2026 race files."""
    if year == 2026:
        parts = []
        for office, f in (("HOUSE", "house"), ("SEN", "senate"), ("GOV", "governor")):
            r = pd.read_csv(PROC / f"races_2026_{f}.csv").assign(office=office)
            r["district"] = r["district"] if "district" in r else 0
            r["special"] = r["special"] if "special" in r else False
            r = r[r["incumbent_running"].astype(bool)]
            parts.append(r.assign(side=r["incumbent_party"])[["office", "state_po", "district", "special", "side"]])
        return pd.concat(parts)
    bt = pd.read_csv(ROOT / "midterms_2026" / "outputs" / "backtest_race_forecasts.csv")
    bt = bt[(bt["year"] == year) & (bt["inc_side"] != 0)]
    return bt.assign(side=np.where(bt["inc_side"] > 0, "D", "R"))[["office", "state_po", "district", "special", "side"]]


def senate_governor_2026() -> pd.DataFrame:
    """2026 Senate/Governor tiers come from the hand-checked 2026 coding (build_candidate_quality.py,
    same rules, plus overrides for Alaska's top-four ballot and a few odd descriptions)."""
    q = pd.read_csv(PROC / "candidate_quality_2026.csv")
    inc = pd.concat([pd.read_csv(PROC / f"races_2026_{f}.csv").assign(office=o) for o, f in (("SEN", "senate"), ("GOV", "governor"))])
    inc["special"] = inc["special"].fillna(False).astype(bool) if "special" in inc else False
    inc = inc[inc["incumbent_running"].astype(bool)][["office", "state_po", "special", "incumbent"]]
    q = q.merge(inc, on=["office", "state_po", "special"], how="left")
    q["incumbent"] = [isinstance(i, str) and bool(fec_money.keys_plain(c) & fec_money.keys_plain(i))
                      for c, i in zip(q["candidate"], q["incumbent"])]
    return pd.DataFrame({"office": q["office"], "state_po": q["state_po"], "district": 0, "special": q["special"],
                         "side": q["side"].map({"dem": "D", "rep": "R"}), "name": q["candidate"],
                         "incumbent": q["incumbent"], "year": 2026, "tier": q["tier"], "description": q["description"]})


def build(year: int) -> pd.DataFrame:
    nom = nominees(year)
    if year == 2026:
        nom = nom[nom["office"] == "HOUSE"]
    inc = incumbents(year).assign(incumbent=True)
    inc["district"] = inc["district"].fillna(0).astype(int)
    nom = nom.merge(inc.drop_duplicates(), on=["office", "state_po", "district", "special", "side"], how="left")
    nom["incumbent"] = nom["incumbent"].fillna(False).astype(bool)
    pages = {}
    out = []
    for _, r in nom.iterrows():
        title = page_title(year, r["office"], r["state_po"], bool(r["special"]))
        if title not in pages:
            html = fetch(title)
            pages[title] = candidate_lines(html, r["office"] == "HOUSE") if html else []
        desc = find_description(str(r["name"]), pages[title], int(r["district"]) if r["office"] == "HOUSE" else None)
        if r["incumbent"]:
            tier = OFFICE_TIER[r["office"]]
        elif year == 2026 and r["name"] in OVERRIDES:
            tier = OVERRIDES[r["name"]]
        else:
            tier = classify(desc) if desc else np.nan
        out.append({**r.to_dict(), "year": year, "tier": tier, "description": desc[:200]})
    out = pd.DataFrame(out)
    return pd.concat([out, senate_governor_2026()], ignore_index=True) if year == 2026 else out


def update_current() -> None:
    """Daily run: recode 2026 nominees (after build_candidate_quality.py), keep past years."""
    path = PROC / "candidate_experience.csv"
    cur = build(2026)
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=cur.columns)
    pd.concat([old[old["year"] != 2026], cur], ignore_index=True).to_csv(path, index=False)
    print(f"2026: {len(cur)} nominees, tier found for {cur['tier'].notna().mean():.0%}")


def main() -> None:
    frames = []
    for y in YEARS:
        df = build(y)
        found = df["tier"].notna()
        print(f"{y}: {len(df)} nominees, tier found for {found.mean():.0%} "
              f"({df.groupby('office')['tier'].apply(lambda s: f'{s.notna().mean():.0%}').to_dict()}); "
              f"tiers {df['tier'].value_counts().sort_index().to_dict()}", flush=True)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(PROC / "candidate_experience.csv", index=False)
    print("wrote", PROC / "candidate_experience.csv")


if __name__ == "__main__":
    main()
