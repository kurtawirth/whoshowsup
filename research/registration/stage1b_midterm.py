"""Stage 1b: midterm county test. Outcome = county midterm Senate/Governor margin minus the county's
previous presidential margin (the model's 'lean' baseline), relative to the state's race-wide shift
(state x office x year fixed effects). Predictor = change in D-R registration share from the
presidential election to the midterm. Also a strictly forward test for the presidential panel.
TEST ONLY. Writes stage1b_results.txt."""
import io

import numpy as np
import pandas as pd

from common import HERE, fe_ols, load_pres, load_reg, load_cvap

buf = io.StringIO()


def out(*a):
    print(*a)
    print(*a, file=buf)


reg = load_reg().merge(load_cvap(), on=["fips", "year"], how="left")
reg["regrate"] = 100 * reg.total / reg.cvap
pres = load_pres()
mid = pd.read_csv(HERE / "county_midterm_results.csv", dtype={"county_fips": str})
mid["fips"] = mid.county_fips.str.zfill(5)
mid["mmargin"] = 100 * (mid.dem - mid.rep) / (mid.dem + mid.rep)
mid["mvotes"] = mid.dem + mid.rep

R = reg.set_index(["fips", "year"])
P = pres.set_index(["fips", "year"])


def get(T, f, y, c):
    try:
        return T.at[(f, y), c]
    except KeyError:
        return np.nan


rows = []
for r in mid.itertuples():
    p0 = r.year - 2
    rows.append(dict(fips=r.fips, state=r.state_po, office=r.office, year=r.year,
                     dev=r.mmargin - get(P, r.fips, p0, "margin"),                     # midterm vs prior pres
                     lagswing=get(P, r.fips, p0, "margin") - get(P, r.fips, p0 - 4, "margin"),
                     margin0=get(P, r.fips, p0, "margin"), votes0=get(P, r.fips, p0, "votes"),
                     dreg=get(R, r.fips, r.year, "regshare") - get(R, r.fips, p0, "regshare"),
                     dreg_prev=get(R, r.fips, p0, "regshare") - get(R, r.fips, p0 - 4, "regshare"),
                     dtot=get(R, r.fips, r.year, "regrate") - get(R, r.fips, p0, "regrate"),
                     dturnout_rel=r.mvotes / get(P, r.fips, p0, "votes")))
m = pd.DataFrame(rows).dropna(subset=["dev", "dreg", "lagswing"])
m["g"] = m.state + "_" + m.office + "_" + m.year.astype(str)
m.loc[m.dtot.abs() > 40, "dtot"] = np.nan
out("=== Stage 1b: midterm counties (Sen/Gov 2018, 2022) ===")
out(m.groupby(["year", "state", "office"]).size().to_string())


def show(label, r, xs):
    s = "  ".join(f"{x}: b={r['params'][x]:+.3f} (clSE {r['se'][x]:.3f}, HC1 {r['se_hc1'][x]:.3f})" for x in xs)
    out(f"{label:52s} n={r['n']:4d} R2w={r['r2_within']:.3f}  {s}")


for weight in [None, "votes0"]:
    out(f"--- weight={weight or 'none'} ---")
    for yrs, lab in [((2018, 2022), "2018+2022"), ((2018,), "2018"), ((2022,), "2022")]:
        s = m[m.year.isin(yrs)]
        b = fe_ols(s, "dev", ["lagswing", "margin0"], "g", weight, "g")
        show(f"[{lab}] dev ~ lagswing + margin0", b, ["lagswing", "margin0"])
        r = fe_ols(s, "dev", ["dreg"], "g", weight, "g")
        show(f"[{lab}] dev ~ dreg", r, ["dreg"])
        r = fe_ols(s, "dev", ["dreg", "lagswing", "margin0"], "g", weight, "g")
        show(f"[{lab}] dev ~ dreg + lagswing + margin0", r, ["dreg", "lagswing"])
        out(f"{'':52s} R2 gain from dreg: {r['r2_within'] - b['r2_within']:+.3f}")
        r = fe_ols(s, "dev", ["dtot", "lagswing", "margin0"], "g", weight, "g")
        show(f"[{lab}] dev ~ dtot + lagswing + margin0", r, ["dtot"])
    out()

# lag check for midterms: does pres->midterm registration change track the PREVIOUS pres swing?
out("Within-group correlations (unweighted): dreg(pres->midterm) with prior pres swing vs. midterm deviation")
for (y), g in m.groupby("year"):
    d = g.copy()
    for c in ["dreg", "dev", "lagswing"]:
        d[c] = g[c] - g.groupby("g")[c].transform("mean")
    out(f"  {y}: n={len(d)}  r(dreg, prior pres swing)={d.dreg.corr(d.lagswing):+.3f}  "
        f"r(dreg, midterm deviation)={d.dreg.corr(d.dev):+.3f}  r(lagswing, deviation)={d.lagswing.corr(d.dev):+.3f}")
out()

# out-of-sample: fit on one midterm year, predict the other
out("=== Midterm cross-year prediction of relative deviation (fit on one year, test on the other) ===")
for weight in [None, "votes0"]:
    for tr_y, te_y in [(2018, 2022), (2022, 2018)]:
        tr, te = m[m.year == tr_y], m[m.year == te_y]
        w = te[weight].values if weight else np.ones(len(te))
        rel = te.dev - te.groupby("g").dev.transform("mean")

        def pred(xs):
            r = fe_ols(tr, "dev", xs, "g", weight, None)
            return sum(r["params"][x] * (te[x] - te.groupby("g")[x].transform("mean")) for x in xs)

        def rmse(p):
            return np.sqrt(np.sum(w * (rel - p) ** 2) / np.sum(w))

        out(f"  weight={weight or 'none':6s} train {tr_y} -> test {te_y}: RMSE zero={rmse(0):.2f}  "
            f"lag={rmse(pred(['lagswing', 'margin0'])):.2f}  lag+dreg={rmse(pred(['dreg', 'lagswing', 'margin0'])):.2f}  "
            f"dreg only={rmse(pred(['dreg'])):.2f}")
out()

# strictly forward presidential test: train on all earlier cycles, test on the next
pan = pd.read_csv(HERE / "stage1_panel.csv", dtype={"fips": str})
out("=== Presidential panel, strictly forward (train on earlier cycles only) ===")
for weight in [None, "votes0"]:
    for te_c, tr_cs in [("2016-2020", ["2008-2012", "2012-2016"]), ("2020-2024", ["2008-2012", "2012-2016", "2016-2020"]),
                        ("2020-2024", ["2016-2020"])]:
        tr, te = pan[pan.cycle.isin(tr_cs)], pan[pan.cycle == te_c].dropna(subset=["lagswing", "margin0", "dreg"])
        w = te[weight].values if weight else np.ones(len(te))
        rel = te.swing - te.groupby("sc").swing.transform("mean")

        def pred(xs):
            r = fe_ols(tr, "swing", xs, "sc", weight, None)
            return sum(r["params"][x] * (te[x] - te.groupby("sc")[x].transform("mean")) for x in xs), r

        def rmse(p):
            return np.sqrt(np.sum(w * (rel - p) ** 2) / np.sum(w))

        p1, _ = pred(["lagswing", "margin0"])
        p2, r2 = pred(["dreg", "lagswing", "margin0"])
        p3, _ = pred(["dreg"])
        out(f"  weight={weight or 'none':6s} train {'+'.join(tr_cs):30s} -> {te_c}: zero={rmse(0):.2f} lag={rmse(p1):.2f} "
            f"lag+dreg={rmse(p2):.2f} (b_dreg={r2['params']['dreg']:+.2f}) dreg only={rmse(p3):.2f}")
    # what coefficient would have been best in 2020-24, given lag model fit on 2016-20?
    te = pan[pan.cycle == "2020-2024"].dropna(subset=["lagswing", "margin0", "dreg"])
    w = te[weight].values if weight else np.ones(len(te))
    rel = te.swing - te.groupby("sc").swing.transform("mean")
    dd = te.dreg - te.groupby("sc").dreg.transform("mean")
    grid = {b: np.sqrt(np.sum(w * (rel - b * dd) ** 2) / np.sum(w)) for b in [0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5]}
    out(f"  2020-24 RMSE by fixed dreg coefficient (no other terms): " + ", ".join(f"{b}:{v:.2f}" for b, v in grid.items()))

(HERE / "stage1b_results.txt").write_text(buf.getvalue())
