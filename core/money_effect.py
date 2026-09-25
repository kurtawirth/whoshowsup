"""How much does a fundraising edge predict, beyond what the race model already knows?

    .venv/Scripts/python.exe core/money_effect.py

Takes the race backtest (2018-2024 as of Sept 22, current model, no money term) and asks:
after the district lean, the national environment, incumbency/personal vote and the
close-seat effect, does the Democrat-vs-Republican money ratio (core/fec_money.py, June 30
reports) explain what's left?

    miss = actual margin - model's fundamentals - national-environment miss
    miss = b[office] * clip(ln((D money + 25k) / (R money + 25k)), -3, 3) * exp(-(fundamentals / 12)^2)

The money gap only counts near a toss-up (the exp term fades it out in safe seats, where
war chests pile up for reasons unrelated to the race) and is capped at about 20-to-1.
Chosen over plainer versions (money everywhere; separate open-seat / incumbent effects)
by out-of-sample error: it cut competitive races' squared miss from 48.8 to 45.5 when each
year was predicted from the other three, with stable coefficients. Fit on all years and
leaving each year out (for the backtest). Writes data/processed/money_effect.csv.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
PROC, OUT = ROOT / "data" / "processed", ROOT / "midterms_2026" / "outputs"
KEY = ["year", "office", "state_po", "district", "special"]


CLIP, WIDTH = 3.0, 12.0


def signal(ratio, fundamentals):
    return np.clip(ratio, -CLIP, CLIP) * np.exp(-(np.asarray(fundamentals) / WIDTH) ** 2)


def data() -> pd.DataFrame:
    bt = pd.read_csv(OUT / "backtest_race_forecasts.csv")
    if "money_log_ratio" in bt:
        bt = bt.drop(columns="money_log_ratio")
    money = pd.read_csv(PROC / "fec_money.csv")
    df = bt.merge(money[KEY + ["money_log_ratio", "dem_money", "rep_money"]], on=KEY, how="inner")
    df = df[df["office"].isin(["HOUSE", "SEN"]) & (df["race_type"] == "standard") & df["money_log_ratio"].notna()].copy()
    # the no-money fundamentals: if the backtest file already includes a money term, take it back out
    base = df["fundamentals_mean"] - df.get("money_adj", 0.0)
    df["fund0"] = base
    df["miss"] = df["actual"] - base - df["env_miss"]
    df["x"] = signal(df["money_log_ratio"], base)
    return df


def fit(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for g, x in df.groupby("office"):
        m = smf.ols("miss ~ x - 1", data=x).fit()
        rows.append({"group": g, "n": int(m.nobs), "b": m.params["x"], "se": m.bse["x"],
                     "sd_before": np.sqrt(np.mean(x["miss"] ** 2)), "sd_after": np.sqrt(m.scale)})
    return pd.DataFrame(rows)


def main() -> None:
    df = data()
    print(f"{len(df)} races with money data; median money D ${df.dem_money.median():,.0f}, R ${df.rep_money.median():,.0f}")
    comp = df["fund0"].abs() < 12
    pred = pd.Series(0.0, index=df.index)
    for y in df["year"].unique():
        b = fit(df[df["year"] != y]).set_index("group")["b"]
        t = df["year"] == y
        pred[t] = df.loc[t, "office"].map(b) * df.loc[t, "x"]
    e0, e1 = df["miss"], df["miss"] - pred
    print(f"Out of sample (each year from the others): competitive races' mean squared miss "
          f"{np.mean(e0[comp] ** 2):.1f} -> {np.mean(e1[comp] ** 2):.1f}; all races {np.mean(e0 ** 2):.1f} -> {np.mean(e1 ** 2):.1f}")
    allf = fit(df).assign(left_out="none")
    print("\nAll years:\n", allf.round(3).to_string(index=False))
    loo = pd.concat([fit(df[df["year"] != y]).assign(left_out=y) for y in sorted(df["year"].unique())])
    print("\nLeaving one year out (b):\n", loo.pivot(index="group", columns="left_out", values="b").round(2).to_string())
    print("\nEach year alone (b):")
    for y in sorted(df["year"].unique()):
        print(y, fit(df[df["year"] == y]).set_index("group")["b"].round(2).to_dict())
    pd.concat([allf, loo]).to_csv(PROC / "money_effect.csv", index=False)


if __name__ == "__main__":
    main()
