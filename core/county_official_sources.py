"""County results from official sources, for statewide races neither MEDSL's files nor Wikipedia's tables cover
cleanly. Used by core/build_county_results.py (display on the site's Past results page; not a model input).

  data/raw/official_2020/XX_tabular.tsv   "US 2020 General Official Election Results in Tabular Format"
      (Harvard Dataverse, doi:10.7910/DVN/RV80FW, CC0): every contest by county, from state results files.
      Used for the 2020 Senate races in Georgia (both), Illinois, Kentucky, Louisiana and North Carolina, and
      North Carolina's governor. Wikipedia has no county table for several of these, and for Georgia's
      special and Louisiana's all-party ballots its tables lump minor candidates of a party together.
  data/raw/openelections_ks_2020/          OpenElections (github.com/openelections/openelections-data-ks):
      Kansas 2020 precinct results, one file per county (the Harvard file for Kansas has no U.S. Senate race).
  data/raw/la_sos/20191116_governor_by_parish.csv   Louisiana Secretary of State, 2019 governor runoff by
      parish (voterportal.sos.la.gov results download).

On all-party ballots (Georgia's 2020 special, Louisiana) each party's candidates are added up, as MEDSL does.
"""
from pathlib import Path
import re

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
KEY = ["year", "state_po", "county_fips", "office", "special"]


def _fips(state_name: str) -> dict:
    from wiki_county_patch import _county_fips_lookup, _norm  # noqa: F401
    lk = _county_fips_lookup()
    lk = lk[lk["state_name"].str.upper() == state_name.upper()]
    return dict(zip(lk["key"], lk["county_fips"]))


def _match(names: pd.Series, state_name: str) -> pd.Series:
    from wiki_county_patch import _norm
    by = _fips(state_name)
    keys = names.map(_norm)
    out = keys.map(by)
    out = out.fillna((keys + "city").map(by))
    missing = sorted(set(names[out.isna()]))
    if missing:
        raise ValueError(f"{state_name}: unmatched counties {missing[:8]}")
    return out.astype(int)


def official_2020() -> pd.DataFrame:
    parts = []
    for f in sorted((RAW / "official_2020").glob("*_tabular.tsv")):
        d = pd.read_csv(f, sep="\t")
        d = d[d["VoteType"] == "total"]
        for contest, g in d.groupby("Contest"):
            m = re.match(r"US Senate (\w\w)( \(partial term\))?$", contest) or re.match(r"(NC) Governor$", contest)
            if not m:
                continue
            st, office = m.group(1), "GOV" if contest.endswith("Governor") else "SEN"
            special = bool(m.lastindex and m.lastindex >= 2 and m.group(2))
            state_name, county = g["ReportingUnit"].str.split(";", n=1).str[0], g["ReportingUnit"].str.split(";", n=1).str[1]
            g = g.assign(county=county, side=g["Party"].map({"Democratic Party": "dem", "Republican Party": "rep"}))
            wide = g.pivot_table(index="county", columns="side", values="Count", aggfunc="sum", fill_value=0)
            wide["total"] = g.groupby("county")["Count"].sum()
            wide = wide.reset_index()
            wide["county_fips"] = _match(wide["county"], state_name.iloc[0])
            parts.append(wide.assign(year=2020, state_po=st, office=office, special=special)[KEY + ["dem", "rep", "total"]])
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=KEY + ["dem", "rep", "total"])


def kansas_2020() -> pd.DataFrame:
    files = sorted((RAW / "openelections_ks_2020").glob("*.csv"))
    if not files:
        return pd.DataFrame(columns=KEY + ["dem", "rep", "total"])
    d = pd.concat([pd.read_csv(f, dtype=str) for f in files], ignore_index=True)
    d = d[d["office"] == "U.S. Senate"].copy()
    d["votes"] = pd.to_numeric(d["votes"], errors="coerce").fillna(0)
    d["side"] = d["party"].map({"Democratic": "dem", "Republican": "rep"})
    wide = d.pivot_table(index="county", columns="side", values="votes", aggfunc="sum", fill_value=0)
    wide["total"] = d.groupby("county")["votes"].sum()
    wide = wide.reset_index()
    wide["county_fips"] = _match(wide["county"], "Kansas")
    return wide.assign(year=2020, state_po="KS", office="SEN", special=False)[KEY + ["dem", "rep", "total"]]


def louisiana_2019() -> pd.DataFrame:
    f = RAW / "la_sos" / "20191116_governor_by_parish.csv"
    if not f.exists():
        return pd.DataFrame(columns=KEY + ["dem", "rep", "total"])
    d = pd.read_csv(f)
    dem = [c for c in d.columns if "(DEM)" in c]
    rep = [c for c in d.columns if "(REP)" in c]
    votes = [c for c in d.columns if c not in ("Office", "Parish")]
    out = pd.DataFrame({"dem": d[dem].sum(axis=1), "rep": d[rep].sum(axis=1), "total": d[votes].sum(axis=1)})
    out["county_fips"] = _match(d["Parish"], "Louisiana")
    return out.assign(year=2019, state_po="LA", office="GOV", special=False)[KEY + ["dem", "rep", "total"]]


def all_official() -> pd.DataFrame:
    return pd.concat([official_2020(), kansas_2020(), louisiana_2019()], ignore_index=True)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT / "core"))
    o = all_official()
    g = o.groupby(["year", "state_po", "office", "special"])[["dem", "rep", "total"]].sum()
    g["margin"] = (100 * (g.dem - g.rep) / (g.dem + g.rep)).round(2)
    print(g.to_string())
