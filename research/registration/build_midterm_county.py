"""County-level two-party results for 2018 and 2022 Senate/Governor races in the six registration states,
aggregated from MEDSL precinct files already on disk. TEST ONLY. Writes county_midterm_results.csv."""
import io
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = Path(__file__).resolve().parent
STATES = ["FL", "CA", "NC", "IA", "CO", "PA"]
USE = ["office", "party_simplified", "mode", "votes", "county_fips", "state_po", "stage", "special", "writein"]


def collapse(d, year):
    d = d[d.state_po.isin(STATES) & d.office.isin(["US SENATE", "GOVERNOR"])]
    d = d[(d.stage.astype(str).str.upper() == "GEN") & (d.special.astype(str).str.upper() != "TRUE")]
    d = d[d.party_simplified.isin(["DEMOCRAT", "REPUBLICAN"])]
    d = d.assign(votes=pd.to_numeric(d.votes, errors="coerce").fillna(0),
                 county_fips=d.county_fips.astype(str).str.split(".").str[0].str.zfill(5))
    # if a county reports a TOTAL mode, use it; otherwise sum the vote modes
    has_total = d[d["mode"].astype(str).str.upper() == "TOTAL"].groupby(["state_po", "office", "county_fips"]).size()
    key = list(zip(d.state_po, d.office, d.county_fips))
    ht = set(has_total.index)
    keep = [(k in ht) == (str(m).upper() == "TOTAL") for k, m in zip(key, d["mode"])]
    d = d[keep]
    g = d.groupby(["state_po", "office", "county_fips", "party_simplified"]).votes.sum().unstack(fill_value=0)
    g = g.rename(columns={"DEMOCRAT": "dem", "REPUBLICAN": "rep"}).reset_index()
    g["year"] = year
    return g


parts = []
# 2022: per-state files (despite the "local" name they contain all offices)
for st in STATES:
    z = RAW / "medsl_2022" / f"2022-{st.lower()}-local-precinct-general.zip"
    with zipfile.ZipFile(z) as zf:
        raw = zf.read(zf.namelist()[0])
    d = pd.read_csv(io.BytesIO(raw), usecols=lambda c: c in USE, dtype=str, encoding="latin-1")
    parts.append(collapse(d, 2022))
    print("2022", st, flush=True)

# 2018 Senate
with zipfile.ZipFile(RAW / "medsl_2018" / "SENATE_precinct_general.zip") as zf:
    d = pd.read_csv(zf.open(zf.namelist()[0]), usecols=lambda c: c in USE, dtype=str, encoding="latin-1")
parts.append(collapse(d, 2018))
print("2018 senate", flush=True)

# 2018 Governor: stream the 1.9 GB statewide-offices file
with zipfile.ZipFile(RAW / "medsl_2018" / "STATE_precinct_general.zip") as zf:
    acc = []
    for ch in pd.read_csv(zf.open(zf.namelist()[0]), usecols=lambda c: c in USE, dtype=str,
                          encoding="latin-1", chunksize=2_000_000):
        ch = ch[ch.state_po.isin(STATES) & (ch.office == "GOVERNOR")]
        if len(ch):
            acc.append(ch)
    parts.append(collapse(pd.concat(acc), 2018))
print("2018 governor", flush=True)

out = pd.concat(parts, ignore_index=True)
out = out[(out.dem > 0) & (out.rep > 0)]
out.to_csv(OUT / "county_midterm_results.csv", index=False)
print(out.groupby(["year", "state_po", "office"]).agg(n=("county_fips", "size"), dem=("dem", "sum"),
                                                       rep=("rep", "sum")).to_string())
