"""Fill gaps in MEDSL county data from Wikipedia county-results tables.

MEDSL's precinct files are missing a few statewide races entirely (or most of
a state's counties). Wikipedia race pages carry a full county-by-county table
for nearly every Senate and governor race, so we patch those specific races.
"""
from pathlib import Path
import io
import re

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CACHE = RAW / "wikipedia"
HEADERS = {"User-Agent": "politics-forecast-research/0.1 (personal project)"}

# (year, state_po, office, special) -> page title, or (title, n) to use the
# n-th county table on the page (0-based) when a page covers several races.
PATCHES = {
    (2018, "IN", "SEN", False): "2018_United_States_Senate_election_in_Indiana",
    (2022, "IN", "SEN", False): "2022_United_States_Senate_election_in_Indiana",
    (2022, "TN", "GOV", False): "2022_Tennessee_gubernatorial_election",
    # This page has two county tables: the partial-term special, then the full term.
    (2022, "CA", "SEN", False): ("2022_United_States_Senate_elections_in_California", 1),
}


def _county_fips_lookup() -> pd.DataFrame:
    df = pd.read_csv(RAW / "county_pres" / "2020_US_County_Level_Presidential_Results.csv")
    df["key"] = df["county_name"].map(_norm)
    return df[["state_name", "key", "county_fips"]]


def _norm(name: str) -> str:
    name = re.sub(r"\[.*?\]", "", str(name)).lower()
    name = re.sub(r"\b(county|parish|city and borough|borough)\b", "", name)
    return re.sub(r"[^a-z]", "", name)


def _fetch(title: str) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{title}.html"
    if not path.exists():
        path.write_text(requests.get(f"https://en.wikipedia.org/wiki/{title}", headers=HEADERS).text,
                        encoding="utf-8")
    return path.read_text(encoding="utf-8")


def _find_county_table(html: str, n: int = 0) -> pd.DataFrame:
    tables = [tb for tb in pd.read_html(io.StringIO(html))
              if isinstance(tb.columns, pd.MultiIndex)
              and "county" in str(tb.columns[0][0]).lower() and len(tb) > 10]
    return tables[n]


def _vote_col(tb: pd.DataFrame, pattern: str):
    for top, sub in tb.columns:
        if re.search(pattern, str(top), re.I) and str(sub).strip() in ("#", "Votes", "Total", "Total votes", "Total votes cast"):
            return (top, sub)
    raise KeyError(pattern)


def patch_race(year: int, state_po: str, office: str, special: bool, page,
               state_name: str) -> pd.DataFrame:
    title, n = (page, 0) if isinstance(page, str) else page
    tb = _find_county_table(_fetch(title), n)
    county = tb[tb.columns[0]].astype(str)
    num = lambda c: pd.to_numeric(tb[c].astype(str).str.replace(r"[^\d]", "", regex=True), errors="coerce")
    out = pd.DataFrame({
        "key": county.map(_norm),
        "dem": num(_vote_col(tb, "Democratic")),
        "rep": num(_vote_col(tb, "Republican")),
        "total": num(_vote_col(tb, r"^Total")),
    })
    out = out[~out["key"].str.startswith("total")].dropna()
    fips = _county_fips_lookup()
    fips = fips[fips["state_name"].str.upper() == state_name.upper()]
    out = out.merge(fips, on="key", how="left")
    missing = out[out["county_fips"].isna()]["key"].tolist()
    if missing:
        raise ValueError(f"{title}: unmatched counties {missing}")
    return out.assign(year=year, state_po=state_po, office=office, special=special)[
        ["year", "state_po", "county_fips", "office", "special", "dem", "rep", "total"]]


STATE_NAMES = {"IN": "Indiana", "TN": "Tennessee", "CA": "California"}


def all_patches() -> pd.DataFrame:
    return pd.concat([patch_race(*k, title, STATE_NAMES[k[1]]) for k, title in PATCHES.items()],
                     ignore_index=True)
