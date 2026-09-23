"""Collect 2026 general-election polls from Wikipedia race pages.

For every Senate and Governor race (and House races whose state page has
district polls), read each poll table and keep only polls that include BOTH
of the actual nominees -- hypothetical matchups with candidates who lost a
primary are dropped.

Output: data/processed/polls_2026_wikipedia.csv, one row per poll:
  office, state_po, district, special, pollster, pollster_party (D/R/'' --
  Wikipedia marks partisan pollsters "(R)"/"(D)"), sponsored (footnote marks a
  partisan client), start_date, end_date, sample_size, population (LV/RV/A),
  dem_pct, rep_pct, other_pct, undecided_pct, plus the source page/heading.

When one poll appears on several rows (e.g. with and without leaners), the
first row is kept.
"""
from pathlib import Path
import io
import re
import sys
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "midterms_2026"))
from build_races import STATE_PO, clean  # noqa: E402

RAW = ROOT / "data" / "raw" / "wikipedia"
PROC = ROOT / "data" / "processed"
HEADERS = {"User-Agent": "politics-forecast-research/0.1 (personal project; kurtawirth)"}
PO_STATE = {v: k for k, v in STATE_PO.items()}


def fetch(title: str, refresh: bool = False) -> str | None:
    path = RAW / f"{title}.html"
    if refresh or not path.exists():
        r = requests.get(f"https://en.wikipedia.org/wiki/{title}", headers=HEADERS)
        if r.status_code != 200:
            return None
        path.write_text(r.text, encoding="utf-8")
        time.sleep(0.3)  # be polite to Wikipedia
    return path.read_text(encoding="utf-8")


def poll_tables(html: str):
    """Yield (heading_path, DataFrame) for each poll table, in page order."""
    soup = BeautifulSoup(html, "lxml")
    heads = {"h2": "", "h3": "", "h4": ""}
    for el in soup.find_all(["h2", "h3", "h4", "table"]):
        if el.name in heads:
            heads[el.name] = el.get_text(" ", strip=True)
            for lower in [h for h in ("h2", "h3", "h4") if h > el.name]:
                heads[lower] = ""
            continue
        if "wikitable" not in (el.get("class") or []):
            continue
        text = el.get_text(" ", strip=True)[:300]
        if "Poll source" not in text:
            continue
        try:
            tb = pd.read_html(io.StringIO(str(el)))[0]
        except ValueError:
            continue
        if isinstance(tb.columns, pd.MultiIndex):
            tb.columns = [c[-1] for c in tb.columns]
        yield " > ".join(h for h in heads.values() if h), tb


def last_name(full: str) -> str:
    parts = [p for p in re.sub(r"\b(Jr|Sr|II|III)\.?$", "", full).split() if p]
    return parts[-1].lower() if parts else ""


def find_col(cols, name: str):
    ln = last_name(name)
    hits = [c for c in cols if ln and ln in str(c).lower()]
    return hits[0] if len(hits) == 1 else None


MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def parse_dates(s: str):
    s = clean(s).replace("—", "–")
    parts = [p.strip() for p in re.split(r"\s*[–-]\s*", s)]
    end = parts[-1]
    start = parts[0]
    ym = re.search(r"(\d{4})$", end)
    if not ym:
        return pd.NaT, pd.NaT
    year = ym.group(1)
    if not re.match(MONTHS, end):  # "June 13–14, 2026" -> end is "14, 2026"
        end = re.match(rf"({MONTHS})", start).group(1) + " " + end if re.match(MONTHS, start) else end
    if not re.search(r"\d{4}", start):
        start = f"{start}, {year}"
    return pd.to_datetime(start, errors="coerce"), pd.to_datetime(end, errors="coerce")


def pct(v) -> float:
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*%", clean(v))
    return float(m.group(1)) if m else float("nan")


def parse_table(tb: pd.DataFrame, dem: str, rep: str) -> list[dict]:
    cols = list(tb.columns)
    src = next((c for c in cols if str(c).startswith("Poll source")), None)
    dcol, rcol = find_col(cols, dem), find_col(cols, rep)
    if src is None or dcol is None or rcol is None or dcol == rcol:
        return []
    date_col = next(c for c in cols if str(c).startswith("Date"))
    size_col = next((c for c in cols if str(c).startswith("Sample")), None)
    other_col = next((c for c in cols if str(c).startswith("Other")), None)
    und_col = next((c for c in cols if str(c).startswith("Undecided")), None)
    rows = []
    for _, r in tb.iterrows():
        raw_src = str(r[src])
        if raw_src == "nan" or pct(r[dcol]) != pct(r[dcol]):  # skip separator/event rows
            continue
        pollster = re.sub(r"\[.*?\]|\((R|D)\)", "", raw_src).strip()
        party = re.search(r"\((R|D)\)", raw_src)
        size = clean(r[size_col]) if size_col else ""
        n = re.match(r"([\d,]+)", size)
        pop = re.search(r"\((LV|RV|A|V)\)", size)
        start, end = parse_dates(str(r[date_col]))
        rows.append({
            "pollster": pollster,
            "pollster_party": party.group(1) if party else "",
            # Upper-case footnote letters on Wikipedia poll tables mark partisan clients.
            "sponsored": bool(re.search(r"\[[A-Z]{1,2}\]", raw_src)),
            "start_date": start, "end_date": end,
            "sample_size": int(n.group(1).replace(",", "")) if n else None,
            "population": pop.group(1) if pop else "",
            "dem_pct": pct(r[dcol]), "rep_pct": pct(r[rcol]),
            "other_pct": pct(r[other_col]) if other_col else float("nan"),
            "undecided_pct": pct(r[und_col]) if und_col else float("nan"),
            "dem_col": str(dcol), "rep_col": str(rcol),
        })
    return rows


def race_pages(office: str, state_po: str, special: bool) -> list[str]:
    st = PO_STATE[state_po].replace(" ", "_")
    if office == "SEN":
        return [f"2026_United_States_Senate_special_election_in_{st}" if special
                else f"2026_United_States_Senate_election_in_{st}"]
    if office == "GOV":
        return [f"2026_{st}_gubernatorial_election"]
    return [f"2026_United_States_House_of_Representatives_elections_in_{st}"]


def slot_candidates(r) -> tuple[str, str]:
    """The two names that define the race: Democratic slot vs Republican slot."""
    dem = str(r["dem_candidate"]) if pd.notna(r["dem_candidate"]) else ""
    rep = str(r["rep_candidate"]) if pd.notna(r["rep_candidate"]) else ""
    if r["race_type"] == "independent":
        # The independent takes the slot of the missing party.
        (rep, dem) = (r["race_note"], dem) if not rep else (rep, r["race_note"])
    if r["race_type"] == "rcv_bloc":
        # Several Republicans on the ballot: the incumbent (or first listed) anchors the bloc.
        reps = rep.split("; ")
        rep = next((x for x in reps if last_name(x) == last_name(str(r["incumbent"]))), reps[0])
    return dem.split("; ")[0], rep


def district_from_heading(heading: str):
    m = re.search(r"District (\d+)|(\d+)(?:st|nd|rd|th) district|At-large", heading, re.I)
    if not m:
        return None
    return int(m.group(1) or m.group(2)) if (m.group(1) or m.group(2)) else 0


def main(refresh: bool = False) -> None:
    races = []
    for office, f in [("SEN", "senate"), ("GOV", "governor"), ("HOUSE", "house")]:
        df = pd.read_csv(PROC / f"races_2026_{f}.csv")
        df["office"] = office
        if office == "HOUSE":
            df["special"] = False
        races.append(df)
    races = pd.concat(races, ignore_index=True)
    races = races[races["race_type"].isin(["standard", "independent", "rcv_bloc"])]

    out = []
    house_pages_done = {}
    for _, r in races.iterrows():
        dem, rep = slot_candidates(r)
        for page in race_pages(r["office"], r["state_po"], r["special"]):
            if r["office"] == "HOUSE":
                if page not in house_pages_done:
                    html = fetch(page, refresh)
                    house_pages_done[page] = list(poll_tables(html)) if html else []
                tables = [(h, tb) for h, tb in house_pages_done[page]
                          if district_from_heading(h) == int(r["district"])]
            else:
                html = fetch(page, refresh)
                tables = list(poll_tables(html)) if html else []
            for heading, tb in tables:
                for row in parse_table(tb, dem, rep):
                    out.append({"office": r["office"], "state_po": r["state_po"],
                                "district": r.get("district"), "special": r["special"],
                                "dem_candidate": dem, "rep_candidate": rep,
                                **row, "source_page": page, "heading": heading})
    polls = pd.DataFrame(out)
    polls = polls.drop_duplicates(["office", "state_po", "district", "special", "pollster",
                                   "start_date", "end_date", "sample_size"], keep="first")
    polls.to_csv(PROC / "polls_2026_wikipedia.csv", index=False)
    print(f"{len(polls)} polls")
    print(polls.groupby("office").agg(polls=("pollster", "size"), races=("state_po", lambda s: s.nunique())))


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
