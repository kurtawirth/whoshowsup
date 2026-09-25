"""Candidate ideology: how far each nominee sits from the middle of their own party.

    .venv/Scripts/python.exe core/candidate_ideology.py

Source: Adam Bonica's Database on Ideology, Money in Politics, and Elections (DIME), public
version 4.0 (Stanford University Libraries, 1979-2024, ODC-BY 1.0), recipients file,
data/raw/dime/dime_recipients_1979_2024.csv.gz. Each candidate's CFscore places them on a
left-right scale from who gives them money.

For a nominee in year Y we only use a score from an EARLIER cycle (their latest dynamic
CFscore before Y): that is all a forecaster would have had, and all we have for 2026 (DIME
ends in 2024). First-time candidates therefore have no score; about half of nominees do,
mostly incumbents and returning candidates.

  extremity = how much more liberal (Democrats) or conservative (Republicans) than their
              party's median House/Senate nominee that year, in CFscore units; 0 if unknown
  ideology_gap = extremity(R) - extremity(D)   (positive = the Republican is further out)

Nominees are linked by FEC candidate ID (core/fec_money.py's matching). Writes
data/processed/candidate_ideology.csv (one row per race).
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
import fec_money  # noqa: E402

PROC, RAW = ROOT / "data" / "processed", ROOT / "data" / "raw" / "dime"
YEARS = [2018, 2020, 2022, 2024, 2026]
KEY = ["office", "state_po", "district", "special"]


def dime() -> pd.DataFrame:
    d = pd.read_csv(RAW / "dime_recipients_1979_2024.csv.gz", low_memory=False,
                    usecols=["cycle", "seat", "Cand.ID", "recipient.cfscore.dyn"])
    d = d[d["Cand.ID"].notna() & d["recipient.cfscore.dyn"].notna() & d["seat"].isin(["federal:house", "federal:senate"])]
    return d.rename(columns={"Cand.ID": "cand_id", "recipient.cfscore.dyn": "cf"})


def build(year: int, d: pd.DataFrame) -> pd.DataFrame:
    nom = fec_money.match(fec_money.nominees(year), fec_money.candidates(year), year)
    prior = d[d["cycle"] < year].sort_values("cycle").groupby("cand_id").tail(1).set_index("cand_id")["cf"]
    nom["cf"] = nom["cand_id"].map(prior)
    med = nom.groupby("side")["cf"].median()
    sign = np.where(nom["side"] == "D", -1.0, 1.0)  # more liberal (D) / more conservative (R) = more extreme
    nom["extremity"] = (sign * (nom["cf"] - nom["side"].map(med))).fillna(0.0)
    nom["scored"] = nom["cf"].notna()
    g = nom.groupby(KEY + ["side"]).agg(ext=("extremity", "max"), scored=("scored", "any")).unstack("side")
    out = pd.DataFrame({"ext_D": g[("ext", "D")], "ext_R": g[("ext", "R")],
                        "scored_D": g[("scored", "D")], "scored_R": g[("scored", "R")]}).reset_index()
    out["ideology_gap"] = out["ext_R"].fillna(0) - out["ext_D"].fillna(0)
    return out.assign(year=year)


def effect(width: float = 12.0) -> pd.DataFrame:
    """Fit the House ideology weight on the backtest's leftover miss, near a toss-up only:
    miss = b * ideology_gap * exp(-(fundamentals / width)^2); all years and leaving each out."""
    bt = pd.read_csv(ROOT / "midterms_2026" / "outputs" / "backtest_race_forecasts.csv")
    ig = pd.read_csv(PROC / "candidate_ideology.csv")
    df = bt.merge(ig, on=["year"] + KEY, how="left")
    df = df[(df["race_type"] == "standard") & (df["office"] == "HOUSE")].copy()
    base = df["fundamentals_mean"] - df.get("ideology_adj", 0.0)
    df["miss"] = df["actual"] - base - df["env_miss"]
    df["x"] = df["ideology_gap"].fillna(0) * np.exp(-(base / width) ** 2)
    slope = lambda g: float((g["x"] * g["miss"]).sum() / (g["x"] ** 2).sum())
    rows = [{"office": "HOUSE", "left_out": "none", "b": slope(df)}]
    rows += [{"office": "HOUSE", "left_out": y, "b": slope(df[df["year"] != y])} for y in sorted(df["year"].unique())]
    out = pd.DataFrame(rows)
    out.to_csv(PROC / "ideology_effect.csv", index=False)
    print(out.round(2).to_string(index=False))
    return out


def update_current() -> None:
    """Daily run: recompute 2026 (nominees can change); past years stay."""
    path = PROC / "candidate_ideology.csv"
    cur = build(2026, dime())
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=cur.columns)
    pd.concat([old[old["year"] != 2026], cur], ignore_index=True).to_csv(path, index=False)


def main() -> None:
    d = dime()
    frames = []
    for y in YEARS:
        df = build(y, d)
        print(f"{y}: {len(df)} races; D scored {df['scored_D'].mean():.0%}, R scored {df['scored_R'].mean():.0%}; "
              f"gap sd {df['ideology_gap'].std():.2f}", flush=True)
        frames.append(df)
    pd.concat(frames, ignore_index=True).to_csv(PROC / "candidate_ideology.csv", index=False)
    print("wrote", PROC / "candidate_ideology.csv")
    effect()


if __name__ == "__main__":
    main()
