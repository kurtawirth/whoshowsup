"""Stage 2 (confirmatory): does registration change since the baseline presidential election predict the
model's backtest miss? Statewide SEN/GOV in FL, CA, NC, IA, CO, PA; House districts in FL, CA, CO
where registration exists on the same lines. TEST ONLY. Writes stage2_results.txt."""
import io

import numpy as np
import pandas as pd
import statsmodels.api as sm

from common import HERE, ROOT

buf = io.StringIO()


def out(*a):
    print(*a)
    print(*a, file=buf)


bt = pd.read_csv(ROOT / "midterms_2026" / "outputs" / "backtest_race_forecasts.csv")
bt["miss"] = bt.actual - bt.margin_median
bt["fmiss"] = bt.actual - bt.fundamentals_mean
STATES = ["FL", "CA", "NC", "IA", "CO", "PA"]

# ---------------- statewide registration
reg = pd.read_csv(HERE / "county_registration.csv", dtype={"fips": str})
st = reg.groupby(["state", "year"])[["dem", "rep", "total"]].sum()
st["regshare"] = 100 * (st.dem - st.rep) / st.total
S = st.regshare.to_dict()

sw = bt[bt.office.isin(["SEN", "GOV"]) & bt.state_po.isin(STATES) & ~bt.special.fillna(False).astype(bool)].copy()
sw["base"] = np.where(sw.year % 4 == 0, sw.year - 4, sw.year - 2)   # previous presidential election
sw["dreg"] = [S.get((s, y), np.nan) - S.get((s, b), np.nan) for s, y, b in zip(sw.state_po, sw.year, sw.base)]
sw = sw.dropna(subset=["dreg", "miss"])
# national registration context is unknown; also form the version relative to the other sample states that year
sw["dreg_rel"] = sw.dreg - sw.groupby("year").dreg.transform("mean")
sw["level"] = "statewide"

# ---------------- House on unchanged lines
cd = pd.read_csv(HERE / "cd_registration.csv")
cd["regshare"] = 100 * (cd.dem - cd.rep) / cd.total
C = cd.set_index(["state", "year", "district"]).regshare.to_dict()
# (race year) -> (registration baseline year on the same lines), per state
SAME_LINES = {
    "CA": {2014: 2012, 2016: 2012, 2018: 2016, 2020: 2016, 2024: 2022},
    "CO": {2014: 2012, 2016: 2012, 2018: 2016, 2020: 2016, 2024: 2022},
    "FL": {2018: 2016, 2020: 2016, 2024: 2022},
}
h = bt[(bt.office == "HOUSE") & bt.state_po.isin(SAME_LINES.keys())].copy()
h["regbase"] = [SAME_LINES[s].get(y, np.nan) for s, y in zip(h.state_po, h.year)]
h["dreg"] = [C.get((s, y, d), np.nan) - C.get((s, int(b), d), np.nan) if b == b else np.nan
             for s, y, d, b in zip(h.state_po, h.year, h.district, h.regbase)]
h = h.dropna(subset=["dreg", "miss"])
h["dreg_rel"] = h.dreg - h.groupby(["year", "state_po"]).dreg.transform("mean")
h["level"] = "house"

out("=== Stage 2 sample ===")
out("statewide:", sw.groupby("year").size().to_dict())
out("house:", h.groupby(["year", "state_po"]).size().to_dict())
out()


def ols(d, y, xs, cluster=None):
    X = sm.add_constant(d[xs].values)
    m = sm.OLS(d[y].values, X)
    return m.fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d[cluster])[0]}) if cluster else m.fit(cov_type="HC1")


for name, d in [("statewide", sw), ("house (same lines)", h)]:
    out(f"--- {name}: n={len(d)} ---")
    for y in ["miss", "fmiss"]:
        for x in ["dreg", "dreg_rel"]:
            r = ols(d, y, [x], "year")
            out(f"  {y:5s} ~ {x:8s}: b={r.params[1]:+.3f} (SE clustered by year {r.bse[1]:.3f}) R2={r.rsquared:.3f}")
    if name.startswith("house"):
        pl = d[d.poll_count == 0]
        r = ols(pl, "fmiss", ["dreg_rel"], "year")
        out(f"  poll-less only (n={len(pl)}): fmiss ~ dreg_rel: b={r.params[1]:+.3f} (SE {r.bse[1]:.3f})")
    sub = d[d.year >= 2018]
    r = ols(sub, "miss", ["dreg_rel"], "year")
    out(f"  2018+ only (n={len(sub)}): miss ~ dreg_rel: b={r.params[1]:+.3f} (SE {r.bse[1]:.3f})")
    out()

# ---------------- leave-one-year-out
out("=== Leave-one-year-out: RMSE of the backtest miss, without vs with a registration correction ===")
out("Correction = b * dreg_rel (b fit on the other years, no intercept: registration only re-ranks races).")
for name, d in [("statewide", sw), ("house", h)]:
    for y in ["miss", "fmiss"]:
        rows = []
        for yr in sorted(d.year.unique()):
            tr, te = d[d.year != yr], d[d.year == yr]
            b = np.sum(tr.dreg_rel * (tr[y] - tr.groupby("year")[y].transform("mean"))) / np.sum(tr.dreg_rel ** 2)
            base = np.sqrt(np.mean(te[y] ** 2))
            corr = np.sqrt(np.mean((te[y] - b * te.dreg_rel) ** 2))
            rows.append(dict(level=name, target=y, held_out=yr, n=len(te), b=round(b, 3),
                             rmse_model=round(base, 2), rmse_with_reg=round(corr, 2), change=round(corr - base, 3)))
        t = pd.DataFrame(rows)
        out(t.to_string(index=False))
        w = t[t.held_out >= 2018]
        out(f"  2018+ n-weighted mean change in RMSE: {np.average(w.change, weights=w.n):+.3f} pts; all years: "
            f"{np.average(t.change, weights=t.n):+.3f}")
        out()

pd.concat([sw, h])[["level", "year", "office", "state_po", "district", "actual", "margin_median", "fundamentals_mean",
                    "miss", "fmiss", "dreg", "dreg_rel", "poll_count"]].to_csv(HERE / "stage2_races.csv", index=False)
(HERE / "stage2_results.txt").write_text(buf.getvalue())
