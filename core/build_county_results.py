"""Build a single county-level results table for statewide races.

Output: data/processed/county_results.parquet with one row per
(year, state_po, county_fips, office, special) and columns dem, rep, total.

Sources (all in data/raw/):
  - medsl/countypres_2000-2024.csv  MEDSL county presidential results
  - medsl_2018/         MEDSL precinct returns (US Senate, statewide offices)
  - medsl_2022/         MEDSL precinct returns, one zip per state
  - medsl_2024/         MEDSL county-level US Senate returns

Why statewide races only: every county has a contested race at the top of
the ticket, so turnout comparisons are never distorted by an uncontested
House seat.
"""
from pathlib import Path
import zipfile

import pandas as pd

from wiki_county_patch import all_patches

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "county_results.parquet"

KEEP_OFFICES = {"US PRESIDENT": "PRES", "US SENATE": "SEN", "GOVERNOR": "GOV", "GOVERNOR/LIEUTENANT GOVERNOR": "GOV"}
# States whose "TOTAL" mode is really just one mode (election day), so every
# mode must be summed. Found by validating against official statewide totals.
SUM_ALL_MODES = {(2022, "LA")}
NON_CANDIDATES = (r"OVERVOTE|UNDERVOTE|TOTAL VOTES|BLANK|SPOILED|REJECTED|FEDERAL BALLOTS|"
                  r"BALLOTS CAST|REGISTERED|PUBLIC COUNTER|AFFIDAVIT|ABSENTEE|EMERGENCY|MANUALLY")
USECOLS = ["precinct", "office", "candidate", "party_detailed", "party_simplified", "mode", "votes", "county_fips",
           "state_po", "year", "stage", "special", "writein"]


def _collapse_precincts(df: pd.DataFrame) -> pd.DataFrame:
    """Precinct rows -> county totals for DEM, REP, and all candidates."""
    df = df.assign(office=df["office"].astype(str).str.upper().str.strip())
    df = df[df["office"].isin(KEEP_OFFICES) & (df["stage"].str.upper() == "GEN")].copy()
    df["office"] = df["office"].map(KEEP_OFFICES)
    # Drop bookkeeping rows (overvotes, undervotes, ballot counters) that some
    # states report as if they were candidates; they would inflate turnout.
    cand = df["candidate"].astype(str).str.upper()
    df = df[~cand.str.contains(NON_CANDIDATES)]
    df["votes"] = pd.to_numeric(df["votes"], errors="coerce").fillna(0)
    df["county_fips"] = pd.to_numeric(df["county_fips"], errors="coerce")
    df = df.dropna(subset=["county_fips"])
    df["special"] = df["special"].astype(str).str.upper().eq("TRUE")
    # Rescue major-party labels MEDSL files under OTHER: North Dakota's
    # "Democratic-NPL", Washington's "GOP" / "Prefers Republican Party".
    if "party_detailed" in df:
        det = df["party_detailed"].astype(str).str.upper()
        other = ~df["party_simplified"].isin(["DEMOCRAT", "REPUBLICAN"])
        df.loc[other & det.str.contains("DEMOCRAT"), "party_simplified"] = "DEMOCRAT"
        df.loc[other & det.str.contains(r"REPUBLICAN|^GOP$"), "party_simplified"] = "REPUBLICAN"
    key = ["year", "state_po", "county_fips", "office", "special"]

    # Some files add "COUNTY TOTAL" pseudo-precincts on top of real precincts.
    if "precinct" in df:
        agg = df["precinct"].astype(str).str.upper().str.contains(r"^COUNTY TOTAL|^TOTAL$")
        has_real = (~agg).groupby([df[k] for k in key]).transform("any")
        df = df[~(agg & has_real)]

    # Some states report vote modes (early, mail, election day) separately AND
    # as a TOTAL row; others mix the two within a county. Per candidate, take
    # the larger of (TOTAL rows) and (sum of the other modes) so a vote is
    # never counted twice and a zero-filled TOTAL row never hides real votes.
    df["is_total"] = df["mode"].astype(str).str.upper().eq("TOTAL")
    sum_all = [(y, st) in SUM_ALL_MODES for y, st in zip(df["year"], df["state_po"])]
    df.loc[sum_all, "is_total"] = False
    df["cand"] = df["candidate"].astype(str).str.upper().str.strip()
    by_mode = (df.groupby(key + ["cand", "party_simplified", "is_total"], dropna=False)["votes"]
                 .sum().unstack("is_total", fill_value=0))
    df = by_mode.max(axis=1).rename("votes").reset_index()

    # Credit each candidate with ALL their ballot lines (NY/CT fusion voting:
    # a Democrat also running on the Working Families line). A candidate is
    # a "Democrat" if most of their major-party-line votes came on the DEM line;
    # jungle-primary states (LA) sum every candidate of the party.
    race = ["year", "state_po", "office", "special"]
    line = df.groupby(race + ["cand", "party_simplified"])["votes"].sum().unstack(fill_value=0)
    for col in ("DEMOCRAT", "REPUBLICAN"):
        if col not in line:
            line[col] = 0
    major = line[["DEMOCRAT", "REPUBLICAN"]]
    side = major.idxmax(axis=1).where(major.max(axis=1) > 0).rename("side").reset_index()
    df = df.merge(side, on=race + ["cand"], how="left")
    df["dem"] = df["votes"].where(df["side"].eq("DEMOCRAT"), 0)
    df["rep"] = df["votes"].where(df["side"].eq("REPUBLICAN"), 0)
    out = df.groupby(key, as_index=False)[["dem", "rep", "votes"]].sum()
    return out.rename(columns={"votes": "total"})


def load_2018() -> pd.DataFrame:
    parts = []
    for name in ["SENATE_precinct_general.zip", "STATE_precinct_general.zip"]:
        zf = zipfile.ZipFile(RAW / "medsl_2018" / name)
        csv = [n for n in zf.namelist() if n.endswith(".csv")][0]
        # The statewide-office file is ~2 GB, so stream it and keep only governor rows.
        for chunk in pd.read_csv(zf.open(csv), usecols=USECOLS, chunksize=1_000_000,
                                 low_memory=False, dtype={"county_fips": str}, encoding="latin-1"):
            parts.append(chunk[chunk["office"].astype(str).str.upper().isin(KEEP_OFFICES)])
    return _collapse_precincts(pd.concat(parts))


def load_2022() -> pd.DataFrame:
    parts = []
    for z in sorted((RAW / "medsl_2022").glob("*.zip")):
        zf = zipfile.ZipFile(z)
        for n in zf.namelist():
            if not n.endswith(".csv") or n.startswith("__MACOSX"):
                continue
            df = pd.read_csv(zf.open(n), usecols=lambda c: c in USECOLS, encoding="latin-1",
                             low_memory=False, dtype={"county_fips": str})
            parts.append(df[df["office"].astype(str).str.upper().isin(KEEP_OFFICES)])
    return _collapse_precincts(pd.concat(parts))


def load_2024_senate() -> pd.DataFrame:
    df = pd.read_csv(RAW / "medsl_2024" / "2024-senate-county.csv", dtype={"county_fips": str})
    return _collapse_precincts(df)


def load_president() -> pd.DataFrame:
    df = pd.read_csv(RAW / "medsl" / "countypres_2000-2024.csv", dtype={"county_fips": str})
    df = df.rename(columns={"party": "party_simplified", "candidatevotes": "votes"})
    df["office"] = "US PRESIDENT"
    df["stage"] = "GEN"
    df["special"] = False
    return _collapse_precincts(df)


def main() -> None:
    pres = load_president()
    stat = pd.concat([load_2024_senate(), load_2022(), load_2018()])
    # Races MEDSL lacks (or has only partially) are replaced wholesale by Wikipedia tables.
    patches = all_patches()
    patched = set(map(tuple, patches[["year", "state_po", "office", "special"]].drop_duplicates().values))
    keep = [tuple(r) not in patched for r in stat[["year", "state_po", "office", "special"]].values]
    stat = pd.concat([stat[keep], patches], ignore_index=True)
    stat = stat[stat["state_po"] != "DC"]  # DC "senator" rows are the non-voting shadow seat
    out = pd.concat([pres, stat], ignore_index=True)
    out["county_fips"] = out["county_fips"].astype(int)
    out["year"] = out["year"].astype(int)
    out = out[["year", "state_po", "county_fips", "office", "special", "dem", "rep", "total"]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(out.groupby(["year", "office"]).agg(counties=("county_fips", "nunique"),
                                             states=("state_po", "nunique"),
                                             total=("total", "sum")))


if __name__ == "__main__":
    main()
