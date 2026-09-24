"""Special elections (D vs R) with each one's overperformance.

Source: The Downballot's special-election result sheets (formerly Daily Kos
Elections), one CSV per year in data/raw/downballot/specials_YYYY.csv.
Each row is a state-legislative or congressional special election contested
by both parties, with the district's most recent presidential result.

    overperformance = special-election margin (D-R) - most recent presidential margin (D-R)

A positive number means Democrats beat the district's usual baseline. Specials
are low-turnout, so the average overperformance across many of them is a
direct read on which party's voters are more motivated -- one of the model's
turnout signals.

Output: data/processed/special_elections.csv
"""
from pathlib import Path
import re

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "downballot"
OUT = ROOT / "data" / "processed" / "special_elections.csv"


# The Downballot's live 2025-26 Big Board: one tab per year of results.
LIVE_SHEET = "1JGk1r1VXnxBrAIVHz1C5HTB5jxCO6Zw4QNPivdhyWHw"
LIVE_TABS = {2025: "415249345", 2026: "1173601967"}


def refresh() -> None:
    """Re-download the current cycle's special-election results (older years are final)."""
    for year, gid in LIVE_TABS.items():
        r = requests.get(f"https://docs.google.com/spreadsheets/d/{LIVE_SHEET}/export?format=csv&gid={gid}",
                         timeout=60)
        r.raise_for_status()
        (RAW / f"specials_{year}.csv").write_text(r.text, encoding="utf-8")


def _pct(v) -> float:
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*%", str(v))
    return float(m.group(1)) if m else float("nan")


def parse_year(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, header=None, dtype=str).fillna("")
    hdr_i = raw.index[raw.apply(lambda r: "Date" in r.values and "State" in r.values, axis=1)][0]
    hdr = list(raw.iloc[hdr_i])
    above = list(raw.iloc[hdr_i - 1])  # "Special Election", "2024 Presidential", ...
    body = raw.iloc[hdr_i + 1:]
    col = {name: hdr.index(name) for name in ("Date", "State", "District", "Held By", "Winner")}
    margins = [i for i, h in enumerate(hdr) if h == "Margin"]
    diffs = [i for i, h in enumerate(hdr) if h == "Margin Dif."]
    pres_label = next((a for a in above if "Presidential" in a), "")
    rows = []
    for _, r in body.iterrows():
        date = pd.to_datetime(r[col["Date"]], format="%d-%b-%y", errors="coerce")
        if pd.isna(date):
            continue
        rows.append({
            "date": date, "state_po": r[col["State"]], "district": r[col["District"]].replace(" *", "").strip(),
            "held_by": r[col["Held By"]].strip("()"), "winner": r[col["Winner"]].split(")")[0].strip("( "),
            "flipped": "✓" in r[col["Winner"]],
            "chamber": "US House" if re.match(r"^[A-Z]{2}-(\d+|AL)$", r[col["District"]].strip()) else "state legislature",
            "special_margin": _pct(r[margins[0]]),
            "pres_margin": _pct(r[margins[1]]) if len(margins) > 1 else float("nan"),
            "overperformance": _pct(r[diffs[0]]) if diffs else float("nan"),
            "pres_baseline": pres_label.replace(" Presidential", ""),
        })
    return pd.DataFrame(rows)


def main(refresh_live: bool = False) -> pd.DataFrame:
    if refresh_live:
        refresh()
    df = pd.concat([parse_year(p) for p in sorted(RAW.glob("specials_20*.csv"))], ignore_index=True)
    df = df.dropna(subset=["special_margin"]).sort_values("date").reset_index(drop=True)
    df["year"] = df["date"].dt.year
    df.to_csv(OUT, index=False)
    s = df.groupby("year").agg(n=("overperformance", "count"), mean_overperf=("overperformance", "mean"),
                              median_overperf=("overperformance", "median"), baseline=("pres_baseline", "first"))
    return s


if __name__ == "__main__":
    import sys
    print(main("--refresh" in sys.argv).round(1).to_string())
