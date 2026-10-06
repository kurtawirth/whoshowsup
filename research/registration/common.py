"""Shared loaders for the registration research (TEST ONLY)."""
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"

# ACS 5-year CVAP window centred on each election year (2024 uses the latest, 2020-2024)
CVAP_FILE = {2008: "2006_2010", 2010: "2008_2012", 2012: "2010_2014", 2014: "2012_2016", 2016: "2014_2018",
             2018: "2016_2020", 2020: "2018_2022", 2022: "2020_2024", 2024: "2020_2024"}


def load_cvap():
    out = []
    for y, f in CVAP_FILE.items():
        d = pd.read_csv(RAW / "cvap" / f"county_cvap_{f}.csv", encoding="latin-1")
        d.columns = [c.lower() for c in d.columns]
        d = d[d.lntitle == "Total"]
        out.append(pd.DataFrame({"fips": d.geoid.str[-5:], "year": y, "cvap": d.cvap_est.astype(float)}))
    return pd.concat(out)


def load_pres():
    d = pd.read_csv(RAW / "medsl" / "countypres_2000-2024.csv", dtype={"county_fips": str})
    d = d[(d.year >= 2004) & d.county_fips.notna()]
    d["fips"] = d.county_fips.str.split(".").str[0].str.zfill(5)
    d["is_total"] = d["mode"].astype(str).str.upper() == "TOTAL"
    has_total = d.groupby(["year", "fips"]).is_total.transform("any")
    d = d[d.is_total | ~has_total]
    g = d.groupby(["year", "state_po", "fips", "party"]).candidatevotes.sum().unstack(fill_value=0)
    tot = d.groupby(["year", "state_po", "fips"]).candidatevotes.sum()
    out = pd.DataFrame({"pd": g["DEMOCRAT"], "pr": g["REPUBLICAN"], "votes": tot}).reset_index()
    out["margin"] = 100 * (out.pd - out.pr) / (out.pd + out.pr)
    return out


def load_reg():
    r = pd.read_csv(HERE / "county_registration.csv", dtype={"fips": str})
    r["regshare"] = 100 * (r.dem - r.rep) / r.total
    return r


def fe_ols(df, y, xs, fe, weight=None, cluster=None):
    """OLS of y on xs with fixed effects (absorbed by within-demeaning), optional weights,
    cluster-robust SEs by `cluster` (falls back to HC1). Returns dict with coefs/SEs and within-R2."""
    d = df.dropna(subset=[y] + xs + ([weight] if weight else [])).copy()
    w = d[weight].values if weight else np.ones(len(d))
    cols = [y] + xs
    dm = d[cols].copy()
    for c in cols:
        wm = (d[c] * w).groupby(d[fe]).transform("sum") / pd.Series(w, index=d.index).groupby(d[fe]).transform("sum")
        dm[c] = d[c] - wm
    X = dm[xs].values
    model = sm.WLS(dm[y].values, X, weights=w)
    if cluster:
        res = model.fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d[cluster])[0]})
    else:
        res = model.fit(cov_type="HC1")
    res_hc = model.fit(cov_type="HC1")
    resid = dm[y].values - X @ res.params
    tss = np.sum(w * dm[y].values ** 2)
    r2 = 1 - np.sum(w * resid ** 2) / tss
    return {"n": len(d), "groups": d[fe].nunique(), "params": dict(zip(xs, res.params)),
            "se": dict(zip(xs, res.bse)), "se_hc1": dict(zip(xs, res_hc.bse)), "r2_within": r2,
            "t": dict(zip(xs, res.tvalues))}
