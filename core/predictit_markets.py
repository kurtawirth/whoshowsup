"""PredictIt prices for the 2026 midterms, matched to our races. DISPLAY ONLY -- never a model input.

    .venv/Scripts/python.exe core/predictit_markets.py            # fetch today's prices
    .venv/Scripts/python.exe core/predictit_markets.py --offline  # re-parse today's saved file

Source: PredictIt's free market-data feed (https://www.predictit.org/api/marketdata/all/), which PredictIt
makes available for non-commercial use with PredictIt credited as the source. One request per daily run
(PredictIt refreshes it every 60 seconds and asks for no more than one request a minute).
Kalshi and Polymarket are not used: their terms forbid republishing or automated collection of their data.

Each market's "Yes" contracts trade separately and PredictIt's fees push their prices to add up to a bit
more than $1, so a race's chance is each contract's price divided by the sum. Many House markets barely
trade (no trades, offers from 2 to 99 cents), so a contract's price is the midpoint of its best offers
only when they are close together; otherwise it's treated as unknown and, if the race's chance can't be
pinned down, the race is left out rather than shown with a meaningless number.

Output: data/processed/markets_predictit.csv, one row per race and date (history kept across days):
    date, race_id, p_dem (chance for the side our forecast calls "Democratic" -- the independent where we
    count one on the Democratic side), market_id, market, url
Race ids "control-house" and "control-senate" hold the chamber-control markets.
"""
from pathlib import Path
import json
import re
import sys

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "predictit"
PROC = ROOT / "data" / "processed"
OUT = PROC / "markets_predictit.csv"
FEED = "https://www.predictit.org/api/marketdata/all/"
MAX_SPREAD = 0.15   # widest gap between the best buy and sell offers we still treat as a price
LONGSHOT = 0.03     # a contract offered at 3 cents or less with no bids is priced at half its offer

STATES = json.loads((ROOT / "site" / "src" / "data" / "states.json").read_text(encoding="utf-8"))["names"]
POSTAL = {name.lower(): po for po, name in STATES.items()}


def fetch(day: str) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    r = requests.get(FEED, timeout=60, headers={"Accept": "application/json"})
    r.raise_for_status()
    data = r.json()
    (RAW / f"marketdata_{day}.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def price(c: dict) -> float | None:
    """A contract's price, or None when its market is too thin to say."""
    ask, bid = c.get("bestBuyYesCost"), c.get("bestSellYesCost")
    if ask is not None and bid is not None and ask - bid <= MAX_SPREAD:
        return (ask + bid) / 2
    if ask is not None and bid is None and ask <= LONGSHOT:
        return ask / 2
    return None


def race_of(name: str) -> str | None:
    """Our race id for a PredictIt market name, before checking it exists."""
    n = name.lower()
    if "2026" not in n:
        return None
    if re.search(r"which party will (win|control) the (house|senate)( in| after)", n):
        return "control-house" if "house" in n else "control-senate"
    m = re.search(r"us senate (special )?election in ([a-z ]+?)\?", n)
    if m:
        return f"senate-{POSTAL.get(m.group(2).strip(), '??').lower()}" + ("-special" if m.group(1) else "")
    m = re.search(r"election for governor of ([a-z ]+?)\?", n)
    if m:
        return f"governor-{POSTAL.get(m.group(1).strip(), '??').lower()}"
    m = re.search(r"us house (?:election|race) in ([a-z ]+?)'s (\d+)(?:st|nd|rd|th) district", n)
    if m:
        return f"house-{POSTAL.get(m.group(1).strip(), '??').lower()}-{m.group(2)}"
    return None


def _last(s) -> str:
    words = [w for w in str(s).split(";")[0].split() if not re.fullmatch(r"(Jr\.?|Sr\.?|I{2,3})", w)]
    return words[-1].lower() if words else ""


def our_side(market: dict, race: dict | None) -> str | None:
    """Which contract is the side our forecast calls Democratic (p_dem)."""
    names = [c["shortName"] for c in market["contracts"]]
    if race is None:  # chamber control
        return "Democratic"
    ind_d = race["race_type"] == "independent" and bool(race.get("rep_candidate"))
    if "Democratic" in names or "Independent" in names:
        return "Independent" if ind_d else "Democratic"
    # candidate-named market (e.g. governor of California): match the Democratic side's surname
    who = _last(race["race_note"] if ind_d else race.get("dem_candidate"))
    return next((n for n in names if who and who in n.lower()), None)


def chance(market: dict, side: str) -> float | None:
    prices = {c["shortName"]: price(c) for c in market["contracts"] if c.get("status", "Open") == "Open"}
    if side not in prices:
        return None
    mine, others = prices[side], [v for k, v in prices.items() if k != side]
    if mine is not None and all(v is not None for v in others):
        return mine / (mine + sum(others))
    if mine is None and all(v is not None for v in others):
        return max(0.0, min(1.0, 1 - sum(others)))
    if mine is not None:
        return mine  # a rival is too thin to price: fall back to the raw price
    return None


def parse(data: dict, day: str) -> pd.DataFrame:
    races = {r["race_id"]: r for r in json.loads((ROOT / "site" / "src" / "data" / "races.json").read_text(encoding="utf-8"))}
    rows = []
    for m in data["markets"]:
        rid = race_of(m["name"])
        if rid is None:
            continue
        race = None
        if not rid.startswith("control-"):
            if rid not in races and f"{rid}-special" in races:  # e.g. Florida's only 2026 Senate race is the special
                rid = f"{rid}-special"
            race = races.get(rid)
            if race is None:
                print(f"  no race for PredictIt market {m['id']}: {m['name']}")
                continue
        side = our_side(m, race)
        p = chance(m, side) if side else None
        if p is None:
            continue
        rows.append({"date": day, "race_id": rid, "p_dem": round(p, 4), "market_id": m["id"],
                     "market": m["name"], "url": m["url"]})
    return pd.DataFrame(rows)


def main(offline: bool = False, day: str | None = None) -> pd.DataFrame:
    day = day or pd.Timestamp.today().strftime("%Y-%m-%d")
    path = RAW / f"marketdata_{day}.json"
    data = json.loads(path.read_text(encoding="utf-8")) if offline else fetch(day)
    today = parse(data, day)
    hist = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame(columns=today.columns)
    hist = pd.concat([hist[hist["date"] != day], today], ignore_index=True).sort_values(["date", "race_id"])
    hist.to_csv(OUT, index=False)
    print(f"PredictIt: {len(today)} races priced on {day} "
          f"({(today['race_id'].str.startswith('house-')).sum()} House, {(today['race_id'].str.startswith('senate-')).sum()} Senate, "
          f"{(today['race_id'].str.startswith('governor-')).sum()} governor, {(today['race_id'].str.startswith('control-')).sum()} control)")
    return today


if __name__ == "__main__":
    main(offline="--offline" in sys.argv)
