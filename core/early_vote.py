"""Early and absentee voting, 2026: daily statewide counts from civicAPI (civicapi.org).

    .venv/Scripts/python.exe core/early_vote.py

civicAPI's early-vote tracker (free for any use, attribution requested) compiles state election offices'
reports: mail ballots requested and returned and in-person early votes, by party registration where the
state records party. It serves each day's snapshot (?date=YYYY-MM-DD), so the history is filled in
once and then extended each morning; the last few days are re-read in case a state revised them.

Display only: early votes are not a model input (party registration is not a vote, and who votes early
changes from year to year).

Output: data/processed/early_vote.csv -- one row per state, category and snapshot date: total ballots
and, where the state records party, registered Democrats, Republicans and everyone else.
"""
from pathlib import Path
import json
import time

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "civicapi"
OUT = ROOT / "data" / "processed" / "early_vote.csv"
API = "https://civicapi.org/api/v2/early-vote"
HEADERS = {"User-Agent": "politics-forecast-research/0.1 (personal project; kurtawirth)"}
STATES = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
          "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()
START = pd.Timestamp("2026-09-01")
REFRESH_DAYS = 3  # re-read the latest few days each run
CATEGORIES = ("requested", "returned", "inperson")


def _get(url: str):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"civicAPI unavailable: {url}")


def capabilities() -> dict:
    caps = {}
    for st in STATES:
        c = _get(f"{API}/{st}/capabilities")
        if c:
            caps[st] = c
        time.sleep(0.15)
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "capabilities.json").write_text(json.dumps(caps, indent=1), encoding="utf-8")
    return caps


def snapshot(st: str, cat: str, day: pd.Timestamp) -> dict | None:
    d = _get(f"{API}/{st}/{cat}?date={day:%Y-%m-%d}")
    if not d or "statewide_total" not in d:
        return None
    tot = {k: int(v.get("votes", 0) or 0) for k, v in d["statewide_total"].items()}
    party = any(k in tot for k in ("Democratic", "Republican"))
    dem, rep = tot.get("Democratic", 0), tot.get("Republican", 0)
    total = sum(tot.values())
    return {"date": d.get("snapshot_date", f"{day:%Y-%m-%d}"), "state_po": st, "category": cat, "total": total,
            "dem": dem if party else None, "rep": rep if party else None,
            "other": total - dem - rep if party else None}


def main() -> pd.DataFrame:
    old = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame(columns=["date", "state_po", "category"])
    today = pd.Timestamp.today().normalize()
    keep_before = today - pd.Timedelta(days=REFRESH_DAYS)
    have = set(zip(old["date"], old["state_po"], old["category"])) if len(old) else set()
    # Days already asked about, including ones with nothing new (before a state began reporting, or a day it
    # skipped, when civicAPI answers with nothing or an earlier snapshot): without this, every such day was asked
    # about again each morning, and the step grew from 13 to 17 minutes as early voting went on.
    checked_path = RAW / "early_vote_checked.json"
    checked = set(json.loads(checked_path.read_text(encoding="utf-8"))) if checked_path.exists() else set()
    caps = capabilities()
    rows = []
    for st, c in caps.items():
        for cat in CATEGORIES:
            if cat not in c.get("categories", {}):
                continue
            for day in pd.date_range(START, today):
                key = f"{day:%Y-%m-%d}|{st}|{cat}"
                if day < keep_before and ((f"{day:%Y-%m-%d}", st, cat) in have or key in checked):
                    continue
                s = snapshot(st, cat, day)
                time.sleep(0.15)
                if s:
                    rows.append(s)
                if day < keep_before:
                    checked.add(key)
    checked_path.write_text(json.dumps(sorted(checked)), encoding="utf-8")
    new = pd.DataFrame(rows)
    out = pd.concat([old, new], ignore_index=True) if len(new) else old
    out = out.drop_duplicates(["date", "state_po", "category"], keep="last").sort_values(["state_po", "category", "date"])
    out.to_csv(OUT, index=False)
    latest = out[out.date == out.date.max()]
    print(f"{len(caps)} states reporting; {len(new)} snapshots read; latest {out.date.max()}: "
          f"{int(latest[latest.category != 'requested'].total.sum()):,} ballots cast")
    return out


if __name__ == "__main__":
    main()
