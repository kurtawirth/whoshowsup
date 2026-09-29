"""Election night: poll civicAPI for results and publish them to the site's live page.

    .venv/Scripts/python.exe scripts/election_night.py                 # the real thing: poll + publish until done
    .venv/Scripts/python.exe scripts/election_night.py --practice      # poll for real, write live.json, don't publish
    .venv/Scripts/python.exe scripts/election_night.py --simulate      # rehearsal: made-up results, nothing fetched
    options: --once (one round), --interval=180 (seconds), --until=2026-11-04T09:00 (UTC; default 4 a.m. ET Nov 4),
             --sim-hour=22 (simulation: stop at 10 p.m. ET), --keep (simulation: leave the made-up live.json in place to look at; restore it before the next push!)

Every round fetches the close races (Senate, governor, and House races neither side is 98% sure to win)
and, every fifth round, all the rest; writes site/src/data/live.json; and, unless practicing, commits
that one file and pushes it, which rebuilds the site (about 1.5 minutes). Stops at --until or when every
race has been called. Results are display only: they never feed the forecast.

--simulate draws a plausible night from our own forecast (each race's final margin from its forecast
range, counted up gradually in poll-closing order, called once it's out of reach) so the page and the
publishing loop can be tested before Nov 3 without touching civicAPI.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import subprocess
import sys
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
import civic_results as cr  # noqa: E402

LIVE = ROOT / "site" / "src" / "data" / "live.json"
LOGS = ROOT / "logs"
ARGS = {a.split("=", 1)[0]: (a.split("=", 1)[1] if "=" in a else True) for a in sys.argv[1:]}
INTERVAL = int(ARGS.get("--interval", 180))
UNTIL = pd.Timestamp(ARGS.get("--until", "2026-11-04T09:00"), tz="UTC")
PRACTICE, SIMULATE, ONCE = "--practice" in ARGS, "--simulate" in ARGS, "--once" in ARGS


def log(msg: str) -> None:
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / f"election_night_{datetime.now():%Y-%m-%d}.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def close_races(ours: pd.DataFrame) -> list[str]:
    close = (ours["office"] != "HOUSE") | ours["p_dem"].between(0.02, 0.98)
    return ours.loc[close & (ours["race_type"] != "same_party"), "race_id"].tolist()


def publish(n_called: int, n_total: int) -> None:
    rel = LIVE.relative_to(ROOT).as_posix()
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)  # noqa: E731
    git("add", rel)
    if git("diff", "--cached", "--quiet", "--", rel).returncode == 0:
        return  # nothing new
    c = git("commit", "-m", f"Election night: results as of {datetime.now():%H:%M} ({n_called} of {n_total} races called)", "--", rel)
    if c.returncode:
        log(f"commit failed: {c.stderr.strip()[:200]}")
        return
    for _ in range(3):
        p = git("push")
        if p.returncode == 0:
            log("published")
            return
        git("pull", "--rebase")
    log(f"push failed: {p.stderr.strip()[:200]}")


# ---------------- rehearsal ----------------
POLL_CLOSE_ET = {  # hour (ET) most polls close; used only to order the simulated night
    **{s: 19 for s in ("GA", "IN", "KY", "SC", "VT", "VA", "FL", "NH")}, **{s: 19.5 for s in ("NC", "OH", "WV")},
    **{s: 20 for s in ("AL", "CT", "DE", "IL", "ME", "MD", "MA", "MS", "MO", "NJ", "OK", "PA", "RI", "TN", "TX", "DC")},
    "AR": 20.5, **{s: 21 for s in ("AZ", "CO", "KS", "LA", "MI", "MN", "NE", "NM", "NY", "ND", "SD", "WI", "WY", "IA")},
    **{s: 22 for s in ("MT", "NV", "UT", "ID")}, **{s: 23 for s in ("CA", "OR", "WA")}, "HI": 24, "AK": 25}


class Simulation:
    def __init__(self, ours: pd.DataFrame, seed: int = 2026):
        rng = np.random.default_rng(seed)
        self.ours = ours.set_index("race_id")
        # a final margin inside each race's forecast range (p10-p90 is roughly +-1.28 sd)
        mid, sd = self.ours["margin_median"], (self.ours["margin_p90"] - self.ours["margin_p10"]) / 2.56
        shared = rng.normal(0, 1.5)  # a national miss that moves every race together
        self.final = mid + shared + rng.normal(0, 1, len(mid)) * sd
        self.close = self.ours["state_po"].map(POLL_CLOSE_ET).fillna(21)
        self.speed = rng.uniform(1.5, 4.0, len(mid))  # hours from poll close to fully counted
        self.clock = 18.5  # 6:30 p.m. ET

    def step(self, hours: float = 0.25) -> dict:
        self.clock += hours
        out = {}
        for i, (rid, r) in enumerate(self.ours.iterrows()):
            if r["race_type"] == "same_party" or self.clock < self.close[rid]:
                continue
            pct = min(100, 100 * (self.clock - self.close[rid]) / self.speed[i])
            # early counts wander around the final margin and settle as they fill in
            m = self.final[rid] + (1 - pct / 100) * 6 * np.sin(3 * i)
            total = 1000 * pct
            d = int(total * (0.5 + m / 200))
            out[rid] = {"pct": round(pct), "d": d, "r": int(total - d), "margin": round(m, 2),
                        "called": ("D" if self.final[rid] > 0 else "R") if pct >= 95 or (pct >= 40 and abs(m) > 12) else None,
                        "updated": None}
        return out


def main() -> None:
    if SIMULATE or PRACTICE:  # never leave rehearsal results where the daily run could publish them
        original = LIVE.read_text(encoding="utf-8") if LIVE.exists() else json.dumps(PLACEHOLDER)
        try:
            run()
        finally:
            if "--keep" not in ARGS:
                LIVE.write_text(original, encoding="utf-8")
                log("rehearsal over: live.json restored")
    else:
        run()


PLACEHOLDER = {"mode": "waiting", "source": "civicAPI", "races": {}, "called": 0, "reporting": 0}


def run() -> None:
    ours = cr.our_races()
    total = int((ours["race_type"] != "same_party").sum())
    close = close_races(ours)
    live = json.loads(LIVE.read_text(encoding="utf-8")) if LIVE.exists() and not SIMULATE else {"races": {}}
    sim = Simulation(ours) if SIMULATE else None
    mode = "simulation" if SIMULATE else "practice (not publishing)" if PRACTICE else "LIVE"
    log(f"Election night {mode}: {len(close)} close races every {INTERVAL}s, all {total} every 5th round")
    k = 0
    while True:
        if SIMULATE:
            res = sim.step()
        else:
            res = cr.fetch(None if k % 5 == 0 else close)
        live["races"].update(res)
        called = sum(1 for v in live["races"].values() if v.get("called"))
        reporting = sum(1 for v in live["races"].values() if (v.get("d") or v.get("r")))
        live.update({"asof": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "mode": "simulation" if SIMULATE else "practice" if PRACTICE else "live",
                     "source": "civicAPI", "called": called, "reporting": reporting, "total": total})
        LIVE.write_text(json.dumps(live, separators=(",", ":")), encoding="utf-8")
        log(f"round {k}: {len(res)} races fetched, {reporting} with votes, {called} of {total} called")
        if not (PRACTICE or SIMULATE):
            publish(called, total)
        k += 1
        done = called >= total or pd.Timestamp.now(tz="UTC") >= UNTIL or (SIMULATE and sim.clock > float(ARGS.get("--sim-hour", 29)))
        if ONCE or done:
            break
        time.sleep(2 if SIMULATE else INTERVAL)
    log("done")


if __name__ == "__main__":
    main()
