"""2024 race polls for the backtest, from Wikipedia (538's archive, used for 2018-2022, stops at 2022).

    .venv/Scripts/python.exe core/polls_2024.py [--refresh]

Reads each 2024 Senate, governor and House race's Wikipedia page(s) with the same table reader the live
forecast uses (midterms_2026/polls/scrape_wikipedia_polls.py): the Senate and governor race articles,
each state's House page (tables under the district's heading) and the districts' own articles. Pages
are today's versions, so polls are filtered by their end date in the backtest (as with 538's archive).

Nominees come from the official results (MEDSL for Senate and House, core/governor_results.py for
governors). One version per poll: likely voters over registered voters over all adults.

Output: data/processed/polls_2024_backtest.csv
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "midterms_2026" / "polls"))
sys.path.insert(0, str(ROOT / "midterms_2026"))
import scrape_wikipedia_polls as swp  # noqa: E402

RAW = ROOT / "data" / "raw" / "medsl"
PROC = ROOT / "data" / "processed"
swp.RAW = ROOT / "data" / "raw" / "wikipedia_2024"
YEAR = 2024


def nominees() -> pd.DataFrame:
    """The leading Democrat and Republican in each 2024 Senate, House and governor race."""
    rows = []
    s = pd.read_csv(RAW / "senate_1976_2024.csv", encoding="latin-1")
    s = s[(s.year == YEAR) & (s.stage.str.lower() == "gen")]
    s["special"] = s["special"].astype(str).str.upper().eq("TRUE")
    for (st, sp), g in s.groupby(["state_po", "special"]):
        top = lambda p: g[g.party_simplified == p].groupby("candidate").candidatevotes.sum().sort_values().index[-1] \
            if (g.party_simplified == p).any() else None
        rows.append({"office": "SEN", "state_po": st, "district": 0, "special": sp, "dem": top("DEMOCRAT"), "rep": top("REPUBLICAN")})
    h = pd.read_csv(RAW / "house_1976_2024.tab", sep=None, engine="python", encoding="latin-1")
    h = h[(h.year == YEAR) & (h.stage.str.upper() == "GEN") & ~h.special.astype(str).str.upper().eq("TRUE")]
    h["party"] = h.party.astype(str).str.upper()
    for (st, dist), g in h.groupby(["state_po", "district"]):
        top = lambda cond: g[cond].groupby("candidate").candidatevotes.sum().sort_values().index[-1] if cond.any() else None
        rows.append({"office": "HOUSE", "state_po": st, "district": int(dist), "special": False,
                     "dem": top(g.party.str.contains("DEMOCRAT")), "rep": top(g.party.eq("REPUBLICAN"))})
    gv = pd.read_csv(PROC / "governor_results.csv")
    for r in gv[gv.year == YEAR].itertuples():
        rows.append({"office": "GOV", "state_po": r.state_po, "district": 0, "special": False, "dem": r.dem, "rep": r.rep})
    d = pd.DataFrame(rows)
    for c in ("dem", "rep"):  # official results are in capitals ("ROBERT P CASEY JR"); the name matcher expects "Casey Jr"
        d[c] = d[c].map(lambda n: n.title() if isinstance(n, str) and n.isupper() else n)
    return d[d.dem.notna() & d.rep.notna() & d.state_po.isin(swp.PO_STATE)].reset_index(drop=True)


def pages(r) -> list[str]:
    st = swp.PO_STATE[r.state_po].replace(" ", "_")
    if r.office == "SEN":
        return [f"{YEAR}_United_States_Senate_{'special_' if r.special else ''}election_in_{st}"]
    if r.office == "GOV":
        return [f"{YEAR}_{st}_gubernatorial_election"]
    if r.district == 0:
        return [f"{YEAR}_United_States_House_of_Representatives_election_in_{st}"]
    return [f"{YEAR}_United_States_House_of_Representatives_elections_in_{st}"]


def district_title(state_po: str, district: int) -> str:
    st = swp.PO_STATE[state_po].replace(" ", "_")
    return f"{YEAR}_{st}'s_{'at-large' if district == 0 else swp.ORD(district)}_congressional_district_election"


def district_articles(races: pd.DataFrame, refresh: bool) -> set[str]:
    path = swp.RAW / "district_articles.txt"
    if not refresh and path.exists():
        return set(path.read_text(encoding="utf-8").split())
    titles = [district_title(r.state_po, r.district) for r in races[races.office == "HOUSE"].itertuples()]
    found = set()
    for i in range(0, len(titles), 50):
        r = requests.get("https://en.wikipedia.org/w/api.php", headers=swp.HEADERS, timeout=60, params={
            "action": "query", "format": "json", "prop": "info", "titles": "|".join(t.replace("_", " ") for t in titles[i:i + 50])})
        r.raise_for_status()
        found |= {p["title"].replace(" ", "_") for p in r.json()["query"]["pages"].values()
                  if "missing" not in p and "redirect" not in p}
    path.write_text("\n".join(sorted(found)), encoding="utf-8")
    return found


def main(refresh: bool = False) -> None:
    swp.RAW.mkdir(parents=True, exist_ok=True)
    races = nominees()
    arts = district_articles(races, refresh)
    state_pages, out = {}, []
    for r in races.itertuples():
        titles = pages(r)
        if r.office == "HOUSE" and district_title(r.state_po, r.district) in arts:
            titles.append(district_title(r.state_po, r.district))
        for t in titles:
            if r.office == "HOUSE" and "_elections_in_" in t:  # multi-district state page: this district's tables
                if t not in state_pages:
                    html = swp.fetch(t, refresh)
                    state_pages[t] = (list(swp.poll_tables(html)) if html else [], swp.page_refs(html) if html else {})
                tabs, refs = state_pages[t]
                tabs = [(hd, tb) for hd, tb in tabs if swp.district_from_heading(hd) == r.district]
            else:
                html = swp.fetch(t, refresh)
                tabs, refs = (list(swp.poll_tables(html)), swp.page_refs(html)) if html else ([], {})
            for hd, tb in tabs:
                if "primar" in hd.lower():
                    continue
                for row in swp.parse_table(tb, r.dem, r.rep, refs):
                    out.append({"office": r.office, "state_po": r.state_po, "district": r.district, "special": r.special,
                                "dem_name": r.dem, "rep_name": r.rep, **row, "page": t})
    p = pd.DataFrame(out)
    # one version per poll (the same poll can appear on two pages, or as LV and RV rows)
    p["pop_rank"] = p.population.map({"LV": 0, "RV": 1, "V": 1, "A": 2}).fillna(3)
    p = p.sort_values("pop_rank").drop_duplicates(["office", "state_po", "district", "special", "pollster", "end_date"])
    p = p.drop(columns="pop_rank").sort_values(["office", "state_po", "district", "end_date"])
    p.to_csv(PROC / "polls_2024_backtest.csv", index=False)
    print(f"{len(races)} races; {len(p)} polls in {p.groupby(['office', 'state_po', 'district', 'special']).ngroups} races")
    print(p.groupby("office").agg(polls=("pollster", "size"), races=("state_po", lambda s: s.nunique())))
    by42 = p[pd.to_datetime(p.end_date) <= pd.Timestamp("2024-09-24")]
    print(f"ending by Sept 24 (42+ days out): {len(by42)} polls in {by42.groupby(['office', 'state_po', 'district']).ngroups} races")
    for t in swp.FAILED:
        print("  download failed:", t)


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
