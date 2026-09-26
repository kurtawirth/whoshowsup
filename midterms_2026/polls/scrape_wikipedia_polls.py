"""Collect 2026 general-election polls from Wikipedia race pages.

For every Senate and Governor race, and every House district (the state's House
page, plus the district's own article where one exists), read each poll table and keep only polls that include BOTH
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


FAILED: list[str] = []  # pages that could not be downloaded this run (their cached copy was used, if any)
ISSUES: list[str] = []  # recent poll tables that yielded no polls of the nominees (read by the daily run)


def fetch(title: str, refresh: bool = False) -> str | None:
    path = RAW / f"{title}.html"
    if refresh or not path.exists():
        try:
            r = requests.get(f"https://en.wikipedia.org/wiki/{title}", headers=HEADERS, timeout=60)
            ok = r.status_code == 200
        except requests.RequestException:
            ok = False
        if ok:
            path.write_text(r.text, encoding="utf-8")
        else:
            FAILED.append(title)  # a failed download must not silently drop the page's polls
        time.sleep(0.3)  # be polite to Wikipedia
    return path.read_text(encoding="utf-8") if path.exists() else None


ORD = lambda n: f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def district_title(state_po: str, district: int) -> str:
    st = PO_STATE[state_po].replace(" ", "_")
    return f"2026_{st}'s_{'at-large' if district == 0 else ORD(district)}_congressional_district_election"


def district_articles(races: pd.DataFrame, refresh: bool = False) -> set[str]:
    """Titles of the House races that have their own Wikipedia article (competitive districts
    often do, and their polls may be listed only there). Checked 50 titles per API call."""
    path = RAW / "district_articles.txt"
    if not refresh and path.exists():
        return set(path.read_text(encoding="utf-8").split())
    titles = [district_title(r.state_po, int(r.district)) for r in races[races["office"] == "HOUSE"].itertuples()]
    found = set()
    try:
        for i in range(0, len(titles), 50):
            r = requests.get("https://en.wikipedia.org/w/api.php", headers=HEADERS, timeout=60, params={
                "action": "query", "format": "json", "prop": "info", "titles": "|".join(t.replace("_", " ") for t in titles[i:i + 50])})
            r.raise_for_status()
            # a redirect usually points at the state page, whose tables cover every district: skip those
            found |= {p["title"].replace(" ", "_") for p in r.json()["query"]["pages"].values()
                      if "missing" not in p and "redirect" not in p}
    except (requests.RequestException, KeyError, ValueError):
        FAILED.append("district article list")
        return set(path.read_text(encoding="utf-8").split()) if path.exists() else set()
    path.write_text("\n".join(sorted(found)), encoding="utf-8")
    return found


def page_refs(html: str) -> dict[str, str]:
    """Footnote number as shown on the page ("12") -> the cited source's URL.
    Poll tables cite each poll's original release with a numbered footnote on the pollster name."""
    soup = BeautifulSoup(html, "lxml")
    out = {}
    for a in soup.select("sup.reference a[href^='#cite_note']"):
        label = a.get_text(strip=True).strip("[]")
        if not label.isdigit() or label in out:
            continue
        li = soup.find(id=a["href"][1:])
        ext = li.select_one("a.external[href^='http']") if li else None
        if ext:
            out[label] = ext["href"]
    return out


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


def name_hits(options, name: str) -> list:
    """Options (column headers, answer labels) naming this candidate. Matched on last name; when
    two share it (Alaska 2026 has Dan S. Sullivan and Dan J. Sullivan), on the full name."""
    ln = last_name(name)
    hits = [o for o in options if ln and ln in str(o).lower()]
    if len(hits) > 1:
        full = re.sub(r"\s+", " ", name.lower()).strip()
        hits = [o for o in hits if full in re.sub(r"\s+", " ", str(o).lower())]
    return hits


def find_col(cols, name: str):
    hits = name_hits(cols, name)
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


def parse_table(tb: pd.DataFrame, dem: str, rep: str, refs: dict | None = None,
                dem_bloc=(), rep_bloc=()) -> list[dict]:
    """Polls in one table that include both slot candidates. In Alaska's bloc races the other
    candidates of each side (dem_bloc / rep_bloc) are added to that side's share."""
    cols = list(tb.columns)
    src = next((c for c in cols if str(c).startswith("Poll source")), None)
    dcol, rcol = find_col(cols, dem), find_col(cols, rep)
    if src is None or dcol is None or rcol is None or dcol == rcol:
        return []
    extra = lambda names: list(dict.fromkeys(c for c in (find_col(cols, n) for n in names) if c is not None and c not in (dcol, rcol)))
    dextra, rextra = extra(dem_bloc), extra(rep_bloc)
    share = lambda r, c, more: pct(r[c]) + sum(0.0 if pct(r[x]) != pct(r[x]) else pct(r[x]) for x in more)
    date_col = next(c for c in cols if str(c).startswith("Date"))
    size_col = next((c for c in cols if str(c).startswith("Sample")), None)
    other_col = next((c for c in cols if str(c).startswith("Other")), None)
    und_col = next((c for c in cols if str(c).startswith("Undecided")), None)
    rows = []
    for _, r in tb.iterrows():
        raw_src = str(r[src])
        if raw_src == "nan" or pct(r[dcol]) != pct(r[dcol]) or pct(r[rcol]) != pct(r[rcol]):  # separator/event rows
            continue
        pollster = re.sub(r"\[.*?\]|\((R|D)\)", "", raw_src).strip()
        party = re.search(r"\((R|D)\)", raw_src)
        size = clean(r[size_col]) if size_col else ""
        n = re.match(r"([\d,]+)", size)
        pop = re.search(r"\((LV|RV|A|V)\)", size)
        start, end = parse_dates(str(r[date_col]))
        cites = re.findall(r"\[(\d+)\]", raw_src) + re.findall(r"\[(\d+)\]", str(r[date_col]))
        src_url = next(((refs or {}).get(c) for c in cites if (refs or {}).get(c)), "")
        rows.append({
            "source_url": src_url,
            "pollster": pollster,
            "pollster_party": party.group(1) if party else "",
            # Upper-case footnote letters on Wikipedia poll tables mark partisan clients.
            "sponsored": bool(re.search(r"\[[A-Z]{1,2}\]", raw_src)),
            "start_date": start, "end_date": end,
            "sample_size": int(n.group(1).replace(",", "")) if n else None,
            "population": pop.group(1) if pop else "",
            "dem_pct": share(r, dcol, dextra), "rep_pct": share(r, rcol, rextra),
            "other_pct": pct(r[other_col]) if other_col else float("nan"),
            "undecided_pct": pct(r[und_col]) if und_col else float("nan"),
            "dem_col": str(dcol), "rep_col": str(rcol),
        })
    if any(str(c).startswith("RCV round") for c in cols):
        # Ranked-choice tables list each round: keep a poll's final round (the head-to-head).
        # Rounds can carry different sample sizes (ballots exhausted), so match on pollster and dates.
        last = {}
        for row in rows:
            last[(row["pollster"], row["start_date"], row["end_date"])] = row
        rows = list(last.values())
    return rows


def race_pages(office: str, state_po: str, special: bool, district: int = 1) -> list[str]:
    st = PO_STATE[state_po].replace(" ", "_")
    if office == "SEN":
        return [f"2026_United_States_Senate_special_election_in_{st}" if special
                else f"2026_United_States_Senate_election_in_{st}"]
    if office == "GOV":
        return [f"2026_{st}_gubernatorial_election"]
    if district == 0:  # one-district states: "...House of Representatives election in Alaska" (singular)
        return [f"2026_United_States_House_of_Representatives_election_in_{st}"]
    return [f"2026_United_States_House_of_Representatives_elections_in_{st}"]


# The Republican who anchors an Alaska bloc race, where the rule below (the incumbent, else the first
# listed) picks the wrong one. Senate: the incumbent is Dan S. Sullivan; Dan J. Sullivan is a different
# Republican. Governor (open seat): Bernadette Wilson leads the Republicans in every general-election
# poll (Sept 2026) and is the one polls test head to head; the rule would pick Dave Bronson.
BLOC_ANCHOR = {("SEN", "AK"): "Dan S. Sullivan", ("GOV", "AK"): "Bernadette Wilson"}


def bloc_names(r) -> tuple[list[str], list[str]]:
    """Every candidate on each side of an Alaska bloc race (empty for other races)."""
    if r["race_type"] != "rcv_bloc":
        return [], []
    split = lambda v: [x for x in str(v).split("; ") if x and x != "nan"]
    return split(r["dem_candidate"]), split(r["rep_candidate"])


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
        rep = BLOC_ANCHOR.get((r["office"], r["state_po"])) or next(
            (x for x in reps if last_name(x) == last_name(str(r["incumbent"]))), reps[0])
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

    FAILED.clear(); ISSUES.clear()
    districts = district_articles(races, refresh)
    recent = pd.Timestamp.today().normalize() - pd.Timedelta(days=21)
    out = []
    house_pages_done = {}
    for _, r in races.iterrows():
        dem, rep = slot_candidates(r)
        pages = race_pages(r["office"], r["state_po"], r["special"], 0 if pd.isna(r.get("district")) else int(r["district"]))
        if r["office"] == "HOUSE" and district_title(r["state_po"], int(r["district"])) in districts:
            pages.append(district_title(r["state_po"], int(r["district"])))  # the district's own article
        for page in pages:
            if r["office"] == "HOUSE" and "_elections_in_" in page:  # a multi-district state page: this district's tables
                if page not in house_pages_done:
                    html = fetch(page, refresh)
                    house_pages_done[page] = (list(poll_tables(html)) if html else [], page_refs(html) if html else {})
                page_tables, refs = house_pages_done[page]
                tables = [(h, tb) for h, tb in page_tables if district_from_heading(h) == int(r["district"])]
            else:
                html = fetch(page, refresh)
                tables = list(poll_tables(html)) if html else []
                refs = page_refs(html) if html else {}
            for heading, tb in tables:
                rows = parse_table(tb, dem, rep, refs, *bloc_names(r))
                named = [c for c in tb.columns if not re.match(r"(Poll source|Date|Sample|Margin|Other|Undecided|Unnamed|RCV)", str(c))]
                if not rows and "primar" not in heading.lower() and not all(str(c).startswith("Generic") for c in named):
                    # A general-election table with fresh polls but none of the nominees' matchup: usually a
                    # hypothetical, but it may be a layout or name the parser can't read. Flag it for a look.
                    ends = [parse_dates(str(v))[1] for v in tb.get(next((c for c in tb.columns if str(c).startswith("Date")), ""), [])]
                    if any(pd.notna(e) and e >= recent for e in ends):
                        cols = [str(c) for c in named]
                        ISSUES.append(f"{r['office']} {r['state_po']}{'' if r['office'] != 'HOUSE' else '-' + str(int(r['district']))}: "
                                      f"recent Wikipedia poll table without {dem} vs {rep} (columns: {', '.join(cols)[:120]}) on {page}")
                for row in rows:
                    out.append({"office": r["office"], "state_po": r["state_po"],
                                "district": r.get("district"), "special": r["special"],
                                "dem_candidate": dem, "rep_candidate": rep,
                                **row, "source_page": page, "heading": heading})
    polls = pd.DataFrame(out)
    polls = polls.drop_duplicates(["office", "state_po", "district", "special", "pollster",
                                   "start_date", "end_date", "sample_size"], keep="first")
    polls.to_csv(PROC / "polls_2026_wikipedia.csv", index=False)
    print(f"{len(polls)} polls ({len(districts)} House districts have their own article, "
          f"{(polls['source_page'].isin(districts)).sum()} polls read from those)")
    print(polls.groupby("office").agg(polls=("pollster", "size"), races=("state_po", lambda s: s.nunique())))
    for t in FAILED:
        print("  download failed (older saved copy used if there is one):", t)
    for i in ISSUES:
        print("  check:", i)


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
