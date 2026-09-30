"""Fill gaps in MEDSL county data from Wikipedia county-results tables.

MEDSL's precinct files are missing a few statewide races entirely (or most of
a state's counties). Wikipedia race pages carry a full county-by-county table
for nearly every Senate and governor race, so we patch those specific races.

EXTRA_RACES adds whole elections our MEDSL files don't cover, so the site's Past results page is
complete from 2018: 2020 Senate and governor, 2024 governor, and the odd-year governor races
(Kentucky, Louisiana and Mississippi in 2019 and 2023; New Jersey and Virginia in 2021 and 2025).
On Louisiana's all-party ballots each party's candidates are added up. Georgia's 2020 regular Senate
race is the November vote (as MEDSL's other years); its 2020 special is the January 2021 runoff, since
the November all-party table lumps the minor Democrats together. Checked against statewide totals by
core/validate_county_results.py.
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
    import unicodedata
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()  # Coös -> Coos
    name = re.sub(r"\[.*?\]", "", name).lower()
    name = re.sub(r"\b(county|parish|city and borough|borough)\b", "", name)
    return re.sub(r"[^a-z]", "", name)


def _fetch(title: str) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{title}.html"
    if not path.exists():
        path.write_text(requests.get(f"https://en.wikipedia.org/wiki/{title}", headers=HEADERS).text,
                        encoding="utf-8")
    return path.read_text(encoding="utf-8")


PLACE = re.compile(r"county|parish|locality|city", re.I)


def _find_county_table(html: str, n: int | None = None, dem: str = "Democratic|DFL", rep: str = "Republican") -> pd.DataFrame:
    """A results-by-county table with both a Democratic and a Republican column (so a party primary's
    table is never picked). With several, the n-th, or by default the one with the most votes: the
    general election, not a top-two primary (Washington) that also lists both parties."""
    def tidy(tb):
        # a caption row stacked on top of the usual (candidate, #/%) headers (New Hampshire 2024): drop it
        return tb.droplevel(0, axis=1) if isinstance(tb.columns, pd.MultiIndex) and tb.columns.nlevels == 3 else tb
    def ok(tb):
        if not isinstance(tb.columns, pd.MultiIndex) or not PLACE.search(str(tb.columns[0])) or len(tb) < 3:
            return False
        tops = [str(c[0]) for c in tb.columns]
        return any(re.search(dem, x, re.I) for x in tops) and any(re.search(rep, x, re.I) for x in tops)
    tables = [tb for tb in map(tidy, pd.read_html(io.StringIO(html))) if ok(tb)]
    if n is not None:
        return tables[n]
    votes = lambda tb: sum(_num(tb[c]).sum() for c in tb.columns[1:] if str(c[1]).strip() in VOTE_SUBS)  # noqa: E731
    return max(tables, key=votes)


VOTE_SUBS = ("#", "Votes", "Total", "Total votes", "Total votes cast", "Votes cast")


def _num(col: pd.Series) -> pd.Series:
    """Vote counts from a table column: "1,234", "1234.0" or "5,678[a]" -> numbers."""
    if pd.api.types.is_numeric_dtype(col):
        return col
    return pd.to_numeric(col.astype(str).str.replace(r"\[.*?\]|,|\s", "", regex=True), errors="coerce")


def _count_col(tb: pd.DataFrame, top):
    """A candidate's vote-count column. Some tables put the "#" and "%" labels over the wrong columns
    (Indiana 2020), so take whichever of the candidate's columns holds counts rather than percentages."""
    cols = [c for c in tb.columns if c[0] == top]
    def countish(c):
        v = tb[c].astype(str)
        return (v.str.contains("%").mean() < 0.5, _num(tb[c]).sum())
    return max(cols, key=countish)


def _tops(tb: pd.DataFrame, pattern: str) -> list:
    tops = []
    for top, sub in tb.columns:
        if re.search(pattern, str(top), re.I) and not re.match(r"margin", str(top), re.I) and top not in tops:
            tops.append(top)
    if not tops:
        raise KeyError(pattern)
    return tops


def _vote_col(tb: pd.DataFrame, pattern: str):
    return _count_col(tb, _tops(tb, pattern)[0])


def _vote_cols(tb: pd.DataFrame, pattern: str) -> list:
    """Every candidate column for a party (an all-party ballot can have several)."""
    return [_count_col(tb, t) for t in _tops(tb, pattern)]


# Races whose tables label candidates without a party, or with another party line: (Democratic, Republican)
PARTY_PATTERNS = {
    (2019, "KY", "GOV"): ("Beshear", "Bevin"),
    (2023, "KY", "GOV"): ("Beshear", "Cameron"),
    (2020, "VT", "GOV"): ("Zuckerman", "Republican"),  # the Democratic nominee ran on the Progressive line too
}
# All-party ballots, where a party can have several candidates: add them up. Everywhere else the
# nominee's column (a write-in or endorsed extra of the same party is left out, as in the official D-vs-R result).
MULTI = {(2020, "LA", "SEN", False), (2019, "LA", "GOV", False), (2023, "LA", "GOV", False)}
NOT_COUNTIES = re.compile(r"^(total|overseas|uocava|federal|militar|absentee|provisional|statewide)", re.I)


def patch_race(year: int, state_po: str, office: str, special: bool, page,
               state_name: str) -> pd.DataFrame:
    title, n = (page, None) if isinstance(page, str) else page
    dem_p, rep_p = PARTY_PATTERNS.get((year, state_po, office), ("Democratic|DFL", "Republican"))
    tb = _find_county_table(_fetch(title), n, dem_p, rep_p)
    county = tb[tb.columns[0]].astype(str)
    num = lambda c: _num(tb[c])  # noqa: E731
    multi = (year, state_po, office, special) in MULTI
    party = lambda p: sum(num(c).fillna(0) for c in _vote_cols(tb, p)) if multi else num(_vote_col(tb, p))  # noqa: E731
    try:
        total = num(_vote_col(tb, r"^Total"))
    except KeyError:  # no total column: add up every candidate's votes
        total = sum(num(_count_col(tb, t)).fillna(0) for t in dict.fromkeys(c[0] for c in tb.columns[1:])
                    if not re.match(r"margin", str(t), re.I))
    out = pd.DataFrame({"key": county.map(_norm), "raw": county, "dem": party(dem_p), "rep": party(rep_p), "total": total})
    out = out[~out["raw"].astype(str).str.strip().str.match(NOT_COUNTIES) & (out["key"] != "")].drop(columns="raw").dropna()
    fips = _county_fips_lookup()
    fips = fips[fips["state_name"].str.upper() == state_name.upper()]
    out = out.merge(fips, on="key", how="left")
    # Virginia's independent cities appear without "city" unless a county shares the name ("Alexandria",
    # but "Fairfax City"): try the name with "city" added
    by_key = fips.set_index("key")["county_fips"]
    miss = out["county_fips"].isna()
    out.loc[miss, "county_fips"] = (out.loc[miss, "key"] + "city").map(by_key)
    missing = out[out["county_fips"].isna()]["key"].tolist()
    if missing:
        raise ValueError(f"{title}: unmatched counties {missing}")
    return out.assign(year=year, state_po=state_po, office=office, special=special)[
        ["year", "state_po", "county_fips", "office", "special", "dem", "rep", "total"]]


STATE_NAMES = {"AL": "Alabama", "AZ": "Arizona", "CA": "California", "CO": "Colorado", "DE": "Delaware",
               "GA": "Georgia", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
               "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MA": "Massachusetts", "MI": "Michigan",
               "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
               "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NC": "North Carolina",
               "ND": "North Dakota", "OK": "Oklahoma", "OR": "Oregon", "RI": "Rhode Island", "SC": "South Carolina",
               "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
               "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WY": "Wyoming"}

_SEN_2020 = ["AL", "CO", "DE", "GA", "ID", "IL", "IA", "KS", "KY", "LA", "ME", "MA", "MI", "MN", "MS", "MT", "NE",
             "NH", "NJ", "NM", "NC", "OK", "OR", "RI", "SC", "SD", "TN", "TX", "VA", "WV", "WY"]  # AR: no Democrat
_GOV_EVEN = ["DE", "IN", "MO", "MT", "NH", "NC", "ND", "UT", "VT", "WA", "WV"]  # the 2020 and 2024 governor races
_w = lambda s: STATE_NAMES[s].replace(" ", "_")  # noqa: E731
EXTRA_RACES = {
    **{(2020, s, "SEN", False): f"2020_United_States_Senate_election_in_{_w(s)}" for s in _SEN_2020},
    (2020, "AZ", "SEN", True): "2020_United_States_Senate_special_election_in_Arizona",
    # the January 2021 runoff (second table): November's all-party table lumps the minor Democrats into "other"
    (2020, "GA", "SEN", True): ("2020–21_United_States_Senate_special_election_in_Georgia", 1),
    **{(2020, s, "GOV", False): f"2020_{_w(s)}_gubernatorial_election" for s in _GOV_EVEN},
    **{(2024, s, "GOV", False): f"2024_{_w(s)}_gubernatorial_election" for s in _GOV_EVEN},
    **{(y, s, "GOV", False): f"{y}_{_w(s)}_gubernatorial_election" for y in (2019, 2023) for s in ("KY", "LA", "MS")},
    **{(y, s, "GOV", False): f"{y}_{_w(s)}_gubernatorial_election" for y in (2021, 2025) for s in ("NJ", "VA")},
}


def all_patches() -> pd.DataFrame:
    return pd.concat([patch_race(*k, title, STATE_NAMES[k[1]]) for k, title in PATCHES.items()],
                     ignore_index=True)


def extra_races(pause: float = 1.0) -> tuple[pd.DataFrame, dict]:
    """Every race in EXTRA_RACES that parses; returns (rows, {race: error}) so one bad page doesn't stop the rest."""
    import time
    parts, failed = [], {}
    for k, title in EXTRA_RACES.items():
        cached = (CACHE / f"{title}.html").exists()
        try:
            parts.append(patch_race(*k, title, STATE_NAMES[k[1]]))
        except Exception as e:  # noqa: BLE001
            failed[k] = f"{type(e).__name__}: {str(e)[:160]}"
        if not cached:
            time.sleep(pause)  # be gentle with Wikipedia
    return (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()), failed
