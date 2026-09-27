"""Testing hypotheses about undecided voters on 538's archive of race polls (1998-2022).

    .venv/Scripts/python.exe core/undecided_hypotheses.py

Builds on core/undecided_break.py (same polls, same notation: u = undecided share, m = two-party
poll margin, gap = result - m). The national model already sets each year's overall level, so the
test here is WITHIN a year: every form is fitted on the other cycles, and a held-out cycle is scored
after removing its own average miss (its "flat miss"). Lower = the form better predicts which races
miss by more, and which way.

Hypotheses:
  H1  lean     undecideds lean by kind of year (midterm/presidential x president's party), applied
               relative to the year's typical undecided share
  H2  KTI      how hard they swing against the president's party depends on kitchen-table conditions
               that summer: consumer sentiment (University of Michigan: overall, and the current-
               conditions index built from how people rate their own finances), gas prices and
               inflation over the past year (BLS CPI), unemployment and its change (BLS)
  H3  turnout  in states where turnout surges (votes vs the same kind of election 4 years earlier),
               undecideds show up more: their pull/lean is stronger, and polls miss by more

Writes data/processed/undecided_hypotheses.csv (out-of-sample scores) and prints the findings.
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
import undecided_break as ub  # noqa: E402

PROC, ECON = ROOT / "data" / "processed", ROOT / "data" / "raw" / "econ"
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                      "September", "October", "November", "December"], 1)}


def ktis(years) -> pd.DataFrame:
    """National kitchen-table conditions for each election year, as they stood in late summer."""
    um = pd.read_csv(ECON / "umich_sentiment.csv").merge(pd.read_csv(ECON / "umich_components.csv"), on=["Month", "YYYY"])
    um["m"] = um.Month.map(MONTHS)
    bls = pd.read_csv(ECON / "bls_monthly.csv").pivot_table(index=["year", "month"], columns="series", values="value")
    rows = []
    for y in years:
        sep = um[(um.YYYY == y) & (um.m == 9)].iloc[0]
        sep0 = um[(um.YYYY == y - 1) & (um.m == 9)].iloc[0]
        aug, aug0 = bls.loc[(y, 8)], bls.loc[(y - 1, 8)]
        rows.append({"cycle": y, "sentiment": sep.ICS_ALL, "current": sep.ICC,
                     "sentiment_chg": sep.ICS_ALL - sep0.ICS_ALL,
                     "gas_yoy": 100 * (aug.gas_cpi / aug0.gas_cpi - 1), "inflation": 100 * (aug.cpi / aug0.cpi - 1),
                     "unemployment": aug.unemployment, "unemp_chg": aug.unemployment - aug0.unemployment})
    k = pd.DataFrame(rows)
    # a single "hard times" score: low/falling sentiment, rising prices and joblessness (each standardized)
    z = lambda s: (s - s.mean()) / s.std()
    k["hard_times"] = (-z(k.sentiment) - z(k.sentiment_chg) + z(k.gas_yoy) + z(k.inflation) + z(k.unemp_chg)) / 5
    return k


def turnout_surge() -> pd.DataFrame:
    """Votes cast for the House by state and year vs the same kind of election 4 years earlier (log ratio),
    and the same for the nation; 'rel_surge' = the state's surge beyond the nation's."""
    h = pd.read_csv(ROOT / "data" / "raw" / "medsl" / "house_1976_2024.tab", low_memory=False)
    h = h[(h.stage == "GEN") & (h.special == False)]  # noqa: E712
    t = h.drop_duplicates(["year", "state_po", "district"]).groupby(["year", "state_po"])["totalvotes"].sum()
    t = t.reset_index()
    t["prev"] = t.set_index(["year", "state_po"]).totalvotes.reindex(
        pd.MultiIndex.from_arrays([t.year - 4, t.state_po])).to_numpy()
    t["surge"] = np.log(t.totalvotes / t.prev)
    nat = t.groupby("year").apply(lambda g: np.log(g.totalvotes.sum() / g.prev.sum()), include_groups=False).rename("nat_surge")
    t = t.merge(nat.reset_index(), on="year")
    t["rel_surge"] = (t.surge - t.nat_surge).clip(-0.5, 0.5)
    return t.rename(columns={"year": "cycle", "state_po": "state"})[["cycle", "state", "surge", "nat_surge", "rel_surge"]]


def data() -> pd.DataFrame:
    d = ub.polls()
    raw = pd.read_csv(ROOT / "data" / "raw" / "fte" / "raw_polls.csv", low_memory=False)
    loc = raw.drop_duplicates("race_id").set_index("race_id").location
    d["state"] = d.race.map(loc).str[:2]
    d = d.merge(ktis(sorted(d.cycle.unique())), on="cycle").merge(turnout_surge(), on=["cycle", "state"], how="left")
    d["rel_surge"] = d.rel_surge.fillna(0)
    for k in ("hard_times", "sentiment", "current", "sentiment_chg", "gas_yoy", "inflation", "unemp_chg"):
        yr = d.drop_duplicates("cycle")[k]  # standardized across election years (each year once)
        d[f"z_{k}"] = (d[k] - yr.mean()) / yr.std()
    d["w_c"] = d.w - d.groupby("cycle").w.transform(lambda s: np.average(s, weights=d.loc[s.index, "wt"]))
    return d


def cols(d: pd.DataFrame, form: list[str]) -> np.ndarray:
    against = d.out_party  # +1 = toward the out-party (Democrats when a Republican is president)
    f = {
        "m": d.m, "pull": d.w * d.m,
        # H1: lean by kind of year, on the undecided share relative to the year's typical share
        "mid_D": d.w_c * d.midterm * (d.out_party < 0), "mid_R": d.w_c * d.midterm * (d.out_party > 0),
        "pres_D": d.w_c * (1 - d.midterm) * (d.out_party < 0), "pres_R": d.w_c * (1 - d.midterm) * (d.out_party > 0),
        # H2: swing against the president's party, scaled by kitchen-table conditions
        **{f"kti_{k}": d.w_c * against * d[f"z_{k}"]
           for k in ("hard_times", "sentiment", "current", "sentiment_chg", "gas_yoy", "inflation", "unemp_chg")},
        # H3: a turnout surge makes the undecideds count more (stronger pull and lean)
        "pull_x_surge": d.w * d.m * d.rel_surge, "against_x_surge": d.w_c * against * d.rel_surge,
        "surge": d.rel_surge * against,  # (a surge itself favoring the out-party, undecideds or not)
    }
    return np.column_stack([f[c] for c in form])


def fit(d, form):
    X = cols(d, form)
    D = pd.get_dummies(d.cycle).to_numpy(dtype=float)  # each year's flat miss: the national model's job
    Xf, sw = np.column_stack([X, D]), np.sqrt(d.wt.to_numpy())
    return np.linalg.lstsq(Xf * sw[:, None], d.gap.to_numpy() * sw, rcond=None)[0][:X.shape[1]]


def score(d, form) -> dict:
    """Held-out cycles' within-year error (the cycle's own average miss removed), and the coefficients."""
    resid = np.zeros(len(d))
    for c in d.cycle.unique():
        tr, te = (d.cycle != c).to_numpy(), (d.cycle == c).to_numpy()
        r = d.gap[te].to_numpy() - cols(d[te], form) @ fit(d[tr], form)
        w = d.wt[te].to_numpy()
        resid[te] = r - np.average(r, weights=w)
    out = {"rmse_within": float(np.sqrt(np.average(resid ** 2, weights=d.wt)))}
    for c in (2010, 2014, 2018, 2022):
        m = (d.cycle == c).to_numpy()
        out[f"rmse_{c}"] = float(np.sqrt(np.average(resid[m] ** 2, weights=d.wt[m])))
    return out | dict(zip(form, np.round(fit(d, form), 2)))


def main() -> None:
    d = data()
    k = ktis(sorted(d.cycle.unique()))
    print("Kitchen-table conditions by election year (late summer):")
    print(k.round(1).to_string(index=False))
    base = ["m", "pull"]
    lean = base + ["mid_D", "mid_R", "pres_D", "pres_R"]
    forms = {"pull only": base, "H1 lean by kind of year": lean}
    for kk in ("hard_times", "sentiment", "current", "sentiment_chg", "gas_yoy", "inflation", "unemp_chg"):
        forms[f"H2 lean + KTI: {kk}"] = lean + [f"kti_{kk}"]
    forms["H2 KTI instead of kinds: hard_times"] = base + ["kti_hard_times"]
    forms["H3 turnout: pull x surge"] = lean + ["pull_x_surge"]
    forms["H3 turnout: lean x surge"] = lean + ["against_x_surge"]
    forms["H3 turnout: surge alone"] = lean + ["surge"]
    rows = [{"form": n, **score(d, f)} for n, f in forms.items()]
    res = pd.DataFrame(rows)
    res.to_csv(PROC / "undecided_hypotheses.csv", index=False)
    pd.set_option("display.width", 250)
    print("\nWithin-year error on held-out years (lower is better; points):")
    print(res.round(3).to_string(index=False))

    # H3b: do polls miss by MORE where turnout surges (after the best form)?
    b = fit(d, lean)
    X = cols(d, lean)
    D = pd.get_dummies(d.cycle).to_numpy(dtype=float)
    sw = np.sqrt(d.wt.to_numpy())
    full = np.linalg.lstsq(np.column_stack([X, D]) * sw[:, None], d.gap.to_numpy() * sw, rcond=None)[0]
    r2 = (d.gap - np.column_stack([X, D]) @ full) ** 2
    d["abs_surge"] = d.rel_surge.abs()
    d["sbin"] = pd.qcut(d.rel_surge, 5, duplicates="drop")
    print("\nPoll misses by the state's turnout surge beyond the nation's (fifths):")
    print(d.assign(r2=r2).groupby("sbin", observed=True).apply(
        lambda g: pd.Series({"polls": len(g), "rmse": np.sqrt(np.average(g.r2, weights=g.wt)),
                             "mean_gap_toward_out_party": np.average((g.gap - np.average(g.gap, weights=g.wt)) * g.out_party, weights=g.wt)}),
        include_groups=False).round(2).to_string())
    print("\nBy the NATIONAL turnout surge (each year vs 4 years earlier):")
    yr = d.assign(r2=r2).groupby("cycle").apply(lambda g: pd.Series({
        "nat_surge": g.nat_surge.iloc[0], "rmse": np.sqrt(np.average(g.r2, weights=g.wt)),
        "flat_miss_toward_out": np.average(g.gap, weights=g.wt) * g.out_party.iloc[0]}), include_groups=False)
    print(yr.round(3).to_string())
    print("correlation, national surge vs polling spread:", round(yr.nat_surge.corr(yr.rmse), 2),
          "| vs flat miss toward the out-party:", round(yr.nat_surge.corr(yr.flat_miss_toward_out), 2))


if __name__ == "__main__":
    main()
