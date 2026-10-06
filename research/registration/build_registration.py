"""Build county- and district-level party registration tables from the raw official files.

TEST ONLY (registration research). Reads data/raw/registration/**, writes CSVs next to this script:
  county_registration.csv   state, fips, county, year, dem, rep, total
  cd_registration.csv       state, year, district, dem, rep, total   (FL, CA, CO)

Definitions (kept consistent within a state over time, which is what a state-by-cycle
fixed-effects design needs):
  FL  bookclosing, active registrants, general election
  CA  15-day Report of Registration (active registrants), general election
  NC  SBE voter_stats on general election day (stats_type == 'voter'; all statuses in file)
  IA  monthly report nearest before election (Nov 1 of the year), active registrants
  CO  November statistics, active registrants
  PA  general-election registration statistics (all registrants as published)
"""
import re
import glob
import zipfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "registration"
OUT = Path(__file__).resolve().parent


def norm(s):
    s = str(s).upper().strip()
    s = s.replace("SAINT ", "ST ").replace("ST. ", "ST ")
    s = re.sub(r"\bCOUNTY\b", "", s)
    s = re.sub(r"[^A-Z]", "", s)
    return {"DADE": "MIAMIDADE", "LACKWANNA": "LACKAWANNA"}.get(s, s)


pres = pd.read_csv(ROOT / "data/raw/medsl/countypres_2000-2024.csv", dtype={"county_fips": str})
pres = pres[pres.year >= 2008]
FIPS = {}
for (st, nm, f) in pres[["state_po", "county_name", "county_fips"]].drop_duplicates().itertuples(index=False):
    if isinstance(f, str) and f.strip():
        FIPS[(st, norm(nm))] = f.zfill(5)


def tonum(x):
    if isinstance(x, str):
        x = x.replace(",", "").strip()
        if x in ("", "-"):
            return np.nan
    try:
        return float(x)
    except Exception:
        return np.nan


rows = []


def add(st, county, year, dem, rep, total):
    key = (st, norm(county))
    if key not in FIPS:
        raise KeyError(f"no fips for {key}")
    rows.append(dict(state=st, fips=FIPS[key], county=str(county).strip(), year=year,
                     dem=float(dem), rep=float(rep), total=float(total)))


# ---------------------------------------------------------------- Florida
FL_CODES = dict(ALA="Alachua", BAK="Baker", BAY="Bay", BRA="Bradford", BRE="Brevard", BRO="Broward",
                CAL="Calhoun", CHA="Charlotte", CIT="Citrus", CLA="Clay", CLL="Collier", CLM="Columbia",
                DAD="Miami-Dade", DES="DeSoto", DIX="Dixie", DUV="Duval", ESC="Escambia", FLA="Flagler",
                FRA="Franklin", GAD="Gadsden", GIL="Gilchrist", GLA="Glades", GUL="Gulf", HAM="Hamilton",
                HAR="Hardee", HEN="Hendry", HER="Hernando", HIG="Highlands", HIL="Hillsborough",
                HOL="Holmes", IND="Indian River", JAC="Jackson", JEF="Jefferson", LAF="Lafayette",
                LAK="Lake", LEE="Lee", LEO="Leon", LEV="Levy", LIB="Liberty", MAD="Madison",
                MAN="Manatee", MRN="Marion", MRT="Martin", MON="Monroe", NAS="Nassau", OKA="Okaloosa",
                OKE="Okeechobee", ORA="Orange", OSC="Osceola", PAL="Palm Beach", PAS="Pasco",
                PIN="Pinellas", POL="Polk", PUT="Putnam", SAN="Santa Rosa", SAR="Sarasota",
                SEM="Seminole", STJ="St. Johns", STL="St. Lucie", SUM="Sumter", SUW="Suwannee",
                TAY="Taylor", UNI="Union", VOL="Volusia", WAK="Wakulla", WAL="Walton", WAS="Washington")


def fl_table(path):
    """Return list of (label, dem, rep, total) from a FL bookclosing party sheet."""
    v = pd.read_excel(path, header=None)
    hdr = None
    for i in range(min(15, len(v))):
        cells = [str(c).strip().upper() for c in v.iloc[i].tolist()]
        if any(c in ("REP", "REPUBLICAN") or c.startswith("REPUBLICAN") for c in cells) and any(
                c in ("TOTAL",) for c in cells):
            hdr = i
            break
    cells = [str(c).strip().upper() for c in v.iloc[hdr].tolist()]
    ci_r = next(j for j, c in enumerate(cells) if c == "REP" or c.startswith("REPUBLICAN"))
    ci_d = next(j for j, c in enumerate(cells) if c == "DEM" or c.startswith("DEMOCRAT") or c.startswith("FLORIDA DEMOCRAT"))
    ci_t = next(j for j, c in enumerate(cells) if c == "TOTAL")
    out = []
    for i in range(hdr + 1, len(v)):
        r = v.iloc[i].tolist()
        labels = [str(c).strip() for c in r[:max(ci_r, 5)] if isinstance(c, str) and str(c).strip()]
        # label = first string cell that is not a date / ALL
        lab = next((c for c in labels if c.upper() not in ("ALL",) and not re.match(r"\d{4}-", c)), None)
        d, rp, t = tonum(r[ci_d]), tonum(r[ci_r]), tonum(r[ci_t])
        if lab is None or np.isnan(t) or np.isnan(d):
            # older .xls files have the numbers shifted one column right of the header (blank col)
            d2, r2, t2 = (tonum(r[ci_d + 1]) if ci_d + 1 < len(r) else np.nan,
                          tonum(r[ci_r + 1]) if ci_r + 1 < len(r) else np.nan,
                          tonum(r[ci_t + 1]) if ci_t + 1 < len(r) else np.nan)
            if lab is not None and not np.isnan(t2):
                d, rp, t = d2, r2, t2
            else:
                continue
        out.append((lab, d, rp, t))
    return out


FL_COUNTY = {2008: "fl/arch/2008genParty.xls", 2010: "fl/arch/gen2010_countyparty.xls",
             2012: "fl/arch/2012 GEN/gen2012_countyparty.xls", 2014: "fl/arch/2014_GEN/gen2014_countyparty.xls",
             2016: "fl/2016_county.xlsx", 2018: "fl/2018_county.xlsx", 2020: "fl/2020_county.xlsx",
             2022: "fl/2022_county.xlsx", 2024: "fl/2024_county.xlsx"}


def fl_old(path):
    """2008-2012 xls: row label in col 0 (3-letter code), header row has codes offset."""
    v = pd.read_excel(path, header=None)
    hdr = next(i for i in range(15) if "REP" in [str(c).strip() for c in v.iloc[i].tolist()])
    h = [str(c).strip() for c in v.iloc[hdr].tolist()]
    names = [c for c in h if c not in ("nan", "NaT")]
    out, seen = [], set()
    for i in range(hdr + 1, len(v)):
        r = v.iloc[i].tolist()
        code = str(r[0]).strip()
        if code not in FL_CODES or code in seen:
            continue
        nums = [tonum(c) for c in r[1:]]
        nums = [x for x in nums if not np.isnan(x)]
        if len(nums) < len(names):
            continue  # precinct-count page
        nums = nums[:len(names)]
        rec = dict(zip(names, nums))
        seen.add(code)
        out.append((FL_CODES[code], rec["DEM"], rec["REP"], rec["Total"]))
    return out


for y, p in FL_COUNTY.items():
    tab = fl_old(RAW / p) if y <= 2012 else fl_table(RAW / p)
    n = 0
    for lab, d, r, t in tab:
        if lab.strip().upper() in ("TOTAL", "TOTALS"):
            continue
        add("FL", lab, y, d, r, t)
        n += 1
    assert n == 67, (y, n)

# ---------------------------------------------------------------- California
CA_COUNTY = {2010: "ca/2010_county.xls", 2012: "ca/2012_county.xls", 2014: "ca/2014_county.xls",
             2016: "ca/2016_county.xls", 2018: "ca/2018_county.xlsx", 2020: "ca/2020_county.xlsx",
             2022: "ca/2022_county.xlsx", 2024: "ca/2024_county.xlsx"}


def firststr(r):
    return next((str(c).strip() for c in r if isinstance(c, str) and str(c).strip()), "nan")


def ca_cols(v):
    for i in range(6):
        cells = [" ".join(str(c).split()).lower() for c in v.iloc[i].tolist()]
        if any(c.startswith("democratic") for c in cells):
            cd = next(j for j, c in enumerate(cells) if c.startswith("democratic"))
            cr = next(j for j, c in enumerate(cells) if c.startswith("republican"))
            ct = next(j for j, c in enumerate(cells) if c.startswith("registered") or c.startswith("total reg"))
            return i, cd, cr, ct
    raise ValueError


for y, p in CA_COUNTY.items():
    v = pd.read_excel(RAW / p, header=None)
    h, cd, cr, ct = ca_cols(v)
    n = 0
    for i in range(h + 1, len(v)):
        lab = firststr(v.iloc[i].tolist())
        if lab in ("nan", "Percent") or "Total" in lab or lab.startswith("Percent"):
            continue
        t = tonum(v.iat[i, ct])
        if np.isnan(t):
            continue
        add("CA", lab, y, tonum(v.iat[i, cd]), tonum(v.iat[i, cr]), t)
        n += 1
    assert n == 58, (y, n)

# ---------------------------------------------------------------- North Carolina
for z in sorted(glob.glob(str(RAW / "nc" / "voter_stats_*.zip"))):
    y = int(Path(z).stem[-8:-4])
    with zipfile.ZipFile(z) as zf:
        name = zf.namelist()[0]
        d = pd.read_csv(zf.open(name), sep="\t", usecols=["county_desc", "party_cd", "total_voters", "stats_type"],
                        dtype={"party_cd": str}, encoding="latin-1")
    d = d[d.stats_type.astype(str).str.strip().str.lower() == "voter"]
    d["party_cd"] = d.party_cd.str.strip()
    g = d.groupby(["county_desc", "party_cd"]).total_voters.sum().unstack(fill_value=0)
    for c, r in g.iterrows():
        add("NC", c, y, r.get("DEM", 0), r.get("REP", 0), r.sum())
    assert len(g) == 100, (y, len(g))

# ---------------------------------------------------------------- Iowa
ia = pd.read_csv(RAW / "ia" / "state_of_iowa_monthly_voter_registration_totals_by_county_1013_rows.csv")
ia["report_date"] = pd.to_datetime(ia.report_date)
for y in range(2008, 2025, 2):
    s = ia[ia.report_date == pd.Timestamp(f"{y}-11-01")]
    assert len(s) == 99, (y, len(s))
    for r in s.itertuples():
        add("IA", r.county, y, r.dem_active, r.rep_active, r.total_active)

# ---------------------------------------------------------------- Colorado
CO_FILES = {2010: "co/2010_NovemberStatistics.xls", 2012: "co/2012_NovemberStatistics.xls",
            2014: "co/2014_NovemberStatistics.xls", 2016: "co/2016_NovemberStatistics.xlsx",
            2018: "co/2018_NovemberStatistics.xlsx", 2020: "co/2020_NovemberStatistics.xlsx",
            2022: "co/2022_NovemberStatistics.xlsx", 2024: "co/2024_20241101statistics.xlsx"}


def co_parse(v, label_cols):
    """Active-block DEM, REP and Active Total by position. Party-code row = first row containing DEM."""
    pr = next(i for i in range(6) if "DEM" in [str(c).strip() for c in v.iloc[i].tolist()])
    codes = [str(c).strip() for c in v.iloc[pr].tolist()]
    cd = codes.index("DEM")
    cr = codes.index("REP")
    tot = None
    for i in range(max(0, pr - 1), pr + 1):
        cells = [str(c).strip().lower() for c in v.iloc[i].tolist()]
        for j, c in enumerate(cells):
            if c.startswith("active total") or c == "active total":
                tot = j
                break
        if tot is not None:
            break
    out = []
    for i in range(pr + 1, len(v)):
        labs = [str(v.iat[i, j]).strip() for j in label_cols]
        t = tonum(v.iat[i, tot])
        if any(l in ("nan", "") for l in labs) or np.isnan(t):
            continue
        out.append((*labs, np.nan_to_num(tonum(v.iat[i, cd])), np.nan_to_num(tonum(v.iat[i, cr])), t))
    return out


for y, p in CO_FILES.items():
    v = pd.read_excel(RAW / p, header=None, sheet_name="Party & Status")
    n = 0
    for lab, d, r, t in co_parse(v, [0]):
        if lab.lower().startswith("total") or lab.lower().startswith("end"):
            continue
        add("CO", lab, y, d, r, t)
        n += 1
    assert n == 64, (y, n)

# ---------------------------------------------------------------- Pennsylvania
import pdfplumber

line_re = re.compile(r"^([A-Za-z][A-Za-z .']+?)\s+((?:[\d,]+\s+){2,6}[\d,]+)\s*$")
for p in sorted(glob.glob(str(RAW / "pa" / "pa_*.pdf"))):
    y = int(Path(p).stem[-4:])
    seen = {}
    rep_first = None  # column order differs by year (2012, 2014 list Republican first)
    with pdfplumber.open(p) as pdf:
        for pg in pdf.pages:
            for ln in (pg.extract_text() or "").split("\n"):
                lo = ln.lower()
                if rep_first is None and "democratic" in lo and "republican" in lo:
                    rep_first = lo.index("republican") < lo.index("democratic")
                m = line_re.match(ln.strip())
                if not m:
                    continue
                nm = m.group(1).strip()
                if nm.lower().startswith("total") or ("PA", norm(nm)) not in FIPS:
                    continue
                nums = [tonum(x) for x in m.group(2).split()]
                d_, r_ = (nums[1], nums[0]) if rep_first else (nums[0], nums[1])
                seen.setdefault(nm, (d_, r_, nums[-1]))
    for nm, (d, r, t) in seen.items():
        add("PA", nm, y, d, r, t)
    assert len(seen) == 67, (y, len(seen), sorted(seen)[:5])

reg = pd.DataFrame(rows)
assert not reg.duplicated(["state", "fips", "year"]).any()
assert (reg.dem + reg.rep <= reg.total * 1.0001).all(), reg[reg.dem + reg.rep > reg.total]
reg.to_csv(OUT / "county_registration.csv", index=False)
print(reg.groupby(["state", "year"]).agg(n=("fips", "size"), dem=("dem", "sum"), rep=("rep", "sum"),
                                         total=("total", "sum")).astype(int).to_string())

# ================================================================ congressional districts
cd_rows = []


def cadd(st, y, dist, d, r, t):
    cd_rows.append(dict(state=st, year=y, district=int(dist), dem=float(d), rep=float(r), total=float(t)))


# Florida CD files: a row per district (2016+) or per county-within-district (older).
FL_CD = {2010: "fl/arch/gen2010_countypartycongdist.xls", 2012: "fl/arch/2012 GEN/gen2012_countypartycongdist.xls",
         2014: "fl/arch/2014_GEN/gen2014_countypartycongdist.xls", 2016: "fl/2016_cd.xlsx", 2018: "fl/2018_cd.xlsx",
         2020: "fl/2020_cd.xlsx", 2022: "fl/2022_cd.xlsx", 2024: "fl/2024_cd.xlsx"}
FL_CD_LOG = {}
for y, p in FL_CD.items():
    v = pd.read_excel(RAW / p, header=None)
    acc = {}
    if y <= 2012:
        # "Congressional District N" block headers, county rows, then a "Total" row: REP, DEM, ..., Total
        cur = None
        for i in range(len(v)):
            r = [c for c in v.iloc[i].tolist() if str(c) not in ("nan", "NaT")]
            if not r:
                continue
            m = re.match(r"Congressional District\s+(\d+)", str(r[0]))
            if m:
                cur = int(m.group(1))
            elif str(r[0]).strip() == "Total" and cur is not None and cur not in acc:
                nums = [tonum(c) for c in r[1:]]
                acc[cur] = [nums[1], nums[0], nums[-1]]
    else:
        hdr = next(i for i in range(15) if any(str(c).strip().upper().startswith("REPUBLICAN")
                                               for c in v.iloc[i].tolist()))
        cells = [" ".join(str(c).split()).upper() for c in v.iloc[hdr].tolist()]
        ci_j = next(j for j, c in enumerate(cells) if c.startswith("JURIS") and c != "JURISTYPE")
        ci_r = next(j for j, c in enumerate(cells) if c.startswith("REPUBLICAN"))
        ci_d = next(j for j, c in enumerate(cells) if c.startswith("DEMOCRAT") or c.startswith("FLORIDA DEMOCRAT"))
        ci_t = next(j for j, c in enumerate(cells) if c == "TOTAL")
        for i in range(hdr + 1, len(v)):
            k, t = tonum(v.iat[i, ci_j]), tonum(v.iat[i, ci_t])
            if np.isnan(k) or np.isnan(t):
                continue
            a = acc.setdefault(int(k), [0, 0, 0])
            a[0] += tonum(v.iat[i, ci_d]); a[1] += tonum(v.iat[i, ci_r]); a[2] += t
    FL_CD_LOG[y] = len(acc)
    for k, (d, rp, t) in acc.items():
        cadd("FL", y, k, d, rp, t)

# California CD files: county rows inside "US Congressional N" blocks; sum them.
CA_CD = {2010: "ca/2010_cd.xls", 2012: "ca/2012_cd.xls", 2014: "ca/2014_cd.xls", 2016: "ca/2016_cd.xls",
         2018: "ca/2018_cd.xlsx", 2020: "ca/2020_cd.xlsx", 2022: "ca/2022_cd.xlsx", 2024: "ca/2024_cd.xlsx"}
for y, p in CA_CD.items():
    v = pd.read_excel(RAW / p, header=None)
    h = next(i for i in range(6) if any(str(c).strip().lower().startswith("democratic") for c in v.iloc[i].tolist()))
    cells = [" ".join(str(c).split()).lower() for c in v.iloc[h].tolist()]
    cd = next(j for j, c in enumerate(cells) if c.startswith("democratic"))
    cr = next(j for j, c in enumerate(cells) if c.startswith("republican"))
    ct = next(j for j, c in enumerate(cells) if c.startswith("total reg") or c.startswith("registered"))
    cur, acc = None, {}
    for i in range(len(v)):
        lab = firststr(v.iloc[i].tolist())
        m = re.match(r"US Congressional\s+(\d+)", lab)
        if m:
            cur = int(m.group(1))
            continue
        if cur is None or lab in ("nan",) or "Total" in lab or lab.startswith("Percent"):
            continue
        t = tonum(v.iat[i, ct])
        if np.isnan(t):
            continue
        a = acc.setdefault(cur, [0, 0, 0])
        a[0] += tonum(v.iat[i, cd]); a[1] += tonum(v.iat[i, cr]); a[2] += t
    for k, (d, r, t) in acc.items():
        cadd("CA", y, k, d, r, t)

# Colorado CD sheet: rows "CD n | County" plus "CD n | Total" (2024) or unlabeled subtotal rows.
for y, p in CO_FILES.items():
    v = pd.read_excel(RAW / p, header=None, sheet_name="Congressional Districts")
    acc = {}
    for dist, county, d, r, t in co_parse(v, [0, 1]):
        m = re.match(r"CD\s*(\d+)", dist)
        if not m or county.lower().startswith("total") or tonum(county) == tonum(county):
            continue  # skip subtotal rows (county cell numeric) and Total rows
        a = acc.setdefault(int(m.group(1)), [0, 0, 0])
        a[0] += d; a[1] += r; a[2] += t
    for k, (d, r, t) in acc.items():
        cadd("CO", y, k, d, r, t)

cdr = pd.DataFrame(cd_rows)
cdr.to_csv(OUT / "cd_registration.csv", index=False)
chk = cdr.groupby(["state", "year"]).agg(n=("district", "size"), dem=("dem", "sum"), rep=("rep", "sum"),
                                         total=("total", "sum")).astype(int)
st = reg.groupby(["state", "year"])[["dem", "rep", "total"]].sum().astype(int)
print(chk.join(st, rsuffix="_cty").to_string())
print("FL CD header rows:", FL_CD_LOG)
