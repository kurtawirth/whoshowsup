"""Stage 3: does county total-registration growth (EAVS, relative to CVAP) predict turnout change and/or
relative swing, nationwide? TEST ONLY. Writes eavs_county_registration.csv and stage3_results.txt."""
import io
import zipfile

import numpy as np
import pandas as pd

from common import HERE, RAW, fe_ols, load_cvap, load_pres

buf = io.StringIO()


def out(*a):
    print(*a)
    print(*a, file=buf)


E = RAW / "registration" / "eavs"
SRC = {2010: (E / "2010_2010EAVS_A_Final.xls", "QA1a"), 2012: (E / "2012_2012EAVS_NVRAData.xlsx", "QA1a"),
       2014: (E / "EAVS_Section_A.xlsx", "QA1a"),
       2016: (E / "EAVS_2016_Final_Data_for_Public_Release_nolabel_V1.1_CSV.csv", "A1a"),
       2018: (E / "2018_EAVS_2018_for_Public_Release_Updates3.csv", "A1a"),
       2020: (E / "2020_EAVS_for_Public_Release_nolabel_V1.2_CSV.csv", "A1a"),
       2022: (E / "2022_EAVS_for_Public_Release_nolabel_V1.1_CSV.csv", "A1a"),
       2024: (E / "2024_EAVS_for_Public_Release_nolabel_V2.csv", "A1a")}
parts = []
for y, (p, col) in SRC.items():
    if p.suffix == ".csv":
        d = pd.read_csv(p, usecols=["FIPSCode", col], dtype={"FIPSCode": str}, encoding="latin-1")
    else:
        d = pd.read_excel(p, usecols=["FIPSCode", col], dtype={"FIPSCode": str})
    d["FIPSCode"] = d.FIPSCode.str.strip().str.split(".").str[0].str.zfill(10)
    d["reg"] = pd.to_numeric(d[col], errors="coerce")
    d = d[d.reg > 0]                      # drops -77/-88/-99 missing codes
    d["fips"] = d.FIPSCode.str[:5]
    g = d.groupby("fips").reg.sum().reset_index()
    g["year"] = y
    parts.append(g)
eavs = pd.concat(parts)
eavs = eavs[~eavs.fips.str.startswith("02")]  # Alaska reports statewide / by borough inconsistently
eavs = eavs.merge(load_cvap(), on=["fips", "year"], how="inner")
eavs["regrate"] = 100 * eavs.reg / eavs.cvap
eavs.to_csv(HERE / "eavs_county_registration.csv", index=False)
out("EAVS counties per year (with CVAP):", eavs.groupby("year").size().to_dict())

pres = load_pres()
cv = load_cvap()
pres = pres.merge(cv, on=["fips", "year"], how="left")
pres["turnout"] = 100 * pres.votes / pres.cvap
R = eavs.set_index(["fips", "year"]).regrate.to_dict()
P = pres.set_index(["fips", "year"])[["margin", "turnout", "votes", "state_po"]]
Pd = {c: P[c].to_dict() for c in P.columns}

rows = []
for f in eavs.fips.unique():
    for t0 in (2012, 2016, 2020):
        t1 = t0 + 4
        g = lambda c, y: Pd[c].get((f, y), np.nan)
        rows.append(dict(fips=f, state=g("state_po", t1), cycle=f"{t0}-{t1}", t0=t0,
                         dtot=R.get((f, t1), np.nan) - R.get((f, t0), np.nan),
                         dtot_mid=R.get((f, t0 + 2), np.nan) - R.get((f, t0), np.nan),   # known 2 yrs early
                         regrate0=R.get((f, t0), np.nan),
                         dturn=g("turnout", t1) - g("turnout", t0),
                         lagdturn=g("turnout", t0) - g("turnout", t0 - 4),
                         swing=g("margin", t1) - g("margin", t0),
                         lagswing=g("margin", t0) - g("margin", t0 - 4),
                         margin0=g("margin", t0), votes0=g("votes", t0)))
pan = pd.DataFrame(rows).dropna(subset=["dtot", "dturn", "swing", "state"])
# EAVS has reporting glitches (jurisdiction splits, purge timing); trim extreme changes
pan = pan[(pan.dtot.abs() < 30) & (pan.dturn.abs() < 30) & (pan.regrate0.between(40, 160))]
pan["sc"] = pan.state + "_" + pan.cycle
out("panel:", pan.groupby("cycle").size().to_dict())


def show(label, r, xs):
    s = "  ".join(f"{x}: b={r['params'][x]:+.3f} (clSE {r['se'][x]:.3f})" for x in xs)
    out(f"{label:55s} n={r['n']:5d} R2w={r['r2_within']:.3f}  {s}")


for weight in [None, "votes0"]:
    out(f"--- weight={weight or 'none'} (state x cycle fixed effects, SE clustered by state-cycle) ---")
    for lab, sub in [("all cycles", pan), ("2016+ cycles", pan[pan.t0 >= 2016])]:
        show(f"[{lab}] dturn ~ lagdturn", fe_ols(sub, "dturn", ["lagdturn"], "sc", weight, "sc"), ["lagdturn"])
        show(f"[{lab}] dturn ~ dtot + lagdturn", fe_ols(sub, "dturn", ["dtot", "lagdturn"], "sc", weight, "sc"), ["dtot"])
        show(f"[{lab}] dturn ~ dtot_mid + lagdturn", fe_ols(sub, "dturn", ["dtot_mid", "lagdturn"], "sc", weight, "sc"), ["dtot_mid"])
        show(f"[{lab}] swing ~ lagswing + margin0", fe_ols(sub, "swing", ["lagswing", "margin0"], "sc", weight, "sc"), ["lagswing"])
        show(f"[{lab}] swing ~ dtot + lagswing + margin0", fe_ols(sub, "swing", ["dtot", "lagswing", "margin0"], "sc", weight, "sc"), ["dtot"])
        show(f"[{lab}] swing ~ dtot_mid + lagswing + margin0", fe_ols(sub, "swing", ["dtot_mid", "lagswing", "margin0"], "sc", weight, "sc"), ["dtot_mid"])
    for cyc in sorted(pan.cycle.unique()):
        s = pan[pan.cycle == cyc]
        show(f"  {cyc}: dturn ~ dtot + lagdturn", fe_ols(s, "dturn", ["dtot", "lagdturn"], "sc", weight, "sc"), ["dtot"])
        show(f"  {cyc}: swing ~ dtot + lagswing + margin0", fe_ols(s, "swing", ["dtot", "lagswing", "margin0"], "sc", weight, "sc"), ["dtot"])
    out()

(HERE / "stage3_results.txt").write_text(buf.getvalue())
