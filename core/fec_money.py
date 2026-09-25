"""Campaign money for House and Senate nominees, as it stood in mid-summer of each election year.

    .venv/Scripts/python.exe core/fec_money.py            # 2018-2026, cached after the first run
    .venv/Scripts/python.exe core/fec_money.py --refresh  # re-download this cycle's reports

For every D and R nominee we find their principal campaign committee in the FEC's bulk
candidate file (no API needed), then pull the latest report that committee had filed by
Sept 22 of the election year (usually the June 30 quarterly; a pre-primary or monthly report
where that came later) from the FEC API. The backtest therefore only sees money that was
public by Sept 22.

  money = cash on hand at the end of that report + everything spent since Jan 1 of the election year
        = cash banked going into the year + everything raised this year

A nominee with no committee (never raised the $5,000 that requires one) counts as $0; one whose
committee has no report on file counts as unknown, and that race gets no money reading.
Governors are state campaigns, not in FEC data, so this covers House and Senate only.

Writes data/processed/fec_money.csv: one row per race with each side's money and
money_log_ratio = ln((D + $25k) / (R + $25k)) -- the $25k keeps a paper candidate's $0 from
blowing up the ratio.

The API key lives in secrets/fec_api_key.txt (git-ignored). This key allows ~60 requests an
hour, so reports are asked for 100 committees at a time and every response is cached.
"""
from pathlib import Path
import json
import re
import unicodedata
import sys
import time

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW, PROC = ROOT / "data" / "raw" / "fec", ROOT / "data" / "processed"
MEDSL = ROOT / "data" / "raw" / "medsl"
YEARS = [2018, 2020, 2022, 2024, 2026]
FLOOR = 25_000
API = "https://api.open.fec.gov/v1/reports/house-senate/"
CN_COLS = ["cand_id", "name", "party", "election_yr", "state_po", "office", "district", "ici", "status", "pcc"]
SUFFIX = {"JR", "SR", "II", "III", "IV", "MR", "MRS", "MS", "DR", "HON"}


def words(name: str) -> list[str]:
    """Upper-case name words with accents, punctuation and suffixes removed."""
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().upper()
    return [w for w in re.sub(r"[^A-Z ]", " ", name).split() if w not in SUFFIX and w != "FOR"]


def keys_fec(name: str) -> set[str]:
    """FEC 'LAST, FIRST MIDDLE' -> {'LAST F'}, plus the reverse for rows filed backwards ('NICK, LALOTA')."""
    parts = str(name).split(",", 1)
    last, first = words(parts[0]), words(parts[1] if len(parts) > 1 else "")
    out = set()
    if last and first:
        out |= {f"{last[-1]} {first[0][0]}", f"{first[-1]} {last[0][0]}"}
    return out


def keys_plain(name: str) -> set[str]:
    """'John M. Katko' -> {'KATKO J'}; also 'WYDEN RON'-style surname-first -> 'WYDEN R';
    'SCHATZ, BRIAN' -> 'SCHATZ B'."""
    if "," in str(name) and words(str(name).split(",", 1)[1]):  # not just ', JR.'
        return keys_fec(name)
    w = words(name)
    return {f"{w[-1]} {w[0][0]}", f"{w[0]} {w[-1][0]}"} if len(w) >= 2 else set(w)


def candidates(year: int) -> pd.DataFrame:
    cn = pd.read_csv(RAW / f"cn{year % 100}.txt", sep="|", header=None, dtype=str, encoding="latin-1").iloc[:, :10]
    cn.columns = CN_COLS
    cn = cn[cn["office"].isin(["H", "S"])].copy()
    cn["side"] = cn["party"].map({"DEM": "D", "DFL": "D", "REP": "R"})
    cn["district"] = pd.to_numeric(cn["district"], errors="coerce").fillna(0).astype(int)
    cn["keys"] = cn["name"].fillna("").map(keys_fec)
    cn["surnames"] = cn["keys"].map(lambda ks: {k.split()[0] for k in ks})
    return cn


def nominees(year: int) -> pd.DataFrame:
    """Top D and top R general-election candidate in every House and Senate race."""
    if year == 2026:
        rows = []
        h = pd.read_csv(PROC / "races_2026_house.csv")
        for _, r in h.iterrows():
            for side, col in (("D", "dem_candidate"), ("R", "rep_candidate")):
                if isinstance(r[col], str):
                    rows.append({"office": "HOUSE", "state_po": r["state_po"], "district": int(r["district"]),
                                 "special": False, "side": side, "name": r[col]})
        s = pd.read_csv(PROC / "races_2026_senate.csv")
        for _, r in s.iterrows():
            for side, col in (("D", "dem_candidate"), ("R", "rep_candidate")):
                if isinstance(r[col], str):
                    rows.append({"office": "SEN", "state_po": r["state_po"], "district": 0,
                                 "special": bool(r["special"]), "side": side, "name": r[col]})
        out = pd.DataFrame(rows)
        # several names in one cell (e.g. Alaska's top-four): one row per name
        out["name"] = out["name"].str.split(r";|/| and ")
        return out.explode("name").assign(name=lambda d: d["name"].str.strip()).reset_index(drop=True)
    sys.path.insert(0, str(ROOT / "core"))
    from house_calibration import house_results  # noqa: F401 (same fusion-aware side rules)
    h = pd.read_csv(MEDSL / "house_1976_2024.tab", sep=None, engine="python", encoding="latin-1")
    h = h[(h["year"] == year) & (h["stage"].str.upper() == "GEN") & ~h["special"].astype(str).str.upper().eq("TRUE")]
    h = h.assign(office="HOUSE", special=False, district=pd.to_numeric(h["district"], errors="coerce").fillna(0).astype(int))
    s = pd.read_csv(MEDSL / "senate_1976_2024.csv", encoding="latin-1")
    s = s[(s["year"] == year) & (s["stage"].str.lower() == "gen")]
    s = s.assign(office="SEN", district=0, special=s["special"].astype(str).str.upper().eq("TRUE"),
                 party=s["party_simplified"])
    x = pd.concat([h, s], ignore_index=True)
    x["party"] = x["party"].astype(str).str.upper()
    x["side"] = np.where(x["party"].str.contains("DEMOCRAT"), "D", np.where(x["party"].eq("REPUBLICAN"), "R", None))
    x = x[x["side"].notna() & x["candidate"].notna()]
    tot = x.groupby(["office", "state_po", "district", "special", "side", "candidate"], as_index=False)["candidatevotes"].sum()
    top = tot.sort_values("candidatevotes").groupby(["office", "state_po", "district", "special", "side"]).tail(1)
    return top.rename(columns={"candidate": "name"})[["office", "state_po", "district", "special", "side", "name"]]


def match(nom: pd.DataFrame, cn: pd.DataFrame, year: int) -> pd.DataFrame:
    """Nominee -> principal campaign committee, same office, state and district:
    1. same party and name (surname + first initial, either order);
    2. same party, unique surname (Bob vs. Robert);
    3. any party, same name (a nominee registered as an independent, like Alaska's Al Gross)."""
    out = []
    for _, r in nom.iterrows():
        area = cn[(cn["office"] == ("H" if r["office"] == "HOUSE" else "S")) & (cn["state_po"] == r["state_po"])]
        if r["office"] == "HOUSE":
            area = area[area["district"] == r["district"]]
        party = area[area["side"] == r["side"]]
        ks = keys_plain(r["name"])
        sur = {k.split()[0] for k in ks}
        pick = lambda df, col, want: df.loc[df[col].map(lambda x: bool(x & want)).astype(bool)] if len(df) else df
        hit = pick(party, "keys", ks)
        if hit.empty:
            h2 = pick(party, "surnames", sur)
            hit = h2 if h2["pcc"].nunique() == 1 else hit  # one campaign, even if filed under two ids
        if hit.empty:
            hit = pick(area, "keys", ks)
        # a returning candidate can have an old (terminated) committee too: prefer this cycle's record
        hit = hit.assign(cur=(hit["election_yr"] == str(year)).astype(int)).sort_values(["cur", "pcc"], ascending=[False, True],
                                                                                       na_position="last")
        pcc = hit["pcc"].dropna()
        out.append({**r.to_dict(), "cand_id": hit["cand_id"].iloc[0] if len(hit) else None,
                    "committee_id": pcc.iloc[0] if len(pcc) else None})
    return pd.DataFrame(out)


def api_key() -> str:
    return (ROOT / "secrets" / "fec_api_key.txt").read_text().strip()


def get(params: list, cache: Path, refresh: bool = False) -> dict:
    if cache.exists() and not refresh:
        return json.loads(cache.read_text())
    for attempt in range(90):
        r = requests.get(API, params=params + [("api_key", api_key())], timeout=60)
        if r.status_code == 429:  # hourly limit: wait and retry
            print("  rate limited; waiting a minute", flush=True)
            time.sleep(60)
            continue
        if not r.ok:  # don't echo the URL: it carries the API key
            raise RuntimeError(f"FEC API error {r.status_code}: {r.text[:200]}")
        cache.write_text(r.text)
        return r.json()
    raise RuntimeError("FEC API still rate-limited after 90 minutes")


def q2_reports(year: int, committees: list[str], refresh: bool = False, cutoff: str | None = None) -> pd.DataFrame:
    cutoff = cutoff or f"{year}-09-22"
    committees = sorted(set(c for c in committees if isinstance(c, str)))
    rows = []

    def fetch(chunk: list[str]) -> None:
        # Reports filed April 1 - Sept 22 of the election year: whatever each campaign had
        # reported by Sept 22 (later reports and amendments weren't public yet). The API's paging is unstable
        # (unsorted pages repeat some rows and skip others), so a batch whose results don't fit on
        # one page is split in half instead of paged.
        params = [("cycle", year), ("min_receipt_date", f"{year}-04-01"),
                  ("max_receipt_date", cutoff), ("per_page", 100)] + [("committee_id", c) for c in chunk]
        d = get(params, RAW / f"rep_{year}_{cutoff}_{chunk[0]}_{chunk[-1]}_{len(chunk)}.json", refresh)
        if d["pagination"]["count"] > 100:
            fetch(chunk[:len(chunk) // 2])
            fetch(chunk[len(chunk) // 2:])
        else:
            rows.extend(d["results"])

    for i in range(0, len(committees), 90):
        fetch(committees[i:i + 90])
    df = pd.DataFrame(rows)
    assert df["file_number"].is_unique, "FEC pages overlapped"
    df = df[(df["report_year"] == year) & (df["report_type"] != "TER")]
    # the latest period each campaign had reported by Sept 22 (its latest version, if amended)
    df = df.sort_values(["coverage_end_date", "receipt_date"]).groupby("committee_id").tail(1)
    df["money"] = df["cash_on_hand_end_period"].fillna(0).astype(float) + df["total_disbursements_ytd"].fillna(0).astype(float)
    return df[["committee_id", "money", "coverage_end_date", "receipt_date"]]


def build(year: int, refresh: bool = False, cutoff: str | None = None) -> pd.DataFrame:
    nom = match(nominees(year), candidates(year), year)
    rep = q2_reports(year, nom["committee_id"].tolist(), refresh and year == 2026, cutoff)
    nom = nom.merge(rep, on="committee_id", how="left")
    # No committee at all: never raised the $5,000 that requires one -> $0. A committee with no
    # report on file (e.g. a new Senate committee the FEC hasn't processed yet) -> unknown.
    nom.loc[nom["committee_id"].isna(), "money"] = 0.0
    k = ["office", "state_po", "district", "special"]
    g = nom.groupby(k + ["side"]).agg(money=("money", lambda x: x.max(skipna=False) if x.notna().any() else np.nan), name=("name", "first"),
                                      found=("committee_id", lambda s: s.notna().any())).unstack("side")
    out = pd.DataFrame({"dem_name": g[("name", "D")], "rep_name": g[("name", "R")],
                        "dem_money": g[("money", "D")], "rep_money": g[("money", "R")],
                        "dem_found": g[("found", "D")], "rep_found": g[("found", "R")]}).reset_index()
    out["money_log_ratio"] = np.log((out["dem_money"] + FLOOR) / (out["rep_money"] + FLOOR))
    return out.assign(year=year)


def update_current(asof: pd.Timestamp, refresh: bool = True) -> None:
    """Daily run: 2026 money from every report filed by the forecast date (e.g. the Oct 15
    quarterly once it's in); past years stay as of Sept 22."""
    cutoff = min(asof, pd.Timestamp("2026-11-03")).strftime("%Y-%m-%d")
    cur = build(2026, refresh, cutoff)
    path = PROC / "fec_money.csv"
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=cur.columns)
    pd.concat([old[old["year"] != 2026], cur], ignore_index=True).to_csv(path, index=False)
    print(f"2026 money as of reports filed by {cutoff}: {cur['money_log_ratio'].notna().sum()} races")


def main() -> None:
    refresh = "--refresh" in sys.argv
    frames = []
    for y in YEARS:
        df = build(y, refresh)
        both = df["dem_name"].notna() & df["rep_name"].notna()
        found = (df.loc[both, "dem_found"].astype(bool) & df.loc[both, "rep_found"].astype(bool)).mean()
        print(f"{y}: {both.sum()} D-vs-R races, both committees found in {found:.0%}", flush=True)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(PROC / "fec_money.csv", index=False)
    print("wrote", PROC / "fec_money.csv")


if __name__ == "__main__":
    main()
