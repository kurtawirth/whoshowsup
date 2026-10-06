"""Stage 1: does county party-registration change predict a county's swing relative to its state?
TEST ONLY. Prints results; writes stage1_panel.csv and stage1_results.txt."""
import io
import sys

import numpy as np
import pandas as pd

from common import HERE, fe_ols, load_cvap, load_pres, load_reg

buf = io.StringIO()


def out(*a):
    print(*a)
    print(*a, file=buf)


reg = load_reg()
cvap = load_cvap()
pres = load_pres()
reg = reg.merge(cvap, on=["fips", "year"], how="left")
reg["regrate"] = 100 * reg.total / reg.cvap
R = reg.set_index(["fips", "year"])
P = pres.set_index(["fips", "year"])

STATES = sorted(reg.state.unique())


def rv(f, y, col):
    try:
        return R.at[(f, y), col]
    except KeyError:
        return np.nan


def pv(f, y, col):
    try:
        return P.at[(f, y), col]
    except KeyError:
        return np.nan


# ------------------------------------------------------------------ presidential panel
rows = []
for (f, st) in reg[["fips", "state"]].drop_duplicates().itertuples(index=False):
    for t0 in (2008, 2012, 2016, 2020):
        t1 = t0 + 4
        rows.append(dict(
            fips=f, state=st, t0=t0, t1=t1, cycle=f"{t0}-{t1}",
            swing=pv(f, t1, "margin") - pv(f, t0, "margin"),
            lagswing=pv(f, t0, "margin") - pv(f, t0 - 4, "margin"),
            nextswing=pv(f, t1 + 4, "margin") - pv(f, t1, "margin") if t1 + 4 <= 2024 else np.nan,
            margin0=pv(f, t0, "margin"),
            votes0=pv(f, t0, "votes"),
            dturnout=100 * (pv(f, t1, "votes") / rv(f, t1, "cvap") - pv(f, t0, "votes") / rv(f, t0, "cvap")),
            dreg=rv(f, t1, "regshare") - rv(f, t0, "regshare"),
            dreg_mid=rv(f, t0 + 2, "regshare") - rv(f, t0, "regshare"),      # known 2 years early
            dreg_late=rv(f, t1, "regshare") - rv(f, t0 + 2, "regshare"),     # midterm -> eve of election
            dreg_prev=rv(f, t0, "regshare") - rv(f, t0 - 4, "regshare"),
            dtot=rv(f, t1, "regrate") - rv(f, t0, "regrate"),
            regshare0=rv(f, t0, "regshare"),
        ))
pan = pd.DataFrame(rows)
pan["sc"] = pan.state + "_" + pan.cycle
pan["maga"] = pan.t0 >= 2016  # cycles 2016-2020 and 2020-2024 (2012-2016 is the Trump-entry cycle)
pan = pan.dropna(subset=["swing", "dreg"])
# trim absurd registration ratios (tiny counties / list purges) for the dtot variable only
pan.loc[pan.dtot.abs() > 40, "dtot"] = np.nan
pan.to_csv(HERE / "stage1_panel.csv", index=False)

out("=== Stage 1: county panel ===")
out(pan.groupby(["state", "cycle"]).size().unstack().fillna(0).astype(int).to_string())
out()
out("Within state-cycle SDs (vote-weighted not applied):")
dm = pan.copy()
for c in ["swing", "dreg", "dtot", "lagswing"]:
    dm[c] = pan[c] - pan.groupby("sc")[c].transform("mean")
out(dm[["swing", "dreg", "dtot", "lagswing"]].std().round(2).to_string())
out()


def show(label, r, xs):
    s = "  ".join(f"{x}: b={r['params'][x]:+.3f} (clSE {r['se'][x]:.3f}, HC1 {r['se_hc1'][x]:.3f})" for x in xs)
    out(f"{label:58s} n={r['n']:4d} R2w={r['r2_within']:.3f}  {s}")


def block(sub, title, weight):
    out(f"--- {title} | weight={weight or 'none'} ---")
    base = fe_ols(sub, "swing", ["lagswing", "margin0"], "sc", weight, "sc")
    show("swing ~ lagswing + margin0 (no registration)", base, ["lagswing", "margin0"])
    r1 = fe_ols(sub, "swing", ["dreg"], "sc", weight, "sc")
    show("swing ~ dreg", r1, ["dreg"])
    r2 = fe_ols(sub, "swing", ["dreg", "lagswing", "margin0"], "sc", weight, "sc")
    show("swing ~ dreg + lagswing + margin0", r2, ["dreg", "lagswing"])
    out(f"{'':58s} R2 gain from dreg over base: {r2['r2_within'] - base['r2_within']:+.3f}")
    r3 = fe_ols(sub, "swing", ["dreg_mid", "lagswing", "margin0"], "sc", weight, "sc")
    show("swing ~ dreg_mid (t0->midterm only) + lagswing + margin0", r3, ["dreg_mid", "lagswing"])
    r4 = fe_ols(sub, "swing", ["dtot", "lagswing", "margin0"], "sc", weight, "sc")
    show("swing ~ dtot (reg/CVAP growth) + lagswing + margin0", r4, ["dtot"])
    return r1, r2


for weight in [None, "votes0"]:
    block(pan, "ALL cycles", weight)
    block(pan[pan.maga], "2016+ cycles (2016-20, 2020-24)", weight)
    for cyc in sorted(pan.cycle.unique()):
        r = fe_ols(pan[pan.cycle == cyc], "swing", ["dreg", "lagswing", "margin0"], "sc", weight, "sc")
        show(f"  cycle {cyc}: swing ~ dreg + lagswing + margin0", r, ["dreg"])
    for st in STATES:
        s = pan[(pan.state == st) & pan.maga]
        if len(s) > 20:
            r = fe_ols(s, "swing", ["dreg", "lagswing", "margin0"], "sc", weight, None)
            show(f"  {st} 2016+: swing ~ dreg + lagswing + margin0", r, ["dreg"])
    out()

# ------------------------------------------------------------------ causality / lag check
out("=== Lag check: is registration change a lagging indicator of the vote? ===")
out("Within state-cycle correlations of dreg(t0->t1) with swings (unweighted):")
for cyc in sorted(pan.cycle.unique()):
    s = dm[pan.cycle == cyc] if False else None
lag_rows = []
for cyc, g in pan.groupby("cycle"):
    d = g.copy()
    for c in ["dreg", "swing", "lagswing", "nextswing"]:
        d[c] = g[c] - g.groupby("sc")[c].transform("mean")
    lag_rows.append(dict(cycle=cyc, n=len(d),
                         r_prev_swing=d.dreg.corr(d.lagswing),
                         r_concurrent=d.dreg.corr(d.swing),
                         r_next_swing=d.dreg.corr(d.nextswing)))
out(pd.DataFrame(lag_rows).round(3).to_string(index=False))
out()
for weight in [None, "votes0"]:
    out(f"weight={weight or 'none'}")
    r = fe_ols(pan, "dreg", ["lagswing", "swing"], "sc", weight, "sc")
    show("dreg ~ lagswing + swing (what registration change tracks)", r, ["lagswing", "swing"])
    r = fe_ols(pan[pan.maga], "dreg", ["lagswing", "swing"], "sc", weight, "sc")
    show("  2016+ only", r, ["lagswing", "swing"])
    # forward: does registration change already on the books predict the NEXT cycle's swing?
    r = fe_ols(pan, "nextswing", ["dreg", "swing"], "sc", weight, "sc")
    show("nextswing ~ dreg + swing (fwd one cycle)", r, ["dreg", "swing"])
    r = fe_ols(pan, "swing", ["dreg_prev", "lagswing", "margin0"], "sc", weight, "sc")
    show("swing ~ dreg_prev(t0-4->t0) + lagswing + margin0", r, ["dreg_prev", "lagswing"])
    r = fe_ols(pan, "swing", ["dreg_mid", "dreg_late", "lagswing", "margin0"], "sc", weight, "sc")
    show("swing ~ dreg_mid + dreg_late + lagswing + margin0", r, ["dreg_mid", "dreg_late"])
    out()

# ------------------------------------------------------------------ leave-one-cycle-out prediction
out("=== Leave-one-cycle-out: predict relative swing (swing minus state-cycle mean) ===")
out("Baseline predicts 0 relative swing; '+lag' uses lagswing+margin0 fit on other cycles; '+reg' adds dreg.")
loo = []
for weight in [None, "votes0"]:
    for cyc in sorted(pan.cycle.unique()):
        tr, te = pan[pan.cycle != cyc], pan[pan.cycle == cyc].dropna(subset=["lagswing", "margin0", "dreg"])
        w = te[weight].values if weight else np.ones(len(te))
        rel = te.swing - te.groupby("sc").swing.transform("mean")

        def pred(xs):
            r = fe_ols(tr, "swing", xs, "sc", weight, None)
            p = sum(r["params"][x] * (te[x] - te.groupby("sc")[x].transform("mean")) for x in xs)
            return p

        def rmse(p):
            return np.sqrt(np.sum(w * (rel - p) ** 2) / np.sum(w))

        p_lag = pred(["lagswing", "margin0"])
        p_reg = pred(["dreg", "lagswing", "margin0"])
        p_reg_only = pred(["dreg"])
        loo.append(dict(weight=weight or "none", held_out=cyc, n=len(te), rmse_zero=rmse(0),
                        rmse_dreg_only=rmse(p_reg_only), rmse_lag=rmse(p_lag), rmse_lag_plus_dreg=rmse(p_reg)))
out(pd.DataFrame(loo).round(3).to_string(index=False))

(HERE / "stage1_results.txt").write_text(buf.getvalue())
