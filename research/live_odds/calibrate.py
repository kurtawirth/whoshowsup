"""How much should a race's own partial count move its live odds? Calibrate the trust weights on real elections.

For every Senate and governor race from 2018 to 2024 we have our model's election-eve forecast (the leave-one-year-out
backtest, midterms_2026/outputs/backtest_race_forecasts_eve.csv) and the final county-by-county result
(data/processed/county_results.parquet). We replay each race's count many times: counties report at their own pace
(big ones slower), and each county's first-counted ballots lean away from its final margin by a state-wide "ballot
type" skew plus its own, fading as it finishes. At 10%, 25%, 50%, 75% and 90% counted we run the live-odds math
exactly as the results page does (site/src/components/live.js liveOdds, `partial`), with county benchmarks built the
way export_site_data.benchmarks builds them (from the previous presidential result, never the race's own), and score
the chance it gives against who actually won.

The trust in a count is sg = a + b * (1 - share counted) points of noise on what the count says about the race's
own miss. We pick (a, b) that minimize log loss, separately for races with county results (Senate, governor) and
races judged on the whole count alone (House), and check calibration.

What's real here: our forecasts, the final results, and where in each state the forecast missed (the geography that
county benchmarks rely on). What's assumed: the counting order and the size of the early-ballot skew, which we can't
observe from final results; the skew is varied (SKEWS) to check the answer holds up.

    .venv/Scripts/python.exe research/live_odds/calibrate.py
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd
from scipy.special import ndtr

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
YEARS = {2018: 2016, 2020: 2016, 2022: 2020, 2024: 2020}  # race year -> presidential year its benchmarks start from
TURNOUT_SHARE = 0.65                                       # race_model.TURNOUT_SHARE_MEAN
LM = json.loads((ROOT / "site" / "src" / "data" / "live_model.json").read_text(encoding="utf-8"))
VS = LM["env_sd"] ** 2 + LM["region_sd"] ** 2 + LM["state_sd"] ** 2  # shared (national, region, state) variance
FRACS = [0.10, 0.25, 0.50, 0.75, 0.90]
REPLAYS = 30
SKEWS = [3.0, 6.0, 9.0]                                    # sd of the state-wide early-ballot lean, in margin points
rng = np.random.default_rng(2026)


def tp(d, r):
    return 100 * (d - r) / (d + r)


def races() -> list[dict]:
    bt = pd.read_csv(ROOT / "midterms_2026" / "outputs" / "backtest_race_forecasts_eve.csv")
    bt = bt[bt["office"].isin(["SEN", "GOV"]) & bt["year"].isin(YEARS) & bt["contested"].astype(bool)
            & (bt["race_type"] == "standard") & ~bt["state_po"].isin(["AK", "CT"])]
    c = pd.read_parquet(ROOT / "data" / "processed" / "county_results.parquet")
    out = []
    for r in bt.itertuples():
        fin = c[(c["year"] == r.year) & (c["state_po"] == r.state_po) & (c["office"] == r.office)
                & (c["special"].astype(bool) == bool(r.special))].set_index("county_fips")
        pres = c[(c["year"] == YEARS[r.year]) & (c["state_po"] == r.state_po) & (c["office"] == "PRES")].set_index("county_fips")
        idx = fin.index.intersection(pres.index)
        if len(idx) < 3 or len(idx) < 0.9 * len(fin):
            continue
        fin, pres = fin.loc[idx], pres.loc[idx]
        keep = (np.isfinite(pres[["dem", "rep"]].to_numpy(float)).all(axis=1) & np.isfinite(fin[["dem", "rep"]].to_numpy(float)).all(axis=1)
                & (pres["dem"] + pres["rep"] > 0).to_numpy() & (fin["dem"] + fin["rep"] > 0).to_numpy())
        if keep.sum() < 3:
            continue
        fin, pres = fin[keep], pres[keep]
        D, R = pres["dem"].to_numpy(float), pres["rep"].to_numpy(float)
        med = float(r.margin_median)
        s = (med / 100 + 1) / 2
        k = s / (1 - s) * R.sum() / D.sum()
        share = (D + R) / (D + R).sum()
        b = TURNOUT_SHARE * tp(k * D, R) + (1 - TURNOUT_SHARE) * (tp(D, R) + (med - tp(D.sum(), R.sum())))
        b = b + (med - float(np.sum(share * b)))
        fd, fr = fin["dem"].to_numpy(float), fin["rep"].to_numpy(float)
        ok = (fd + fr) > 0
        out.append({"id": f"{r.year} {r.state_po} {r.office}{' sp' if r.special else ''}", "year": r.year,
                    "median": med, "sd_tot": max((r.margin_p90 - r.margin_p10) / 2.563, 2.5),
                    "bench": b[ok], "share": share[ok], "V": (fd + fr)[ok], "m": tp(fd, fr)[ok],
                    "actual": tp(fd[ok].sum(), fr[ok].sum())})
    return out


def replay(race: dict, skew_sd: float):
    """One counting night: the counted votes and margins of each county at each target share counted."""
    n = len(race["V"])
    V = race["V"]
    size = np.log10(V / np.median(V))
    delay = rng.uniform(0, 0.3, n)
    speed = rng.uniform(0.6, 2.0, n) * (1 + 0.3 * np.clip(size, -1, 2))  # big counties take longer
    e_state, e_cty = rng.normal(0, skew_sd), rng.normal(0, skew_sd / 2, n)
    E = V.sum() * np.exp(rng.normal(0, 0.08))              # our turnout expectation is off by ~8%
    ts = np.linspace(0, 6, 601)
    fr = np.array([np.sum(V * np.clip((t - delay) / speed, 0, 1)) / V.sum() for t in ts])
    for f in FRACS:
        t = ts[np.searchsorted(fr, f)]
        p = np.clip((t - delay) / speed, 0, 1)
        m = race["m"] + (1 - p) * (e_state + e_cty)          # what's counted so far leans by ballot type, fading
        yield f, p, V * p, m, E


def summarize(race, p, nc, m, E) -> dict:
    """What the page knows at one moment (live.js raceMath): the count, its gap from our forecast, what's left."""
    C = nc.sum()
    mc = 100 * np.sum(nc * m / 100) / C
    left = np.where(p >= 0.05, nc * (1 - p) / np.maximum(p, 1e-9), np.maximum(race["share"] * E - nc, 0))
    U = left.sum()
    return {"C": C, "U": U, "mc": mc, "f": C / (C + U), "own": max(race["sd_tot"] ** 2 - VS, 4.0), "median": race["median"],
            "g_cty": mc - np.sum(nc * race["bench"]) / C, "g_all": mc - race["median"],
            "rem": np.sum(left * race["bench"]) / U if U > 0 else 0.0, "won": race["actual"] > 0}


def estimate(S: pd.DataFrame, a: float, b: float, counties: bool = True, r: float = 0.5) -> np.ndarray:
    """The results page's live chance that the D side wins (live.js liveOdds with `partial`), shared mean 0,
    for every moment in S at once."""
    sg = a + b * (1 - np.minimum(S["f"], 0.95))
    own = S["own"]
    v = 1 / (1 / own + 1 / sg ** 2)
    g = S["g_cty"] if counties else S["g_all"]
    mu, var = v * g / sg ** 2, (v / own) ** 2 * VS + v
    if counties:
        w = S["U"] / (S["C"] + S["U"])
        F = (S["C"] * S["mc"] + S["U"] * (S["rem"] + mu)) / (S["C"] + S["U"])
        sd = np.sqrt(w ** 2 * var + r ** 2)
    else:
        F, sd = S["median"] + mu, np.sqrt(var + r ** 2)
    return np.clip(ndtr(F / sd), 1e-4, 1 - 1e-4).to_numpy()


def main() -> None:
    R = races()
    print(f"{len(R)} Senate and governor races, 2018-2024 ({', '.join(f'{y}: {sum(r['year'] == y for r in R)}' for y in YEARS)})")
    grid = [(a, b) for a in (0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0) for b in (0, 1, 2, 4, 6, 8, 10, 14, 20, 30)]
    rows, moments = [], {}
    for skew in SKEWS:
        S = pd.DataFrame([{**summarize(race, p, nc, m, E), "frac": f, "race": race["id"]}
                          for race in R for _ in range(REPLAYS) for f, p, nc, m, E in replay(race, skew)])
        S = S[ndtr(S["median"] / np.sqrt(S["own"] + VS)).between(0.05, 0.95)].reset_index(drop=True)  # competitive races
        moments[skew] = S
        won = S["won"].to_numpy()
        for counties in (True, False):
            for (a, b), r in [(ab, r) for ab in grid for r in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0)]:
                pr = estimate(S, a, b, counties, r)
                rows.append({"skew": skew, "counties": counties, "a": a, "b": b, "r": r,
                             "logloss": -np.mean(won * np.log(pr) + (1 - won) * np.log(1 - pr)), "brier": np.mean((pr - won) ** 2)})
        print(f"  skew {skew}: {len(S):,} replayed moments in {S['race'].nunique()} competitive races")
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "grid.csv", index=False)
    # the weights that do best on average across the skew scenarios, and how they do in each
    avg = res.groupby(["counties", "a", "b", "r"])["logloss"].agg(["mean", "max"]).reset_index()
    for counties in (True, False):
        print("best", "counties" if counties else "whole count", "(mean over skews; max = worst skew)")
        print(avg[avg["counties"] == counties].sort_values("mean").head(8).round(4).to_string(index=False))
    best = avg.loc[avg.groupby("counties")["mean"].idxmin()]
    cur = {True: (6.0, 2, 0.5), False: (0.5, 6, 0.5)}  # the weights live.js uses (first guess was 1.5+6, 2+10)
    for counties, (a, b, r) in cur.items():
        print("current", "counties" if counties else "whole count", a, b, r,
              avg[(avg["counties"] == counties) & (avg["a"] == a) & (avg["b"] == b) & (avg["r"] == r)][["mean", "max"]].round(4).to_dict("records"))
    # this morning's forecast alone, for comparison (no use of the count)
    for skew, S in moments.items():
        pr = np.clip(ndtr(S["median"] / np.sqrt(S["own"] + VS)), 1e-4, 1 - 1e-4)
        won = S["won"].to_numpy()
        print(f"  forecast only, skew {skew}: logloss {-np.mean(won * np.log(pr) + (1 - won) * np.log(1 - pr)):.4f}")
    # calibration of the chosen weights at the middle skew, by how sure we were and by share counted
    S = moments[6.0]
    cal = []
    for counties in (True, False):
        a, b, r = best[best["counties"] == counties][["a", "b", "r"]].iloc[0]
        pr = estimate(S, a, b, counties, r)
        cal.append(pd.DataFrame({"counties": counties, "frac": S["frac"], "p_fav": np.maximum(pr, 1 - pr),
                                 "fav_won": (pr >= 0.5) == S["won"].to_numpy()}))
    cal = pd.concat(cal)
    cal["bin"] = pd.cut(cal["p_fav"], [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0001], right=False)
    tab = cal.groupby(["counties", "bin"], observed=True).agg(n=("fav_won", "size"), said=("p_fav", "mean"), won=("fav_won", "mean")).reset_index()
    tab.to_csv(OUT / "calibration.csv", index=False)
    print(tab.round(3).to_string(index=False))
    print(cal.groupby(["counties", "frac"]).agg(n=("fav_won", "size"), said=("p_fav", "mean"), won=("fav_won", "mean")).round(3).reset_index().to_string(index=False))


if __name__ == "__main__":
    main()
