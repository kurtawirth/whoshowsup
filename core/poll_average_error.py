"""How accurate is a race's poll average ~6 weeks before the election?

From 538's raw_polls (1998-2022, results known): for every D-vs-R general-
election race, average the polls taken at least `days_out` days before the
election (42 = Sept 22) -- using the same rules as the 2026 model
(partisan polls corrected by the historical bias and given half weight).
Then compare with the actual margin.

We fit  error_sd(n) = sqrt(floor^2 + spread^2 / n_eff)
  floor   error that no amount of polling removes (late shifts, shared misses)
  spread  the per-poll noise that averaging many polls washes out
by office. The race model uses this to decide how far to trust a poll average
over the fundamentals prior.
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
from poll_bias_history import load as load_polls  # noqa: E402  (same D-R filtering)

PARTISAN_BIAS = {"D": 3.4, "R": -4.4}   # 2018-2022 estimates from poll_bias_history.py
PARTISAN_WEIGHT = 0.5


def race_averages(days_out: int = 42, window: int = 58) -> pd.DataFrame:
    d = pd.read_csv(ROOT / "data" / "raw" / "fte" / "raw_polls.csv", low_memory=False)
    d = d[d["type_simple"].isin(["Sen-G", "Gov-G", "House-G"])]
    d = d[d["cand1_party"].isin(["DEM", "REP"]) & d["cand2_party"].isin(["DEM", "REP"]) & (d["cand1_party"] != d["cand2_party"])]
    sign = np.where(d["cand1_party"] == "DEM", 1, -1)
    d = d.assign(poll=sign * d["margin_poll"], actual=sign * d["margin_actual"])
    d = d[(d["time_to_election"] >= days_out) & (d["time_to_election"] <= days_out + window)]
    side = d["partisan"].map({"DEM": "D", "REP": "R"})
    d["adj"] = d["poll"] - side.map(PARTISAN_BIAS).fillna(0)
    d["w"] = np.where(side.notna(), PARTISAN_WEIGHT, 1.0)
    g = d.groupby(["race", "type_simple", "cycle"])
    out = pd.DataFrame({
        "avg": g.apply(lambda x: np.average(x["adj"], weights=x["w"]), include_groups=False),
        "actual": g["actual"].first(), "n_eff": g["w"].sum(),
    }).reset_index()
    out["error"] = out["avg"] - out["actual"]
    return out


def fit(errors: np.ndarray, n: np.ndarray) -> tuple[float, float]:
    def nll(p):
        floor, spread = np.exp(p)
        v = floor ** 2 + spread ** 2 / n
        return 0.5 * np.sum(np.log(v) + errors ** 2 / v)
    r = minimize(nll, x0=np.log([4, 5]), method="Nelder-Mead")
    return tuple(np.exp(r.x))


def main(days_out: int = 42) -> pd.DataFrame:
    """Error of poll averages built from polls taken at least `days_out` days before
    the election -- i.e. what we know on a forecast date that far out."""
    a = race_averages(days_out)
    rows = []
    for office in ["Sen-G", "Gov-G", "House-G"]:
        x = a[a["type_simple"] == office]
        floor, spread = fit(x["error"].to_numpy(), x["n_eff"].to_numpy())
        rows.append({"office": office, "races": len(x), "mean_error_D": x["error"].mean(),
                     "floor": floor, "spread": spread,
                     "sd_1_poll": np.hypot(floor, spread), "sd_5_polls": np.hypot(floor, spread / np.sqrt(5))})
    res = pd.DataFrame(rows)
    res.to_csv(ROOT / "data" / "processed" / "poll_average_error.csv", index=False)
    return res


if __name__ == "__main__":
    print(main().round(2).to_string(index=False))
