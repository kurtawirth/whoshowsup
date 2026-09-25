"""Other outlets' race ratings, as Wikipedia's election pages listed them on a given date.

    .venv/Scripts/python.exe core/outlet_ratings.py            # 2018-2024 at Sept 22 + Election Eve, and 2026 now

DISPLAY AND COMPARISON ONLY. These ratings are never a model input.

Wikipedia's Senate / governor / House overview pages carry a "Predictions" (ratings) table
that collects the major raters (Cook, Sabato's Crystal Ball, Inside Elections, ...), each
column dated and cited. Using the page revision in force on a date gives the ratings as they
stood that day, which is what makes a same-date comparison with our model fair.

Output (long format): data/processed/outlet_ratings.csv
    year, asof, office, state_po, district, special, outlet, rating_raw, rating
where rating is one of Safe D, Likely D, Lean D, Toss-up, Lean R, Likely R, Safe R
("Tilt" folds into Lean; "Solid" = Safe).
"""
from pathlib import Path
import io
import re
import sys
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "wikipedia_revisions"
PROC = ROOT / "data" / "processed"
API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "WhoShowsUp-forecast/1.0 (https://github.com/kurtawirth/whoshowsup)"}

ELECTION_DAY = {2018: "2018-11-06", 2020: "2020-11-03", 2022: "2022-11-08", 2024: "2024-11-05", 2026: "2026-11-03"}
PAGES = {"SEN": "{y}_United_States_Senate_elections", "GOV": "{y}_United_States_gubernatorial_elections",
         "HOUSE": "{y}_United_States_House_of_Representatives_elections"}
# Column-name prefix -> outlet name. Only outlets that rate races (not pure vote-share models).
OUTLETS = {"cook": "Cook Political Report", "ie": "Inside Elections", "i.e.": "Inside Elections",
           "the cook political report": "Cook Political Report", "inside elections": "Inside Elections",
           "sabato's crystal ball": "Sabato's Crystal Ball", "the economist": "The Economist",
           "split ticket": "Split Ticket", "silver bulletin": "Silver Bulletin", "decision desk hq": "DDHQ",
           "fiftyplusone": "FiftyPlusOne", "realclearpolitics": "RealClearPolitics", "real clear politics": "RealClearPolitics",
           "fivethirtyeight": "FiveThirtyEight", "elections daily": "Elections Daily", "cnalysis": "CNalysis", "inside": "Inside Elections",
           "sabato": "Sabato's Crystal Ball", "crystal": "Sabato's Crystal Ball",
           "silver": "Silver Bulletin", "econ": "The Economist", "st": "Split Ticket", "split": "Split Ticket",
           "ddhq": "DDHQ", "fpo": "FiftyPlusOne", "fox": "Fox News", "rcp": "RealClearPolitics",
           "538": "FiveThirtyEight", "fte": "FiveThirtyEight", "cnalysis": "CNalysis", "politico": "Politico",
           "cnn": "CNN", "nyt": "New York Times", "npr": "NPR", "rcpol": "RealClearPolitics",
           "daily": "Daily Kos", "dk": "Daily Kos", "elections": "Elections Daily", "ed": "Elections Daily",
           "rrh": "Red Racing Horses", "the": None, "270": "270toWin", "jhk": "JHK Forecasts",
           "decision": "DDHQ", "the hill": "DDHQ", "lean": None}
STATES = {"Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
          "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
          "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
          "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
          "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
          "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
          "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
          "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
          "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
          "Wisconsin": "WI", "Wyoming": "WY"}


def normalize(raw) -> str | None:
    """'Solid R' / 'Safe R' -> Safe R; 'Tilt D' -> Lean D; 'Tossup' / 'Toss-up' -> Toss-up.
    Independent-side ratings (e.g. 'Lean I' for Osborn) count as the non-Republican side."""
    s = re.sub(r"\[.*?\]|\(.*?\)", "", str(raw)).strip().lower()
    if not s or s == "nan":
        return None
    if "toss" in s:
        return "Toss-up"
    side = "D" if re.search(r"\b(d|dem|democratic|i|ind|independent|dfl)\b", s) else "R" if re.search(r"\b(r|rep|republican|gop)\b", s) else None
    if side is None:
        return None
    for word, cat in (("safe", "Safe"), ("solid", "Safe"), ("likely", "Likely"), ("lean", "Lean"), ("tilt", "Lean")):
        if word in s:
            return f"{cat} {side}"
    return None


def revision_html(title: str, asof: str | None) -> tuple[str, str] | None:
    """Rendered HTML of the page revision in force at the end of `asof` (YYYY-MM-DD), or the
    current page if asof is None. Cached."""
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"{title}__{asof or 'current'}.html"
    if path.exists() and asof:
        text = path.read_text(encoding="utf-8")
        rev, html = text.split("\n", 1)
        return rev, html
    params = {"action": "query", "prop": "revisions", "titles": title.replace("_", " "), "rvlimit": 1,
              "rvprop": "ids|timestamp", "format": "json", "redirects": 1}
    if asof:
        params.update({"rvstart": f"{asof}T23:59:59Z", "rvdir": "older"})
    r = requests.get(API, params=params, headers=HEADERS, timeout=60).json()
    page = next(iter(r["query"]["pages"].values()))
    if "revisions" not in page:
        return None
    rev = page["revisions"][0]["revid"]
    p = requests.get(API, params={"action": "parse", "oldid": rev, "prop": "text", "format": "json",
                                  "formatversion": 2}, headers=HEADERS, timeout=120).json()
    html = p["parse"]["text"]
    path.write_text(f"{rev}\n{html}", encoding="utf-8")
    time.sleep(0.5)  # be polite
    return str(rev), html


def outlet_of(col: str) -> str | None:
    c = re.sub(r"\[.*?\]", "", str(col)).strip().lower()
    for key in sorted(OUTLETS, key=len, reverse=True):
        if re.match(re.escape(key) + r"(?![a-z])", c):
            return OUTLETS[key]
    return None


def rating_tables(html: str):
    """Yield DataFrames that look like ratings tables (several outlet columns)."""
    soup = BeautifulSoup(html, "lxml")
    for t in soup.find_all("table", class_="wikitable"):
        head = t.get_text(" ", strip=True)[:600]
        if not re.search(r"Cook|Sabato|Crystal Ball|Inside Elections", head):
            continue
        try:
            tb = pd.read_html(io.StringIO(str(t)))[0]
        except ValueError:
            continue
        if isinstance(tb.columns, pd.MultiIndex):
            tb.columns = [c[-1] if not str(c[-1]).startswith("Unnamed") else c[0] for c in tb.columns]
        outs = [c for c in tb.columns if outlet_of(c)]
        if len(outs) >= 2:
            yield tb, outs


def vertical_house_tables(html: str, state_po: str):
    """Per-state House pages: under each district's heading, a table with rows
    Source | Ranking | As of. Yields (district, outlet, rating_raw)."""
    soup = BeautifulSoup(html, "lxml")
    district = 0  # at-large states have no "District N" headings
    for el in soup.find_all(["h2", "h3", "h4", "table"]):
        if el.name != "table":
            t = el.get_text(" ", strip=True)
            m = re.search(r"District\s+(\d+)", t, re.I)
            if m and el.name in ("h2", "h3"):
                district = int(m.group(1))
            elif re.search(r"at[- ]large", t, re.I) and el.name in ("h2", "h3"):
                district = 0
            continue
        if district is None or "wikitable" not in (el.get("class") or []):
            continue
        head = el.get_text(" ", strip=True)[:120].lower()
        if not (head.startswith("source") and ("ranking" in head or "rating" in head)):
            continue
        try:
            tb = pd.read_html(io.StringIO(str(el)))[0]
        except ValueError:
            continue
        cols = [str(c).lower() for c in tb.columns]
        if len(cols) < 2:
            continue
        for _, r in tb.iterrows():
            outlet = outlet_of(r.iloc[0])
            if outlet:
                yield district, outlet, r.iloc[1]


def parse_place(office: str, text: str):
    """Row label -> (state_po, district, special)."""
    s = re.sub(r"\[.*?\]", "", str(text)).strip()
    special = "special" in s.lower() or "(class" in s.lower()
    if office == "HOUSE":
        m = re.match(r"([A-Za-z .]+?)\s*(\d+|at-large|AL)\b", s, re.I)
        if not m or m.group(1).strip() not in STATES:
            return None
        d = m.group(2)
        return STATES[m.group(1).strip()], 0 if not d.isdigit() else int(d), False
    name = re.sub(r"\(.*?\)|special|\bclass\b.*", "", s, flags=re.I).strip()
    if name not in STATES:
        return None
    return STATES[name], 0, special


def page_with_table(title: str, asof: str | None, election: str):
    """The revision on `asof`; if its ratings table is missing (pages are sometimes reshuffled
    around Election Day), the first later revision that has it -- final pre-election ratings stay
    on the page after the vote, each column still dated."""
    tries = [asof] if asof is None else [asof] + [str((pd.Timestamp(election) + pd.Timedelta(days=d)).date())
                                                  for d in (14, 45)] * (asof >= election[:4] + "-11-01")
    for d in tries:
        got = revision_html(title, d)
        if got and any(True for _ in rating_tables(got[1])):
            return got
    return None


def ratings(year: int, asof: str | None) -> pd.DataFrame:
    rows = []
    for office, pat in PAGES.items():
        got = page_with_table(pat.format(y=year), asof, ELECTION_DAY[year])
        if got is None:
            continue
        rev, html = got
        for tb, outs in rating_tables(html):
            label_col = tb.columns[0]
            for _, r in tb.iterrows():
                place = parse_place(office, r[label_col])
                if place is None:
                    continue
                for c in outs:
                    val = r[c]
                    if isinstance(val, pd.Series):
                        val = val.iloc[0]
                    cat = normalize(val)
                    if cat:
                        rows.append({"year": year, "asof": asof or "current", "office": office,
                                     "state_po": place[0], "district": place[1], "special": place[2],
                                     "outlet": outlet_of(c), "rating_raw": str(val), "rating": cat, "revid": rev})
    if not any(r["office"] == "HOUSE" for r in rows):
        for name, po in STATES.items():
            got = revision_html(f"{year}_United_States_House_of_Representatives_elections_in_{name.replace(' ', '_')}", asof)
            if got is None:
                continue
            rev, html = got
            for district, outlet, raw in vertical_house_tables(html, po):
                cat = normalize(raw)
                if cat:
                    rows.append({"year": year, "asof": asof or "current", "office": "HOUSE", "state_po": po,
                                 "district": district, "special": False, "outlet": outlet,
                                 "rating_raw": str(raw), "rating": cat, "revid": rev})
    df = pd.DataFrame(rows)
    if len(df):
        df = df.drop_duplicates(["year", "asof", "office", "state_po", "district", "special", "outlet"])
    return df


def main() -> None:
    frames = []
    for y in (2018, 2020, 2022, 2024):
        eday = pd.Timestamp(ELECTION_DAY[y])
        for label, date in (("sep22", f"{y}-09-22"), ("eve", str((eday - pd.Timedelta(days=1)).date()))):
            df = ratings(y, date)
            if len(df):
                df["asof"] = label
            frames.append(df)
            print(y, label, len(df), df.groupby(["office", "outlet"]).size().unstack(0).fillna(0).astype(int).to_dict() if len(df) else {})
    now = ratings(2026, None)
    now["asof"] = "current"
    frames.append(now)
    print(2026, "current", len(now))
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(PROC / "outlet_ratings.csv", index=False)
    print(f"wrote {PROC / 'outlet_ratings.csv'} ({len(out)} rows)")


if __name__ == "__main__":
    main()
