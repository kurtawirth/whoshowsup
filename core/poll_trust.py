"""How much to trust a race's poll average, fit on full-season polls (538's lists, 2018-2024).

    .venv/Scripts/python.exe core/poll_trust.py [days_out]

The race model weighs a poll average against the fundamentals by its expected error:

    error_sd(n_eff) = sqrt(floor^2 + spread^2 / n_eff)

core/poll_average_error.py fits that on raw_polls.csv, which keeps only each campaign's last ~60 days,
so as of Sept 22 it sees only polls from ~Aug 8 on. The live model counts every poll of the last 100
days in n_eff, so it saw "more polling" than the fit was calibrated on and trusted poll averages more
than the evidence supports. Here each race's average and n_eff are built exactly as the live model
builds them (same corrections, 14-day half-life inside the average, n_eff = quality-weighted count of
polls in the last 100 days), from polls that ended at least `days_out` days before the election.

Findings (2026-09-28): the fit is unstable -- four cycles are too few races to tell a poll average's
shared miss (floor) from its per-poll noise (spread); leaving out 2018 or 2022 sends the spread to ~0
(averaging more polls barely helped in those years). In the backtest (full-season polls counted as the
live model counts them), these fits did worse than the current ones (Brier 0.0288 -> 0.0292), and the
current fits with live-style counting did as well as the standard backtest (0.0288 vs 0.0289): the live
model is not over-trusting its poll averages. Not used; the backtest keeps --trust=full to rerun it.

Writes data/processed/poll_trust.csv: floor and spread by office, all four cycles and leaving each out.
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
sys.path.insert(0, str(ROOT / "midterms_2026" / "models"))
import race_model as rm  # noqa: E402

KIND = {2018: "mid_Rpres", 2020: "pres_Rpres", 2022: "mid_Dpres", 2024: "pres_Dpres"}
OFFICES = ("HOUSE", "SEN", "GOV")


def race_averages(days_out: int = 42) -> pd.DataFrame:
    d = pd.read_csv(PROC / "poll_archive_538.csv")
    d = d[(d.days >= days_out) & ((d.dem_pct + d.rep_pct) >= 60)].copy()
    d["race_id"] = d.cycle.astype(str) + d.office + d.state_po + d.district.astype(str) + d.special.astype(str)
    d["partisan"] = d.partisan.map({"DEM": "D", "REP": "R"}).fillna("")
    d["margin"] = rm.two_party(d.dem_pct, d.rep_pct)
    d["undecided"] = rm.undecided_share(d.dem_pct, d.rep_pct)
    bias = np.array([rm.PARTISAN_BIAS[o].get(p, 0.0) for o, p in zip(d.office, d.partisan)])
    adj = np.zeros(len(d))
    for c, g in d.groupby("cycle"):
        i = d.index.get_indexer(g.index)
        adj[i] = (rm.undecided_shift(g.margin, g.undecided, KIND[c], typical=rm.typical_share(g.race_id, g.undecided))
                  + rm.pollster_house_adj(g.pollster, f"h_loo_{c}", races=g.race_id)).to_numpy()
    d["adj"] = d.margin - bias + adj
    age = (d.days - days_out).clip(lower=0)
    quality = (np.sqrt(d.sample_size.fillna(600).clip(200, 3000) / 600)
               * d.population.fillna("").str.lower().map(rm.POP_WEIGHT).fillna(0.8)
               * np.where(d.partisan != "", rm.PARTISAN_WEIGHT, 1.0))
    d["w"] = 0.5 ** (age / rm.POLL_HALF_LIFE_DAYS) * quality
    d["q"] = np.where(age <= rm.POLL_WINDOW_DAYS, 1.0, 0.5 ** ((age - rm.POLL_WINDOW_DAYS) / 30)) * quality
    d["actual"] = rm.two_party(d.actual_dem, d.actual_rep)
    g = d.groupby(["cycle", "office", "race_id"])
    out = pd.DataFrame({"avg": g.apply(lambda x: np.average(x.adj, weights=x.w), include_groups=False),
                        "actual": g.actual.first(), "n_eff": g.q.sum(), "polls": g.size()}).reset_index()
    out["error"] = out.avg - out.actual
    # the national miss is modeled separately (the environment draws), as in poll_average_error.py
    return out


def fit(errors: np.ndarray, n: np.ndarray) -> tuple[float, float]:
    def nll(p):
        floor, spread = np.exp(p)
        v = floor ** 2 + spread ** 2 / n
        return 0.5 * np.sum(np.log(v) + errors ** 2 / v)
    r = minimize(nll, x0=np.log([4, 5]), method="Nelder-Mead")
    return tuple(np.exp(r.x))


def fit_pooled(x: pd.DataFrame) -> tuple[dict, float]:
    """One per-poll spread shared by all offices, a floor per office (four cycles are too few races to
    pin down both numbers for each office separately: the spread swings from 0 to 10)."""
    idx = x.office.map({o: i for i, o in enumerate(OFFICES)}).to_numpy()
    e, n = x.error.to_numpy(), x.n_eff.to_numpy()

    def nll(p):
        floors, spread = np.exp(p[:3]), np.exp(p[3])
        v = floors[idx] ** 2 + spread ** 2 / n
        return 0.5 * np.sum(np.log(v) + e ** 2 / v)
    r = minimize(nll, x0=np.log([6, 6, 6, 6]), method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-4, "fatol": 1e-6})
    return dict(zip(OFFICES, np.exp(r.x[:3]))), float(np.exp(r.x[3]))


def main(days_out: int = 42) -> pd.DataFrame:
    a = race_averages(days_out)
    rows = []
    for left_out in ["none", 2018, 2020, 2022, 2024]:
        x = a if left_out == "none" else a[a.cycle != left_out]
        floors, spread = fit_pooled(x)
        for o in OFFICES:
            y = x[x.office == o]
            rows.append({"days_out": days_out, "left_out": left_out, "office": o, "races": len(y),
                         "median_n_eff": float(y.n_eff.median()), "floor": floors[o], "spread": spread})
    res = pd.DataFrame(rows)
    res.to_csv(PROC / "poll_trust.csv", index=False)
    return res


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    print(main(int(sys.argv[1]) if len(sys.argv) > 1 else 42).round(2).to_string(index=False))
    old = pd.read_csv(PROC / "poll_average_error.csv")
    print("\ncurrent fit (raw_polls, last ~60 days):")
    print(old[["office", "races", "floor", "spread"]].round(2).to_string(index=False))
