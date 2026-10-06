"""ZIP code -> 2026 congressional district lookup (for "Enter your ZIP" on the site).

ZIP codes are mail routes, not areas, so we use the Census Bureau's ZIP Code
Tabulation Areas (ZCTAs, 2020 vintage), which are built from whole census
blocks. Every 2020 block sits in at most one ZCTA and (in a block assignment
file) in exactly one congressional district, so blocks are the common unit:

    share(zcta, state, district) = 2020 population of the ZCTA's blocks in that
                                   district / 2020 population of the ZCTA's
                                   blocks in that state

A ZCTA that crosses a state line gets rows in each state, each summing to 1.
A ZCTA (or its part in one state) with no 2020 residents falls back to block
land area (method = "area"; land plus water if it has no land either).

Sources (all official; raw files in data/raw/zip/, fetched by download()):
  - Block -> 2026 district
      * The nine states that redrew for 2026 (AL CA FL LA NC OH TN TX UT): the
        Census Bureau's 120th Congress block equivalency files (cd120.zip,
        published Aug 2026 from the plans states submitted through the
        Redistricting Data Program), cross-checked block by block against each
        state's own official block assignment file where one could be downloaded
        (see STATE_BAFS and check_state_bafs()).
      * Every other state: the Census 119th Congress block equivalency file
        (NationalCD119.txt in cd119.zip) -- the lines used in 2024. That includes
        Missouri, whose 2025 map is in Census's 120th file but was ruled out for
        November 2026 by the U.S. Supreme Court on Sept 25, 2026 (see STATE_BAFS).
  A district that touches a populated ZCTA only through empty blocks is left
  out (share 0). 156 water-only blocks that no district claims ("ZZ") are dropped.
  - Block -> ZCTA: Census 2020 relationship file tab20_zcta520_tabblock20_natl.txt
    (saved gzip-compressed; 1.06 GB uncompressed).
  - Block 2020 population: POP100 for summary level 750 (blocks) in each
    state's 2020 PL 94-171 redistricting-data geographic header. Only the
    geo-header member of each state zip is fetched (HTTP range requests), not the
    data segments. (The Census API now requires a key, so it is not used.)
  - ZCTA internal points: Census Gazetteer ZCTA file, 2026 vintage (the 2020
    Gazetteer still used the 2010-based ZCTAs; 2022 and later use ZCTA520).

Outputs
  data/processed/zip_districts_2026.csv   zcta, state_po, district (0 = at-large
                                           or DC's delegate), share, method
  data/processed/zcta_centroids.csv       zcta, lat, lon (Census internal point),
                                           pop2020, state_po (state with most of
                                           the ZCTA's people)

Run:  .venv/Scripts/python.exe core/build_zip_districts.py
      (downloads anything missing first; about 0.6 GB on a first run)
"""
from pathlib import Path
import gzip
import io
import shutil
import sys
import urllib.request
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "zip"
PLGEO = RAW / "pl_geo"
OUT = ROOT / "data" / "processed" / "zip_districts_2026.csv"
OUT_CENT = ROOT / "data" / "processed" / "zcta_centroids.csv"

CENSUS = "https://www2.census.gov"
FILES = {  # local name -> URL
    "tab20_zcta520_tabblock20_natl.txt.gz":
        f"{CENSUS}/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_tabblock20_natl.txt",
    "tab20_cd11920_zcta520_natl.txt":
        f"{CENSUS}/geo/docs/maps-data/data/rel2020/cd-sld/tab20_cd11920_zcta520_natl.txt",
    "cd119.zip": f"{CENSUS}/programs-surveys/decennial/rdo/mapping-files/2025/119-congressional-district-befs/cd119.zip",
    "cd120.zip": f"{CENSUS}/programs-surveys/decennial/rdo/mapping-files/2027/120-congressional-district-befs/cd120.zip",
    "CD120_BlockSplits.pdf":
        f"{CENSUS}/programs-surveys/decennial/rdo/mapping-files/2027/120-congressional-district-befs/CD120_BlockSplits.pdf",
    "2026_Gaz_zcta_national.zip": f"{CENSUS}/geo/docs/maps-data/data/gazetteer/2026_Gazetteer/2026_Gaz_zcta_national.zip",
    "2026_Gaz_120CDs_national.zip": f"{CENSUS}/geo/docs/maps-data/data/gazetteer/2026_Gazetteer/2026_Gaz_120CDs_national.zip",
}
PL_URL = f"{CENSUS}/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171"

REDRAWN_2026 = ["AL", "CA", "FL", "LA", "NC", "OH", "TN", "TX", "UT"]

# FIPS code, postal code, and folder name in the PL 94-171 directory
STATES = {
    "01": ("AL", "Alabama"), "02": ("AK", "Alaska"), "04": ("AZ", "Arizona"), "05": ("AR", "Arkansas"),
    "06": ("CA", "California"), "08": ("CO", "Colorado"), "09": ("CT", "Connecticut"), "10": ("DE", "Delaware"),
    "11": ("DC", "District_of_Columbia"), "12": ("FL", "Florida"), "13": ("GA", "Georgia"),
    "15": ("HI", "Hawaii"), "16": ("ID", "Idaho"), "17": ("IL", "Illinois"), "18": ("IN", "Indiana"),
    "19": ("IA", "Iowa"), "20": ("KS", "Kansas"), "21": ("KY", "Kentucky"), "22": ("LA", "Louisiana"),
    "23": ("ME", "Maine"), "24": ("MD", "Maryland"), "25": ("MA", "Massachusetts"), "26": ("MI", "Michigan"),
    "27": ("MN", "Minnesota"), "28": ("MS", "Mississippi"), "29": ("MO", "Missouri"), "30": ("MT", "Montana"),
    "31": ("NE", "Nebraska"), "32": ("NV", "Nevada"), "33": ("NH", "New_Hampshire"), "34": ("NJ", "New_Jersey"),
    "35": ("NM", "New_Mexico"), "36": ("NY", "New_York"), "37": ("NC", "North_Carolina"),
    "38": ("ND", "North_Dakota"), "39": ("OH", "Ohio"), "40": ("OK", "Oklahoma"), "41": ("OR", "Oregon"),
    "42": ("PA", "Pennsylvania"), "44": ("RI", "Rhode_Island"), "45": ("SC", "South_Carolina"),
    "46": ("SD", "South_Dakota"), "47": ("TN", "Tennessee"), "48": ("TX", "Texas"), "49": ("UT", "Utah"),
    "50": ("VT", "Vermont"), "51": ("VA", "Virginia"), "53": ("WA", "Washington"), "54": ("WV", "West_Virginia"),
    "55": ("WI", "Wisconsin"), "56": ("WY", "Wyoming")}
PO_TO_FIPS = {po: f for f, (po, _) in STATES.items()}


# ---------------------------------------------------------------- downloads

class RangeFile(io.RawIOBase):
    """Read-only, seekable view of a remote file via HTTP range requests, so
    zipfile can pull one member out of a large zip without downloading the rest."""

    def __init__(self, url, chunk=1 << 20):
        self.url, self.chunk, self.pos, self.cache = url, chunk, 0, {}
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as r:
            self.size = int(r.headers["Content-Length"])
        self.fetched = 0  # bytes actually transferred

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def _block(self, i):
        if i not in self.cache:
            lo = i * self.chunk
            hi = min(self.size, lo + self.chunk) - 1
            req = urllib.request.Request(self.url, headers={"Range": f"bytes={lo}-{hi}"})
            with urllib.request.urlopen(req) as r:
                self.cache = {i: r.read()}  # keep one block in memory
            self.fetched += hi - lo + 1
        return self.cache[i]

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        out = bytearray()
        while n > 0 and self.pos < self.size:
            i, o = divmod(self.pos, self.chunk)
            b = self._block(i)[o:o + n]
            out += b
            self.pos += len(b)
            n -= len(b)
        return bytes(out)


def fetch(url, dest):
    """Plain download. A .gz destination for a non-.gz URL asks the server for
    gzip transfer encoding and stores the compressed bytes as they arrive."""
    print(f"  downloading {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    gz = dest.suffix == ".gz" and not url.endswith(".gz")
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"} if gz else {})
    with urllib.request.urlopen(req) as r, open(tmp, "wb") as f:
        if gz and r.headers.get("Content-Encoding") != "gzip":
            with gzip.GzipFile(fileobj=f, mode="wb") as g:
                shutil.copyfileobj(r, g, 1 << 20)
        else:
            shutil.copyfileobj(r, f, 1 << 20)
    tmp.replace(dest)


def download():
    RAW.mkdir(parents=True, exist_ok=True)
    PLGEO.mkdir(exist_ok=True)
    for name, url in FILES.items():
        if not (RAW / name).exists():
            fetch(url, RAW / name)
    for url, name in STATE_BAFS.values():
        if not (RAW / "state_baf" / name).exists():
            (RAW / "state_baf").mkdir(exist_ok=True)
            fetch(url, RAW / "state_baf" / name)
    # block populations: the geo header of each state's PL 94-171 file
    for fips, (po, folder) in STATES.items():
        dest = PLGEO / f"{po.lower()}geo2020.pl.gz"
        if dest.exists():
            continue
        url = f"{PL_URL}/{folder}/{po.lower()}2020.pl.zip"
        rf = RangeFile(url)
        with zipfile.ZipFile(rf) as z:
            raw = z.read(f"{po.lower()}geo2020.pl")
        with gzip.open(dest.with_suffix(".part"), "wb") as g:
            g.write(raw)
        dest.with_suffix(".part").replace(dest)
        print(f"  {po}: geo header from {url} ({rf.fetched / 1e6:.1f} MB transferred)")


# Official state block assignment files for the 2026 plans, used to cross-check
# the Census 120th Congress files block by block: postal code -> (URL, local name).
#   TX  PLANC2333 (H.B. 4, 89th Leg. 2nd C.S., Aug 2025), Texas Legislative Council
#   CA  AB 604 (Ch. 96, Stats. 2025; adopted by Prop 50, Nov 2025), Assembly Elections Committee
#   FL  EOGPCRP2026 (HB 1-D, signed May 2026), Florida Senate
#   LA  Act 2 of the 2026 Regular Session (SB 121), Louisiana Legislature. Built on
#       the legislature's precinct-adjusted blocks, which the legislature says do
#       not exactly match 2020 Census blocks.
#   NC  S.L. 2025-95 (SB 249, Oct 2025), North Carolina General Assembly
#   OH  Ohio Redistricting Commission plan of Oct 31, 2025 (Excel BAF)
# No machine-readable official file was found for AL (2023 Livingston Plan 3,
# PDF descriptions only), TN (HB 7003, 2026; PDF/JPG maps only) or UT (court-
# ordered Map 1; the state GIS office posts shapes only), so those rest on the
# Census file alone. Missouri: Census's 120th file carries the 2025 HB 1 map,
# but the U.S. Supreme Court ruled on Sept 25, 2026 that the 2022 map governs
# November 2026 (the referendum on HB 1 is Proposition A), so Missouri stays
# on the 119th Congress lines here.
STATE_BAFS = {
    "TX": ("https://data.capitol.texas.gov/dataset/748c952b-e926-4f44-8d01-a738884b3ec8/resource/"
           "bc1ad997-3d59-40f7-8d7f-72a74bb4a5e4/download/planc2333_blk.zip", "TX_planc2333_blk.zip"),
    "CA": ("https://aelc.assembly.ca.gov/system/files/2025-08/ab604.csv", "CA_ab604.csv"),
    "FL": ("https://www.flsenate.gov/PublishedContent/Session/Congressional/EOGPCRP2026.txt", "FL_EOGPCRP2026.txt"),
    "LA": ("https://redist.legis.la.gov/2026_Files/Act2Congress/Block%20Equivalency%20File/"
           "Block%20Equlivancy%20File%20-%20Act%202%20(2026%20RS%20-%20Congress).txt",
           "LA_Act2_2026RS_Congress_BEF.txt"),
    "NC": ("https://webservices.ncleg.gov/ViewBillDocument/2025/7669/0/SL%202025-95%20-%20Block%20Assignment%20File",
           "NC_SL2025-95_BAF.zip"),
    "OH": ("https://redistricting.ohio.gov/api/public/districtmaps/430/download", "OH_2025-10-31_CD_BAF.zip"),
}


# ---------------------------------------------------------------- inputs

def block_population() -> pd.DataFrame:
    """block GEOID (15 digits) -> 2020 population, from the PL 94-171 geo headers.
    Pipe-delimited; field 3 is the summary level (750 = block), field 10 the
    block GEOID, and POP100 is the seventh field from the end."""
    parts = []
    for po, _ in STATES.values():
        with gzip.open(PLGEO / f"{po.lower()}geo2020.pl.gz", "rt", encoding="latin-1") as f:
            rows = [ln.split("|") for ln in f if ln[8:11] == "750"]
        parts.append(pd.DataFrame({"block": [r[9] for r in rows], "pop": [int(r[-7]) for r in rows]}))
    return pd.concat(parts, ignore_index=True)


def block_zcta() -> pd.DataFrame:
    """block -> ZCTA with the block's land/water area (blocks in no ZCTA dropped)."""
    r = pd.read_csv(RAW / "tab20_zcta520_tabblock20_natl.txt.gz", sep="|", dtype=str, encoding="utf-8-sig",
                    usecols=["GEOID_ZCTA5_20", "GEOID_TABBLOCK_20", "AREALAND_PART", "AREAWATER_PART"])
    r = r.rename(columns={"GEOID_ZCTA5_20": "zcta", "GEOID_TABBLOCK_20": "block",
                          "AREALAND_PART": "aland", "AREAWATER_PART": "awater"}).dropna(subset=["zcta"])
    r[["aland", "awater"]] = r[["aland", "awater"]].astype("int64")
    return r


def block_districts() -> pd.DataFrame:
    """block -> 2026 district: 120th Congress BEF for the redrawn states, 119th elsewhere."""
    with zipfile.ZipFile(RAW / "cd119.zip") as z:
        cd119 = pd.read_csv(z.open("NationalCD119.txt"), dtype=str)
    with zipfile.ZipFile(RAW / "cd120.zip") as z:
        cd120 = pd.read_csv(z.open("NationalCD120.txt"), dtype=str, usecols=["GEOID", "CDFP"])
    redrawn = {PO_TO_FIPS[po] for po in REDRAWN_2026}
    cd119 = cd119[~cd119["GEOID"].str[:2].isin(redrawn)]
    cd120 = cd120[cd120["GEOID"].str[:2].isin(redrawn)]
    b = pd.concat([cd119.assign(src="cd119"), cd120.assign(src="cd120")], ignore_index=True)
    b = b.rename(columns={"GEOID": "block"})
    b["fips"] = b["block"].str[:2]
    b = b[b["fips"].isin(STATES)]  # drops Puerto Rico
    b["state_po"] = b["fips"].map(lambda f: STATES[f][0])
    # "ZZ" = water-only blocks no district claims (Lake Michigan off Illinois,
    # Long Island Sound off Connecticut, a few in New Hampshire); nobody lives there
    zz = b["CDFP"] == "ZZ"
    print(f"  dropping {zz.sum()} water-only blocks with no district (ZZ)")
    b = b[~zz]
    assert b["CDFP"].str.fullmatch(r"\d\d").all()
    # 00 = at-large, 98 = DC's non-voting delegate: both become district 0
    b["district"] = b["CDFP"].astype(int).replace({98: 0})
    return b[["block", "state_po", "district", "src"]]


# ---------------------------------------------------------------- build

def build():
    print("reading blocks ...")
    blocks = block_districts()
    pop = block_population()
    bz = block_zcta()
    assert pop["block"].is_unique and blocks["block"].is_unique
    n_blocks = len(blocks)
    blocks = blocks.merge(pop, on="block", how="left")
    assert blocks["pop"].notna().all(), "blocks with no PL population record"
    assert len(blocks) == n_blocks
    print(f"  {len(blocks):,} blocks, {blocks['pop'].sum():,} people (2020)")

    b = blocks.merge(bz, on="block", how="inner")
    print(f"  {len(b):,} blocks in a ZCTA ({b['pop'].sum():,} people); "
          f"{blocks['pop'].sum() - b['pop'].sum():,} people in blocks outside any ZCTA")

    g = (b.groupby(["zcta", "state_po", "district"], as_index=False)[["pop", "aland", "awater"]].sum())
    g["area"] = g["aland"] + g["awater"]
    tot = g.groupby(["zcta", "state_po"])[["pop", "aland", "area"]].transform("sum")
    g["method"] = np.where(tot["pop"] > 0, "population", "area")
    g["share"] = np.where(tot["pop"] > 0, g["pop"] / tot["pop"].where(tot["pop"] > 0),
                          np.where(tot["aland"] > 0, g["aland"] / tot["aland"].where(tot["aland"] > 0),
                                   g["area"] / tot["area"].where(tot["area"] > 0)))
    pairs_all = g[["zcta", "state_po", "district", "aland", "pop"]].copy()  # incl. unpopulated overlaps, for validation
    g = g[g["share"] > 0]  # a district reaching a ZCTA only through empty blocks is dropped
    g["share"] = g["share"].round(6)
    out = g.sort_values(["zcta", "state_po", "district"])[["zcta", "state_po", "district", "share", "method"]]
    out.to_csv(OUT, index=False)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(out):,} rows, {out['zcta'].nunique():,} ZCTAs")

    # centroids: Gazetteer internal point + 2020 population (all states combined)
    with zipfile.ZipFile(RAW / "2026_Gaz_zcta_national.zip") as z:
        gaz = pd.read_csv(z.open(z.namelist()[0]), sep="|", dtype={"GEOID": str})
    gaz.columns = gaz.columns.str.strip()
    zpop = b.groupby("zcta")["pop"].sum()
    main_state = (b.groupby(["zcta", "state_po"])["pop"].sum().reset_index()
                  .sort_values(["zcta", "pop"], ascending=[True, False]).drop_duplicates("zcta")
                  .set_index("zcta")["state_po"])
    cent = pd.DataFrame({"zcta": gaz["GEOID"], "lat": gaz["INTPTLAT"], "lon": gaz["INTPTLONG"]})
    cent = cent[cent["zcta"].isin(out["zcta"])]
    cent["pop2020"] = cent["zcta"].map(zpop).astype(int)
    cent["state_po"] = cent["zcta"].map(main_state)
    cent.sort_values("zcta").to_csv(OUT_CENT, index=False)
    print(f"wrote {OUT_CENT.relative_to(ROOT)}: {len(cent):,} ZCTAs")
    return out, cent, blocks, b, pairs_all


# ---------------------------------------------------------------- checks

# Well-known ZIPs and the district each is in under the 2026 lines, checked by
# hand against official sources (see the notes printed with each).
# "Census map" = the 120th Congress layer of the Census Bureau's TIGERweb map
# service queried at a landmark point; "state file" = that block in the state's
# official assignment file. Two ZIPs are split, so only the landmark is checked.
SPOT_CHECKS = {
    "78701": ("TX", 10, "Texas Capitol block; Census map + state file (east/north parts are TX-37)"),
    "90210": ("CA", 36, "Census map + state file"),
    "27601": ("NC", 2, "Census map + state file"),
    "43215": ("OH", 15, "Statehouse; Census map (Columbus Commons/south side are OH-3)"),
    "84101": ("UT", 1, "Census map + Utah GIS office district layer"),
    "37203": ("TN", 6, "Census map (was TN-7 on the 119th lines)"),
    "70112": ("LA", 2, "Census map + state file"),
    "35203": ("AL", 7, "Census map"),
    "33130": ("FL", 27, "Census map + state file"),
    "10001": ("NY", 12, "Census map (lines unchanged)"),
}


def check_state_bafs(blocks: pd.DataFrame):
    """Block-by-block comparison of the Census 120th Congress assignment with
    each state's own official block assignment file."""
    for po, (url, name) in STATE_BAFS.items():
        path = RAW / "state_baf" / name
        st = read_state_baf(po, path)
        mine = blocks[blocks["state_po"] == po][["block", "district"]]
        m = mine.merge(st, on="block", how="outer", suffixes=("", "_state"), indicator=True)
        both = m[m["_merge"] == "both"]
        diff = both[both["district"] != both["district_state"]]
        msg = (f"  {po}: {len(both):,} blocks matched, {len(diff)} assigned differently, "
               f"{(m['_merge'] != 'both').sum()} unmatched")
        census_only = m[m["_merge"] == "left_only"]
        if len(census_only):
            # Louisiana numbers its own precinct-adjusted blocks, so some Census
            # blocks have no twin: check them against the state's districts for
            # the same block group instead.
            state_only = m[m["_merge"] == "right_only"]
            bg = state_only.groupby(state_only["block"].str[:12])["district_state"].agg(set)
            sets = census_only["block"].str[:12].map(bg)
            ok = [isinstance(s, set) and s == {d} for s, d in zip(sets, census_only["district"])]
            msg += (f"; {sum(ok)} of {len(census_only)} Census-only blocks fall in block groups the "
                    f"state file puts wholly in the same district")
        print(msg)


def read_state_baf(po, path) -> pd.DataFrame:
    """Each state's file in its own format -> block, district."""
    if po in ("TX", "NC"):
        with zipfile.ZipFile(path) as z:
            d = pd.read_csv(z.open(z.namelist()[0]), dtype=str, encoding="utf-8-sig")
    elif po == "OH":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith(".xlsx"))
            d = pd.read_excel(io.BytesIO(z.read(name)), dtype=str)
    elif po == "LA":  # fixed width: block, spaces, district
        d = pd.read_csv(path, sep=r"\s+", header=None, dtype=str)
    else:  # CA, FL: two columns, no header
        d = pd.read_csv(path, header=None, dtype=str, encoding="utf-8-sig")
    d = d.iloc[:, :2]
    d.columns = ["block", "district"]
    return d.assign(district=d["district"].astype(int))


def validate(out, cent, blocks, b, pairs_all):
    print("\nvalidation")
    # 1. every ZCTA with a block in the 50 states + DC is in the lookup
    want = set(b["zcta"])
    gaz_us = set(cent["zcta"])
    print(f"  ZCTAs: {out['zcta'].nunique():,} in output, {len(want):,} with blocks in 50 states + DC; "
          f"missing {len(want - set(out['zcta']))}; centroids for {len(gaz_us):,}")
    assert want == set(out["zcta"]) == gaz_us

    # 2. shares sum to 1 within each (zcta, state)
    s = out.groupby(["zcta", "state_po"])["share"].sum()
    print(f"  share sums: min {s.min():.6f}, max {s.max():.6f}; "
          f"{(out.groupby('zcta')['state_po'].nunique() > 1).sum()} ZCTAs cross a state line; "
          f"method counts {out.drop_duplicates(['zcta', 'state_po'])['method'].value_counts().to_dict()}")
    assert ((s - 1).abs() <= 0.01).all()

    # 3. district lists match the race list (and The Downballot's 2026-lines table)
    races = pd.read_csv(ROOT / "data" / "processed" / "races_2026_house.csv")
    mine = out.groupby("state_po")["district"].apply(lambda d: sorted(set(d)))
    theirs = races.groupby("state_po")["district"].apply(sorted)
    bad = [st for st in theirs.index if mine.get(st) != theirs[st]]
    print(f"  districts: {len(out.drop_duplicates(['state_po', 'district'])) - 1} (+ DC delegate) "
          f"vs {len(races)} in races_2026_house.csv; states that differ: {bad or 'none'}")
    assert not bad and set(mine.index) - set(theirs.index) == {"DC"}
    db = pd.read_csv(ROOT / "data" / "raw" / "downballot" / "pres_by_cd_2026_lines.csv", skiprows=3, header=None)
    db = db[db[0].astype(str).str.match(r"^[A-Z]{2}-(\d\d|AL)$")]
    n_db = db[0].str[:2].value_counts()
    n_mine = out[out["state_po"] != "DC"].drop_duplicates(["state_po", "district"])["state_po"].value_counts()
    print(f"  Downballot 2026-lines table: {len(db)} districts; per-state counts "
          f"{'agree' if n_db.sort_index().equals(n_mine.sort_index()) else 'DIFFER'}")

    # 4. each plan is population-balanced (a garbled assignment would not be)
    dp = blocks.groupby(["state_po", "district"])["pop"].sum().reset_index()
    dp["dev"] = dp["pop"] - dp.groupby("state_po")["pop"].transform("mean")
    worst = dp.loc[dp.groupby("state_po")["dev"].apply(lambda x: x.abs().idxmax())]
    print("  largest deviation from the ideal district population (2020), redrawn states: " +
          ", ".join(f"{r.state_po} {r.dev:+.0f}" for r in worst.itertuples() if r.state_po in REDRAWN_2026))
    other = worst[~worst["state_po"].isin(REDRAWN_2026)].assign(a=lambda d: d["dev"].abs()).nlargest(4, "a")
    print("  ... other states, largest: " + ", ".join(f"{r.state_po} {r.dev:+.0f}" for r in other.itertuples()) +
          "  (states that count prisoners at their home address draw on adjusted data, not raw 2020 counts)")

    # 5. unchanged states agree with the Census 119th Congress ZCTA relationship file (land overlaps)
    rel = pd.read_csv(RAW / "tab20_cd11920_zcta520_natl.txt", sep="|", dtype=str, encoding="utf-8-sig")
    rel = rel.dropna(subset=["GEOID_ZCTA5_20"])
    rel = rel[rel["AREALAND_PART"].astype(int) > 0]
    rel["fips"] = rel["GEOID_CD119_20"].str[:2]
    rel = rel[rel["fips"].isin(STATES)]
    rel["state_po"] = rel["fips"].map(lambda f: STATES[f][0])
    rel = rel[~rel["state_po"].isin(REDRAWN_2026)]
    rel_pairs = set(zip(rel["GEOID_ZCTA5_20"], rel["state_po"],
                        rel["GEOID_CD119_20"].str[2:].astype(int).replace({98: 0})))
    pa = pairs_all[(pairs_all["aland"] > 0) & ~pairs_all["state_po"].isin(REDRAWN_2026)]
    my_pairs = set(zip(pa["zcta"], pa["state_po"], pa["district"]))
    print(f"  unchanged states vs Census CD119-ZCTA file: {len(my_pairs):,} vs {len(rel_pairs):,} land overlaps, "
          f"{len(my_pairs ^ rel_pairs)} differ")
    # population-weighted vs land-area shares: how much the weighting matters
    rel["area_share"] = rel["AREALAND_PART"].astype(int) / rel.groupby(["GEOID_ZCTA5_20", "state_po"])[
        "AREALAND_PART"].transform(lambda x: x.astype(int).sum())
    rel["district"] = rel["GEOID_CD119_20"].str[2:].astype(int).replace({98: 0})
    cmp = out.merge(rel.rename(columns={"GEOID_ZCTA5_20": "zcta"})[["zcta", "state_po", "district", "area_share"]],
                    on=["zcta", "state_po", "district"], how="inner")
    split = cmp[cmp.groupby(["zcta", "state_po"])["district"].transform("size") > 1]
    top_pop = out.loc[out.groupby(["zcta", "state_po"])["share"].idxmax()]
    top_area = rel.loc[rel.groupby(["GEOID_ZCTA5_20", "state_po"])["area_share"].idxmax()]
    tt = top_pop.merge(top_area.rename(columns={"GEOID_ZCTA5_20": "zcta"})[["zcta", "state_po", "district"]],
                       on=["zcta", "state_po"], suffixes=("", "_area"))
    print(f"  split ZCTAs in unchanged states: mean |pop share - area share| {(split['share'] - split['area_share']).abs().mean():.3f}; "
          f"main district differs in {(tt['district'] != tt['district_area']).sum()} of {len(tt):,} ZCTAs")

    # 6. official state files; and which states Census's 120th Congress file changes
    check_state_bafs(blocks)
    with zipfile.ZipFile(RAW / "cd120.zip") as z:
        cd120 = pd.read_csv(z.open("NationalCD120.txt"), dtype=str, usecols=["GEOID", "CDFP"])
    cd120 = cd120[cd120["CDFP"] != "ZZ"].rename(columns={"GEOID": "block"})
    m = blocks.merge(cd120, on="block")
    m = m[m["district"] != m["CDFP"].astype(int).replace({98: 0})]
    print(f"  blocks where Census's 120th Congress file differs from the lines used here: "
          f"{m.groupby('state_po').size().to_dict()} (Missouri expected: 2025 map not in effect)")

    # 7. spot checks
    print("  spot checks:")
    for z, (po, dist, note) in SPOT_CHECKS.items():
        rows = out[out["zcta"] == z]
        got = ", ".join(f"{r.state_po}-{r.district} {r.share:.0%}" for r in rows.itertuples())
        ok = ((rows["state_po"] == po) & (rows["district"] == dist)).any()
        print(f"    {z}: {got:<40} expected {po}-{dist} [{'ok' if ok else 'MISMATCH'}] {note}")


if __name__ == "__main__":
    download()
    if "--download-only" in sys.argv:
        sys.exit()
    out, cent, blocks, b, pairs_all = build()
    validate(out, cent, blocks, b, pairs_all)
