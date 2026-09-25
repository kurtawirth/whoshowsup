"""How much is a candidate-experience edge worth, beyond what the race model already knows?

    .venv/Scripts/python.exe core/experience_effect.py

Takes the race backtest (2018-2024 as of Sept 22) and the experience tiers
(core/candidate_experience.py) and fits, by office, the leftover miss

    miss = actual margin - fundamentals (without the experience term) - national-environment miss

on the tier gap (D tier - R tier), counted everywhere or only near a toss-up
(x exp(-(fundamentals / 12)^2)). Out-of-sample checks (each year predicted from the others)
and the full-simulation backtest settled the model's settings (2026-09-25):

  House     no weight: the gap never helped, with or without the money term (experienced
            challengers mostly run when lean and environment already favor them)
  Senate    no weight: the gap points slightly the wrong way for margins. The old guess of
            1 point per tier improved Senate Brier (0.0456 -> 0.0438) only by making lopsided
            races more lopsided, while Senate margin error rose 5.5 -> 6.1 pts
  Governor  near a toss-up only, ~2.7 points per tier (2.4-3.0 leaving a year out;
            8 -> 5 wrong calls at both dates). Governors have no money term (not in FEC data),
            which may be why experience carries information here.

Writes data/processed/experience_effect.csv (all-years and leave-one-year-out weights).
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC, OUT = ROOT / "data" / "processed", ROOT / "midterms_2026" / "outputs"
KEY = ["year", "office", "state_po", "district", "special"]
WIDTH = 12.0


def data() -> pd.DataFrame:
    bt = pd.read_csv(OUT / "backtest_race_forecasts.csv")
    ce = pd.read_csv(PROC / "candidate_experience.csv")
    t = ce.groupby(KEY + ["side"])["tier"].max().unstack("side").rename(columns={"D": "tier_D", "R": "tier_R"})
    df = bt.merge(t.reset_index(), on=KEY, how="left")
    df = df[df["race_type"] == "standard"].copy()
    df["gap"] = (df["tier_D"] - df["tier_R"]).fillna(0)
    base = df["fundamentals_mean"] - df.get("quality_adj", 0.0)
    df["miss"] = df["actual"] - base - df["env_miss"]
    df["x_all"] = df["gap"]
    df["x_close"] = df["gap"] * np.exp(-(base / WIDTH) ** 2)
    return df


def slope(d: pd.DataFrame, x: str) -> float:
    den = (d[x] ** 2).sum()
    return float((d[x] * d["miss"]).sum() / den) if den > 0 else 0.0


def main() -> None:
    df = data()
    rows = []
    for office, g in df.groupby("office"):
        for form in ("x_all", "x_close"):
            pred = pd.Series(0.0, index=g.index)
            for y in g["year"].unique():
                b = slope(g[g["year"] != y], form)
                rows.append({"office": office, "form": form, "left_out": y, "b": b})
                pred[g["year"] == y] = b * g.loc[g["year"] == y, form]
            rows.append({"office": office, "form": form, "left_out": "none", "b": slope(g, form),
                         "mse_before": np.mean(g["miss"] ** 2), "mse_after_oos": np.mean((g["miss"] - pred) ** 2)})
    out = pd.DataFrame(rows)
    print(out[out["left_out"] == "none"].round(3).to_string(index=False))
    print("\nLeaving one year out:\n", out[out["left_out"] != "none"].pivot_table(
        index=["office", "form"], columns="left_out", values="b").round(2).to_string())
    out.to_csv(PROC / "experience_effect.csv", index=False)


if __name__ == "__main__":
    main()
