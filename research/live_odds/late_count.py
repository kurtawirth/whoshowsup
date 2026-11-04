"""The last stretch of a count: does the live odds' 95% cutoff help, or should the votes still out count until the end?

live.js liveOdds treated a race at 95% counted as nearly final (the current margin, give or take half a point), while
below 95% it estimated the uncounted vote from the counties still out. So a race could jump from a high chance to
under 1% by crossing that line (Mississippi's and Louisiana's Senate races on election night 2026). This replays the
2018-2024 Senate and governor counts (calibrate.py, with the same forecasts, replays and skews) at 90-99% counted and
scores three versions against who won, on every race and on the races still within 3 points at that moment:

    cutoff     today's page: at 95%+, the margin so far +/- 0.5
    remaining  the county math all the way: what's counted, plus the votes still out at their benchmarks and miss
    whole      for races without county results: the whole-count math, as below 95% (no votes-left term)

    .venv/Scripts/python.exe research/live_odds/late_count.py
"""
import numpy as np
import pandas as pd
from scipy.special import ndtr

import calibrate as cal

cal.FRACS = [0.90, 0.93, 0.95, 0.97, 0.99]
COUNTY = (6.0, 2.0, 0.5)   # the weights live.js uses for races with county results
WHOLE = (0.5, 6.0, 0.5)    # and for races judged on the whole count


def score(p, won):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return {"logloss": -np.mean(won * np.log(p) + (1 - won) * np.log(1 - p)), "brier": np.mean((p - won) ** 2),
            "said": np.mean(np.maximum(p, 1 - p)), "fav_won": np.mean((p >= 0.5) == won), "n": len(p)}


def main() -> None:
    R = cal.races()
    rows, kept = [], []
    for skew in cal.SKEWS:
        S = pd.DataFrame([{**cal.summarize(race, p, nc, m, E), "frac": f, "race": race["id"], "year": race["year"]}
                          for race in R for _ in range(cal.REPLAYS) for f, p, nc, m, E in cal.replay(race, skew)])
        S["remaining"] = cal.estimate(S, *COUNTY[:2], True, COUNTY[2])
        S["whole"] = cal.estimate(S, *WHOLE[:2], False, WHOLE[2])
        S["final"] = np.clip(ndtr(S["mc"] / 0.5), 1e-4, 1 - 1e-4)
        # today's page: below 95% the county or whole-count math, at 95% and up the margin so far
        S["cutoff"] = np.where(S["f"] >= 0.95, S["final"], S["remaining"])
        S["skew"] = skew
        kept.append(S)
    S = pd.concat(kept, ignore_index=True)
    S["won"] = S["won"].astype(float)
    S["band"] = pd.cut(S["f"], [0.0, 0.92, 0.94, 0.96, 0.98, 1.01], labels=["~90%", "~93%", "~95%", "~97%", "~99%"])
    S["close"] = S["mc"].abs() < 3
    print(f"{len(R)} races, {S['race'].nunique()} replayed; {len(S):,} moments; {int(S['close'].sum()):,} within 3 points")
    late = S[S["f"] >= 0.95]
    for name, part in [("all races, 95%+ counted", late), ("within 3 points, 95%+ counted", late[late["close"]]),
                       ("within 1 point, 95%+ counted", late[late["mc"].abs() < 1])]:
        won = part["won"].to_numpy()
        for v in ("cutoff", "remaining", "whole"):
            rows.append({"group": name, "version": v, **score(part[v].to_numpy(), won)})
    tab = pd.DataFrame(rows)
    print(tab.round(4).to_string(index=False))
    # the worst skew: the answer shouldn't depend on the assumed early-ballot lean
    wk = []
    for skew, part in late[late["close"]].groupby("skew"):
        won = part["won"].to_numpy()
        wk.append({"skew": skew, **{v: score(part[v].to_numpy(), won)["logloss"] for v in ("cutoff", "remaining", "whole")}})
    print(pd.DataFrame(wk).round(4).to_string(index=False))
    # leave one year out: each year on its own
    yr = []
    for y, part in late[late["close"]].groupby("year"):
        won = part["won"].to_numpy()
        yr.append({"year": y, "n": len(part), **{v: score(part[v].to_numpy(), won)["logloss"] for v in ("cutoff", "remaining", "whole")}})
    print(pd.DataFrame(yr).round(4).to_string(index=False))
    # calibration of each version, late and close
    part = late[late["close"]]
    for v in ("cutoff", "remaining"):
        p = part[v].to_numpy()
        c = pd.DataFrame({"p": np.maximum(p, 1 - p), "w": (p >= 0.5) == part["won"].to_numpy()})
        c["bin"] = pd.cut(c["p"], [0.5, 0.7, 0.9, 0.99, 1.0001], right=False)
        print(v, "said vs. won, within 3 points at 95%+:")
        print(c.groupby("bin", observed=True).agg(n=("w", "size"), said=("p", "mean"), won=("w", "mean")).round(3).to_string())
    # the jump itself: how far a race's chance moves as its count crosses 95%
    a, b = S[S["frac"] == 0.93], S[S["frac"] == 0.97]
    key = ["race", "skew"]
    n = a.groupby(key).cumcount()
    a2, b2 = a.assign(k=n), b.assign(k=b.groupby(key).cumcount())
    m = a2.merge(b2, on=key + ["k"], suffixes=("_a", "_b"))
    m = m[m["mc_a"].abs() < 3]
    for v in ("cutoff", "remaining"):
        print(f"{v}: median change in chance from 93% to 97% counted, races within 3 points: {np.median(np.abs(m[v + '_b'] - m[v + '_a'])):.3f}; "
              f"share moving 25+ points: {np.mean(np.abs(m[v + '_b'] - m[v + '_a']) >= 0.25):.3f}")
    tab.to_csv(cal.OUT / "late_count.csv", index=False)


if __name__ == "__main__":
    main()
