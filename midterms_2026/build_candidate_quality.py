"""Candidate quality for 2026 Senate and Governor nominees.

Reads each nominee's one-line description from the Wikipedia race page
("Mike Collins, U.S. representative from Georgia's 10th congressional
district (2023-present)") and assigns a tier:

  3  current/former U.S. senator or governor
  2  U.S. representative, statewide elected office (AG, lieutenant governor,
     secretary of state, treasurer, ...), or mayor
  1  state legislator or other local elected office
  0  no elected office

The race model uses the tier DIFFERENCE between the two nominees. Output
includes the matched description so every classification can be checked:
data/processed/candidate_quality_2026.csv
"""
from pathlib import Path
import re
import sys

import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "midterms_2026"))
sys.path.insert(0, str(ROOT / "midterms_2026" / "polls"))
from build_races import clean  # noqa: E402
from scrape_wikipedia_polls import fetch, last_name, race_pages  # noqa: E402

PROC = ROOT / "data" / "processed"

TIERS = [  # checked in order; first match wins
    (3, r"incumbent senator"),  # appointed sitting senator (SC's Darline Graham)
    (1, r"(president|speaker|minority leader|majority leader|president pro tem\w*) of the [\w\s]*(senate|house|assembly)|"
        r"deputy mayor|executive councilor|\bstate delegate|speaker pro tem\w*|"
        r"(house of representatives|assembly|state senate|house of delegates) (majority|minority) leader|"
        r"\bstate assembly\b|\bassembly ?(man|woman|member)\b|"
        r"\bstate (senator|representative|assemblym|legislat)|member of the [\w\s]*(house of (representatives|delegates)|senate|assembly|legislature)(?! of the united states)"),
    (3, r"\bu\.?s\.? senator|united states senator|\bgovernor\b(?! of the federal)"),
    (2, r"u\.?s\.? representative|member of the u\.?s\.? house|congress(man|woman)|lieutenant governor|attorney general|"
        r"secretary of state|state treasurer|\btreasurer\b|auditor|comptroller|controller|superintendent of public|"
        r"commissioner of (insurance|agriculture|labor)|insurance commissioner|agriculture commissioner|\bmayor\b|"
        r"public service commission|railroad commission"),
    (1, r"county (commissioner|executive|judge|supervisor|sheriff|clerk)|city council|councilmember|alderman|"
        r"school board|state board|district attorney|sheriff|\bjudge\b|justice of|"
        # local legislators and executives, described every which way on race pages
        r"county (legislator|legislature|council|board(?! of elections)|commission)|board of (commissioners|supervisors|aldermen|chosen freeholders)|"
        r"\bfreeholder|(town|borough|township|village) (council|board|supervisor|commissioner|trustee)|"
        r"\bcouncil(man|woman|member|or)\b|selectm[ae]n|city commissioner|school district (board|trustee)|"
        r"college board of (trustees|governors)"),
]


# Hand-coded where the page format differs (Alaska top-four, Nebraska's independent,
# California's top-two page) or where a description names only appointed posts.
OVERRIDES = {
    "Mary Peltola": 2, "Dan S. Sullivan": 3, "Dan J. Sullivan": 0, "Gerald Heikes": 0,
    "Dan Osborn": 0, "Jonathan Kreiss-Tomkins": 1, "Dave Bronson": 2, "Treg Taylor": 0,
    "Bernadette Wilson": 0, "Xavier Becerra": 2, "Steve Hilton": 0,
    "Robert B. Charles": 0,   # Assistant Secretary of State: appointed, not elected
    "Don Tracy": 0,           # party chair / appointed board
    "Helena Foulkes": 0,      # description mentions her uncle, a former senator
}


def classify(desc: str) -> int:
    # Running for an office is not holding it: drop "candidate/nominee for ..." phrases.
    d = re.sub(r"(candidate|nominee|runner-up|ran) for [^,;()]*", "", desc.lower())
    # A relative's office is not the candidate's ("daughter of former U.S. Senator Pete Domenici").
    d = re.sub(r"\b(son|daughter|wife|husband|widow|widower|brother|sister|father|mother|nephew|niece|"
               r"grandson|granddaughter|grandfather|grandmother|uncle|aunt|cousin|in-law) of [^,;()]*", "", d)
    d = re.sub(r"chief of staff to [^,;()]*|(aide|staffer|adviser|advisor) to [^,;()]*", "", d)
    # "lieutenant governor" must not count as governor; strip it before the tier-3 check.
    for tier, pat in TIERS:
        text = d.replace("lieutenant governor", "lt-gov") if tier == 3 else d
        if re.search(pat, text):
            return tier
    return 0


def nominee_descriptions(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for h in soup.find_all(["h3", "h4", "h5"]):
        if h.get_text(strip=True).startswith("Nominee"):
            ul = h.find_next("ul")
            if ul:
                for li in ul.find_all("li", recursive=False):
                    txt = clean(li.get_text(" ", strip=True))
                    out.append(re.split(r"Running mate", txt)[0])
    return out


def main() -> None:
    rows = []
    for office, f in [("SEN", "senate"), ("GOV", "governor")]:
        races = pd.read_csv(PROC / f"races_2026_{f}.csv")
        for _, r in races.iterrows():
            if r["race_type"] == "same_party":
                continue
            html = fetch(race_pages(office, r["state_po"], bool(r["special"]))[0])
            descs = nominee_descriptions(html) if html else []
            names = {"dem": str(r["dem_candidate"]).split("; "), "rep": str(r["rep_candidate"]).split("; ")}
            if r["race_type"] == "independent":
                names["dem"] = [r["race_note"]]
            for side, cands in names.items():
                for name in cands:
                    if name == "nan":
                        continue
                    ln = last_name(name)
                    hit = next((d for d in descs if ln and ln in d.lower()[:60]), "")
                    tier = OVERRIDES.get(name, classify(hit) if hit else None)
                    rows.append({"office": office, "state_po": r["state_po"], "special": r["special"],
                                 "side": side, "candidate": name, "tier": tier,
                                 "description": hit[:160]})
    df = pd.DataFrame(rows)
    df.to_csv(PROC / "candidate_quality_2026.csv", index=False)
    print(df["tier"].value_counts(dropna=False).to_dict(), "| unmatched:", df["tier"].isna().sum())


if __name__ == "__main__":
    main()
