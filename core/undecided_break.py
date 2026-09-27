"""How do undecided voters behave? Estimated from 538's archive of final-two-months race polls.

    .venv/Scripts/python.exe core/undecided_break.py

For each general-election poll (Senate, governor, House; Democrat vs Republican; 1998-2022):

  u      = 100 - D% - R%                      the undecided (and minor-party) share, in points
  m      = two-party poll margin              what the model reads today: 100 * (D - R) / (D + R)
  actual = two-party result margin
  gap    = actual - m

Reading the poll as two-party (the model's current rule) assumes the undecideds split exactly like
the decided voters. Suppose instead that a fraction g of them end up voting for one of the two
nominees, and those who do lean L points (D - R) on their own. Then, to first order,

  gap = g * u/100 * (L - m)

  g = 1, L = m   -> the current rule (undecideds break like the decided vote)
  g = 1, L = 0   -> they split evenly: every race regresses toward a tie as u grows
  g < 1          -> many undecideds stay home or vote minor-party; the share matters less
  L != 0         -> they lean one way; L can depend on the year's context

Fitted as gap = c*m + a*(u/100) + b*(u/100)*m + context terms * (u/100): c is the ordinary pull of
any poll toward a tie (noise), b = -g is the undecided-specific pull, and a (and the context terms)
= g * L. Each race counts once (its polls share the weight), and every fit is checked leaving one
cycle out: the held-out cycle's gaps are predicted from the other cycles.

Context (years available in the archive):
  out_party  +1 when Democrats don't hold the White House, -1 when they do
  midterm    1 in midterm years
  trump      1 when Trump is on the ballot (2016, 2020); 538's archive has no 2024 race polls

Findings (2026-09-27): the undecided-specific pull is about -1 (they split near evenly, not like the
decided vote); in midterms they lean toward the party out of the White House (6 of 7 midterms since
1998; the exception is 2018, Trump's first midterm), hard under Democratic presidents and mildly
under Republican ones; the result's spread grows with the undecided share (squared miss ~ 38 + 264 x
share). The race model applies the "model" form's w-terms (not the
generic m term: its own Bayesian weighting already pulls polls toward the fundamentals).

Writes data/processed/undecided_break.csv (coefficients, all years and leaving each cycle out) and
data/processed/undecided_spread.csv (the spread fit and the typical share of polls 28+ days out).
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
PRES_PARTY = {1998: "D", 2000: "D", 2002: "R", 2004: "R", 2006: "R", 2008: "R", 2010: "D", 2012: "D",
              2014: "D", 2016: "D", 2018: "R", 2020: "R", 2022: "D"}  # White House before the election


def polls(min_days: int = 0, max_days: int = 61) -> pd.DataFrame:
    d = pd.read_csv(ROOT / "data" / "raw" / "fte" / "raw_polls.csv", low_memory=False)
    d = d[d.type_simple.isin(["Sen-G", "Gov-G", "House-G"]) & d.cycle.isin(PRES_PARTY)
          & d.time_to_election.between(min_days, max_days)]
    d = d[d.cand1_party.isin(["DEM", "REP"]) & d.cand2_party.isin(["DEM", "REP"]) & (d.cand1_party != d.cand2_party)]
    dem1 = d.cand1_party == "DEM"
    D, R = np.where(dem1, d.cand1_pct, d.cand2_pct), np.where(dem1, d.cand2_pct, d.cand1_pct)
    Da, Ra = np.where(dem1, d.cand1_actual, d.cand2_actual), np.where(dem1, d.cand2_actual, d.cand1_actual)
    out = pd.DataFrame({
        "cycle": d.cycle.to_numpy(), "race": d.race_id.to_numpy(), "office": d.type_simple.str[:3].to_numpy(),
        "days": d.time_to_election.to_numpy(), "partisan": d.partisan.fillna("").to_numpy(),
        "u": 100 - D - R, "m": 100 * (D - R) / (D + R), "actual": 100 * (Da - Ra) / (Da + Ra)})
    # keep real head-to-heads between the eventual nominees: a two-way race actually happened and the
    # poll isn't mostly undecided (a handful of early multi-candidate polls list 60%+ as other/unsure)
    out = out[(out.u >= 0) & (out.u <= 40) & out.actual.abs().lt(60) & out.m.abs().lt(60)].copy()
    out["gap"] = out.actual - out.m
    out["w"] = out.u / 100
    out["out_party"] = np.where(out.cycle.map(PRES_PARTY) == "R", 1.0, -1.0)
    out["midterm"] = (out.cycle % 4 == 2).astype(float)
    out["trump"] = out.cycle.isin([2016, 2020]).astype(float)
    out["wt"] = 1 / out.groupby(["cycle", "race"])["m"].transform("size")  # each race counts once
    return out.reset_index(drop=True)


FORMS = {
    "none (today's rule)": [],
    "noise pull only": ["m"],
    "+ undecided pull": ["m", "w*m"],
    "+ undecided lean (constant)": ["m", "w*m", "w"],
    "+ lean by context": ["m", "w*m", "w", "w*out_mid", "w*out_pres", "w*trump"],
    # The model's form. Each cycle also gets its own flat miss shared by every race (fitted, then set
    # aside), so the undecided terms are measured only from whether races with MORE undecideds moved
    # more than races with fewer in the same year. Without it, a year-wide polling miss such as 2016
    # and 2020 (a flat miss predicts those years better than one scaled by the undecided share) would
    # be credited to undecideds; that kind of miss is the national generic-ballot correction's job.
    # The lean is estimated separately for each kind of year (midterm or presidential x the president's
    # party), since it isn't symmetric: under Democratic presidents midterm undecideds broke hard
    # Republican (1998, 2010, 2014, 2022); under Republican presidents only mildly Democratic
    # (2002, 2006; 2018 leaned slightly Republican).
    "model": ["m", "w*m", "w*mid_Dpres", "w*mid_Rpres", "w*pres_Dpres", "w*pres_Rpres", "cycle"],
}


def design(d: pd.DataFrame, cols: list[str], cycles=None) -> np.ndarray:
    """Columns for the named terms; "cycle" adds one flat-miss column per cycle in `cycles`."""
    f = {"m": d.m, "w": d.w, "w*m": d.w * d.m,
         "w*out_mid": d.w * d.out_party * d.midterm,        # lean toward the out-party in midterms
         "w*out_pres": d.w * d.out_party * (1 - d.midterm),  # ... and in presidential years
         "w*trump": -d.w * d.trump,
         "w*mid_Dpres": d.w * d.midterm * (d.out_party < 0), "w*mid_Rpres": d.w * d.midterm * (d.out_party > 0),
         "w*pres_Dpres": d.w * (1 - d.midterm) * (d.out_party < 0), "w*pres_Rpres": d.w * (1 - d.midterm) * (d.out_party > 0)}                          # toward the Republican with Trump on the ballot
    named = [f[c] for c in cols if c != "cycle"]
    if "cycle" in cols:
        named += [(d.cycle == c).astype(float) for c in (cycles if cycles is not None else sorted(d.cycle.unique()))]
    return np.column_stack(named) if named else np.zeros((len(d), 0))


def fit(d: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """Coefficients of the named terms (the per-cycle flat misses are fitted but not returned)."""
    if not cols:
        return np.zeros(0)
    X, y, sw = design(d, cols), d.gap.to_numpy(), np.sqrt(d.wt.to_numpy())
    b = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)[0]
    return b[:len([c for c in cols if c != "cycle"])]


def terms(cols: list[str]) -> list[str]:
    return [c for c in cols if c != "cycle"]


def main() -> None:
    d = polls()
    print(f"{len(d):,} polls in {d.groupby(['cycle', 'race']).ngroups:,} races, {d.cycle.nunique()} cycles; "
          f"undecided share median {d.u.median():.0f} pts (middle half {d.u.quantile(.25):.0f}-{d.u.quantile(.75):.0f})")
    rows, oos = [], []
    for name, cols in FORMS.items():
        beta = fit(d, cols)
        rows.append({"form": name, "left_out": "none", **dict(zip(terms(cols), beta))})
        pred = np.zeros(len(d))
        for cyc in sorted(d.cycle.unique()):
            tr, te = d.cycle != cyc, d.cycle == cyc
            b = fit(d[tr], cols)
            rows.append({"form": name, "left_out": cyc, **dict(zip(terms(cols), b))})
            pred[te.to_numpy()] = design(d[te], terms(cols)) @ b if cols else 0.0
        err = d.gap - pred
        oos.append({"form": name, "rmse_oos": np.sqrt(np.average(err ** 2, weights=d.wt)),
                    **{f"rmse_{c}": np.sqrt(np.average(err[d.cycle == c] ** 2, weights=d.wt[d.cycle == c]))
                       for c in (2010, 2014, 2018, 2022, 2016, 2020)}})
    coef = pd.DataFrame(rows)
    coef.to_csv(PROC / "undecided_break.csv", index=False)
    print("\nOut-of-sample error of the poll-vs-result gap (each cycle predicted from the others; points):")
    print(pd.DataFrame(oos).round(2).to_string(index=False))
    print("\nCoefficients, all cycles:")
    print(coef[coef.left_out == "none"].drop(columns="left_out").round(3).to_string(index=False))
    full = coef[(coef.form == "+ lean by context") & (coef.left_out != "none")]
    print("\nLean by context, leaving each cycle out:")
    print(full.drop(columns="form").round(2).to_string(index=False))

    # Do bigger undecided shares make the result less predictable, beyond the expected pull?
    b = fit(d, FORMS["+ lean by context"])
    d["resid"] = d.gap - design(d, FORMS["+ lean by context"]) @ b
    d["ubin"] = pd.cut(d.u, [-0.1, 4, 8, 12, 16, 20, 40])
    # spread around the model's expectation, the year's flat miss removed (that part is the national model's)
    full = FORMS["model"]
    X, sw = design(d, full), np.sqrt(d.wt.to_numpy())
    r2 = (d.gap - X @ np.linalg.lstsq(X * sw[:, None], d.gap.to_numpy() * sw, rcond=None)[0]) ** 2
    X = np.column_stack([np.ones(len(d)), d.w])
    s0, s1 = np.linalg.lstsq(X * sw[:, None], r2.to_numpy() * sw, rcond=None)[0]
    w_ref = float(np.average(d.w[d.days >= 28], weights=d.wt[d.days >= 28]))
    pd.DataFrame([{"s0": s0, "s1": s1, "w_ref": w_ref}]).to_csv(PROC / "undecided_spread.csv", index=False)
    print(f"\nSquared miss = {s0:.1f} + {s1:.1f} x undecided share; typical share 28+ days out {w_ref:.3f}")
    print("\nSpread of what's left, by undecided share:")
    print(d.groupby("ubin", observed=True).apply(
        lambda g: pd.Series({"polls": len(g), "rmse": np.sqrt(np.average(g.resid ** 2, weights=g.wt))}),
        include_groups=False).round(2).to_string())


if __name__ == "__main__":
    main()
