"""What if 2026's polls miss the way a past year's did? (Display only: the forecast itself never uses this.)

    .venv/Scripts/python.exe midterms_2026/models/poll_miss_scenarios.py

For each past year since 2012, take how far that year's final polling averages landed from the results
(backtest_race_forecasts_eve.csv: our own poll average for every polled race on Election Eve, minus the actual
two-party margin), state by state:
  - every 2026 race's poll average is moved by its state's miss that year (the year's average miss where the
    state had no polled race), and
  - the national environment moves by the generic ballot's miss that year, beyond the Democratic lean the model
    already subtracts from generic-ballot polls, times the generic ballot's weight in the national estimate.
Then the same simulation engine reruns (10,000 simulations) with everything else unchanged.

Writes outputs/poll_miss_scenarios.csv (one row per year: the misses applied and both chambers' odds) and
outputs/poll_miss_races.csv (each race's Democratic chance in each scenario).
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "midterms_2026" / "models"))
sys.path.insert(0, str(ROOT / "core"))
import race_model as rm  # noqa: E402

OUT, PROC = rm.OUT, rm.PROC
YEARS = [2012, 2014, 2016, 2018, 2020, 2022, 2024]
N = 10_000
SHRINK = 15  # polls' worth of pull toward the year's average miss
INDEPENDENT_RACES = {(2016, "SEN", "AK"), (2018, "SEN", "ME"), (2018, "SEN", "VT"), (2020, "SEN", "AK"),
                     (2022, "SEN", "UT"), (2022, "SEN", "AK"), (2022, "GOV", "AK"), (2024, "SEN", "ME"),
                     (2024, "SEN", "VT"), (2024, "SEN", "NE"), (2014, "SEN", "KS"), (2014, "GOV", "AK")}


def misses() -> tuple[pd.DataFrame, pd.Series]:
    """State-by-year miss of the final poll averages (poll minus result, D-R points; positive = polls
    overstated Democrats), and each year's average across states."""
    d = pd.read_csv(OUT / "backtest_race_forecasts_eve.csv")
    d = d[(d["poll_count"] > 0) & d["poll_avg"].notna() & d["actual"].notna()]
    # races where a major independent made the D-vs-R polls and results incomparable
    d = d[~d.apply(lambda r: (r["year"], r["office"], r["state_po"]) in INDEPENDENT_RACES, axis=1)]
    # one race's miss counts at most +-15 points; a race counts more the more polls it had (up to 30)
    d = d.assign(miss=(d["poll_avg"] - d["actual"]).clip(-15, 15), w=d["poll_count"].clip(upper=30),
                 statewide=d["office"] != "HOUSE")
    wmean = lambda g: np.average(g["miss"], weights=g["w"])
    year_avg = d[d["statewide"]].groupby("year").apply(wmean, include_groups=False)
    # each state's own miss (its statewide races; its polled House races if it had none), pulled toward the
    # year's average in proportion to how few polls it rests on
    rows = []
    for (year, st), g in d.groupby(["year", "state_po"]):
        g = g[g["statewide"]] if g["statewide"].any() else g
        n = g["w"].sum()
        rows.append({"year": year, "state_po": st, "polls": n,
                     "miss": (np.sum(g["w"] * g["miss"]) + SHRINK * year_avg[year]) / (n + SHRINK)})
    return pd.DataFrame(rows), year_avg


def generic_shift() -> pd.Series:
    """How far the national environment moves in each year's scenario."""
    h = pd.read_csv(PROC / "national_history.csv").set_index("year")
    reads = pd.read_csv(OUT / "national_env_reads.csv").set_index("read")
    w = float(reads.loc["generic", "weight"])
    lean_assumed = float(h.loc[2026, "generic_margin"] - reads.loc["generic", "dem_margin"])  # D lean already removed
    miss = h["generic_margin"] - h["house_margin"]
    return -(miss - lean_assumed) * w, miss, lean_assumed


def chambers(live: pd.DataFrame, fixed_r: pd.DataFrame, margin: np.ndarray) -> dict:
    """Both chambers' odds, counted exactly as race_model.simulate counts them."""
    office = live["office"].to_numpy()
    win = margin > 0
    ind = ((live["race_type"] == "independent") & live["rep_candidate"].notna()).to_numpy()
    out = {}
    for off in ("HOUSE", "SEN", "GOV"):
        m = office == off
        fixed_d = int(((fixed_r["office"] == off) & (fixed_r["race_note"] == "D")).sum())
        out[off] = win[m].sum(axis=0) + fixed_d - win[m & ind].sum(axis=0)
    house, sen = out["HOUSE"], 34 + out["SEN"]
    return {"p_house_d": (house >= 218).mean(), "house_median": np.median(house),
            "p_senate_d": (sen >= 51).mean(), "senate_median": np.median(sen), "gov_median": np.median(out["GOV"])}


def main() -> pd.DataFrame:
    races, env, D0, R0 = rm.prepare()
    by_state, year_avg = misses()
    shift, gmiss, lean = generic_shift()
    rows, per_race = [], {}
    for year in [None] + YEARS:
        r = races.copy()
        e = env
        info = {"year": year or "forecast"}
        if year:
            st = by_state[by_state["year"] == year].set_index("state_po")["miss"]
            m = r["state_po"].map(st).fillna(year_avg[year])
            r["poll_avg"] = r["poll_avg"] - m.where(r["poll_avg"].notna())
            e = env + shift[year]
            polled = r[r["office"] != "HOUSE"]
            info.update(statewide_miss=float(year_avg[year]), generic_miss=float(gmiss[year]), env_shift=float(shift[year]),
                        states_with_data=int(polled["state_po"].isin(st.index).sum()))
        live, fixed_r, margin, E, a = rm.run_simulation(r, e, D0, R0, np.random.default_rng(rm.SEED), n_sims=N)
        info.update(chambers(live, fixed_r, margin), nat_median=float(np.median(E)))
        rows.append(info)
        per_race[info["year"]] = pd.Series(live["p_dem"].to_numpy(), index=live.apply(rm.race_id, axis=1))
        print(f"{info['year']}: Senate D {info['p_senate_d']:.0%}, House D {info['p_house_d']:.0%}, national {info['nat_median']:+.1f}")
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "poll_miss_scenarios.csv", index=False)
    pd.DataFrame(per_race).rename_axis("race_id").reset_index().to_csv(OUT / "poll_miss_races.csv", index=False)
    print(f"generic-ballot lean already assumed: D+{lean:.1f}")
    return out


if __name__ == "__main__":
    main()
