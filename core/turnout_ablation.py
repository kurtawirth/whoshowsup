"""How much do the turnout pieces of the model actually buy us? Backtest ablation, 2018-2024 as of Sept 22.

    .venv/Scripts/python.exe core/turnout_ablation.py

Variants (everything else identical, same random seeds, same close-seat bonus per year):
  full               the model as it runs
  uniform swing      turnout-shaped share a = 0: every district's margin moves by the national swing
  all turnout        a = 1: each party's vote scales with its national vote
  no specials        the national estimate built without the special-elections reading
Writes midterms_2026/outputs/turnout_ablation.csv. Read-only otherwise.
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "midterms_2026" / "models"))
sys.path.insert(0, str(ROOT / "core"))
import race_model as rm  # noqa: E402
import national_env as ne  # noqa: E402
import backtest_races as bt  # noqa: E402

OUT = ROOT / "midterms_2026" / "outputs"


def scores(res: pd.DataFrame) -> dict:
    y = (res["actual"] > 0).astype(float)
    comp = (res["p_dem"] > 0.05) & (res["p_dem"] < 0.95)
    house = res["office"] == "HOUSE"
    return {"brier_all": float(np.mean((res["p_dem"] - y) ** 2)),
            "brier_competitive": float(np.mean((res.loc[comp, "p_dem"] - y[comp]) ** 2)),
            "called_all": float(np.mean((res["p_dem"] > 0.5) == (y == 1))),
            "called_competitive": float(np.mean((res.loc[comp, "p_dem"] > 0.5) == (y[comp] == 1))),
            "competitive_races": int(comp.sum()),
            "margin_mae_house": float(np.mean(np.abs(res.loc[house, "margin_median"] - res.loc[house, "actual"])))}


def main() -> None:
    saved = pd.read_csv(OUT / "backtest_race_forecasts.csv")
    bonus = saved.groupby("year")["close_bonus_used"].first().to_dict()
    base_mean, base_conc, base_load = rm.TURNOUT_SHARE_MEAN, rm.TURNOUT_SHARE_CONC, ne.load
    rows = []
    variants = {"full": {}, "uniform swing (a=0)": {"a": 1e-4}, "all turnout (a=1)": {"a": 1 - 1e-4},
                "no special-elections reading": {"no_specials": True}}
    for name, v in variants.items():
        rm.TURNOUT_SHARE_MEAN, rm.TURNOUT_SHARE_CONC = (v["a"], 1e5) if "a" in v else (base_mean, base_conc)
        if v.get("no_specials"):
            def load_no_specials():
                df = base_load()
                return df.assign(specials_implied=np.nan)
            ne.load = load_no_specials
        else:
            ne.load = base_load
        res, _ = bt.run_all(bonus)
        s = scores(res)
        env = res.groupby("year")["env_miss"].first().abs().mean()
        rows.append({"variant": name, **s, "national_env_mae": float(env)})
        print(name, {k: round(x, 4) for k, x in s.items()}, "national MAE", round(env, 2))
    rm.TURNOUT_SHARE_MEAN, rm.TURNOUT_SHARE_CONC, ne.load = base_mean, base_conc, base_load
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "turnout_ablation.csv", index=False)
    print(out.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
