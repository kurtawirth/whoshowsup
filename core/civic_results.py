"""Election-night results from civicAPI, matched to our races. DISPLAY ONLY -- never a model input.

    .venv/Scripts/python.exe core/civic_results.py --map        # match civicAPI's Nov 3 races to ours
    .venv/Scripts/python.exe core/civic_results.py --fetch      # fetch current results once (all mapped races)

Source: civicAPI (https://civicapi.org), free for any use with attribution ("please either link to
civicapi.org or list our name somewhere"). No key. Each race is one small request (?light drops the
county breakdown); responses are cached by civicAPI for 15 seconds.

map_races() runs in the daily forecast: one search per state for races on Election Day, matched to our
race ids by office, state and district (Senate specials by "Special" in the name). Writes
data/processed/civic_race_map.csv.

fetch() reads the current count for a set of races and returns, per race: percent reporting, the votes
for our forecast's Democratic side and Republican side (Osborn in Nebraska and Hill in Alaska's House race
count on the Democratic side, as in our forecast; in Alaska's top-four races each side is its party's
candidates added together), the two-side margin, and civicAPI's call (the winning side), if any.
scripts/election_night.py calls it in a loop and publishes site/src/data/live.json.
"""
from pathlib import Path
import json
import re
import sys
import time

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
SITE = ROOT / "site" / "src" / "data"
API = "https://civicapi.org/api/v2"
ELECTION_DAY = "2026-11-03"
MAP = PROC / "civic_race_map.csv"
HEADERS = {"User-Agent": "WhoShowsUp/1.0 (https://whoshowsup.net; election-night results)"}
OFFICE = {"US Senate": "SEN", "US Senate Special": "SEN", "Senate": "SEN", "Governor": "GOV", "House of Representatives": "HOUSE"}


def get(path: str, tries: int = 3) -> dict:
    for k in range(tries):
        try:
            r = requests.get(f"{API}/{path}", headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if k == tries - 1:
                raise
            time.sleep(2 * (k + 1))


def our_races() -> pd.DataFrame:
    return pd.DataFrame(json.loads((SITE / "races.json").read_text(encoding="utf-8")))


def _district(name: str) -> int | None:
    if re.search(r"at[- ]large", name, re.I):
        return 0
    m = re.search(r"(?:House|District)\s*(\d+)\b", name)
    return int(m.group(1)) if m else None


def map_races() -> pd.DataFrame:
    ours = our_races()
    ids = set(ours["race_id"])
    rows, unmatched = [], []
    for st in sorted(ours["state_po"].unique()):
        d = get(f"race/search?startDate={ELECTION_DAY}&endDate={ELECTION_DAY}&country=US&province={st}&limit=500")
        if d.get("count", 0) >= 500:  # a state with many local races that day (Indiana, Kentucky): get them all
            d = get(f"race/search?startDate={ELECTION_DAY}&endDate={ELECTION_DAY}&country=US&province={st}&limit=10000")
        for x in d.get("races", []):
            office = OFFICE.get(x.get("type"))
            if office is None or x.get("election_type") not in (None, "General", "Statewide"):
                continue
            name = x.get("election_name", "")
            if office == "HOUSE":
                dist = _district(name)
                rid = f"house-{st.lower()}-{'al' if dist == 0 else dist}"
            else:
                rid = f"{'senate' if office == 'SEN' else 'governor'}-{st.lower()}" + ("-special" if re.search(r"special", f"{name} {x.get('type')}", re.I) else "")
            if rid in ids:
                rows.append({"race_id": rid, "civic_id": x["id"], "civic_name": name})
            else:
                unmatched.append(f"{st}: {name} ({x['id']})")
    m = pd.DataFrame(rows).drop_duplicates("race_id", keep="first")
    m.to_csv(MAP, index=False)
    missing = sorted(ids - set(m["race_id"]))
    print(f"civicAPI: matched {len(m)} of {len(ids)} races; {len(missing)} of ours not found yet"
          + (f" (e.g. {', '.join(missing[:8])})" if missing else ""))
    if unmatched:
        print("  civicAPI races we couldn't place: " + "; ".join(unmatched[:10]))
    return m


def _side_votes(race: dict, cands: list[dict]) -> tuple[int, int, str | None]:
    """Votes for our forecast's D side and R side, and the winning side if called.
    In an independent race (Osborn in Nebraska, Hill in Alaska's House race, Kiley in CA-6) the
    independent takes the side opposite the party they face, and that side's own party nominee
    (e.g. Hafner, D, in Alaska) counts for neither side, as in our forecast."""
    ind_side = None
    if race["race_type"] == "independent":
        ind_side = "D" if race.get("rep_candidate") else "R"
        ind_last = str(race.get("race_note") or "").lower().split()[-1]
    d = r = 0
    called = None
    for c in cands:
        party, name = str(c.get("party") or ""), str(c.get("name") or "").lower()
        side = "D" if party.startswith("Democrat") else "R" if party.startswith("Republican") else None
        if ind_side:
            side = ind_side if ind_last in name else (None if side == ind_side else side)
        votes = int(float(c.get("votes") or 0))
        if side == "D":
            d += votes
        elif side == "R":
            r += votes
        if c.get("winner") and side:
            called = side
    return d, r, called


def fetch(race_ids: list[str] | None = None, pause: float = 0.25) -> dict:
    m = pd.read_csv(MAP)
    ours = our_races().set_index("race_id")
    if race_ids is not None:
        m = m[m["race_id"].isin(race_ids)]
    out = {}
    for row in m.itertuples():
        try:
            x = get(f"race/{row.civic_id}?light")
        except Exception as e:  # keep going: one race failing shouldn't stop the rest
            print(f"  {row.race_id}: {e!r}")
            continue
        x = x.get("data", x)
        d, r, called = _side_votes(ours.loc[row.race_id].to_dict(), x.get("candidates") or [])
        out[row.race_id] = {"pct": x.get("percent_reporting"), "d": d, "r": r,
                            "margin": round(100 * (d - r) / (d + r), 2) if d + r else None,
                            "called": called, "updated": x.get("last_updated")}
        time.sleep(pause)
    return out


if __name__ == "__main__":
    if "--map" in sys.argv:
        map_races()
    if "--fetch" in sys.argv:
        res = fetch()
        print(f"{len(res)} races fetched; with votes: {sum(1 for v in res.values() if (v['d'] or v['r']))}")
