"""One command to refresh every data source and rerun the whole 2026 forecast.

    .venv/Scripts/python.exe midterms_2026/run_forecast.py                 # refresh + forecast as of today
    .venv/Scripts/python.exe midterms_2026/run_forecast.py --no-refresh    # rerun models on cached data
    .venv/Scripts/python.exe midterms_2026/run_forecast.py --date 2026-10-15
    .venv/Scripts/python.exe midterms_2026/run_forecast.py --push          # also commit + push to GitHub

Steps
  1. Refresh sources: Wikipedia race + overview pages, VoteHub, DDHQ, The Downballot specials
  2. Rebuild: race list, polls, candidate quality, special elections
  3. National environment: history as of this calendar day in past years -> Bayesian blend
  4. Poll accuracy for this many days before the election
  5. Race simulation
  6. Checks: data freshness, race counts, big moves since the last run
  7. Snapshot to outputs/history/<date>/ and append to outputs/forecast_history.csv
  8. Website: export site/src/data/*.json and test-build the site (GitHub Actions deploys it on push)

Anything that looks wrong is printed as a WARNING at the end; it does not stop
the run, because a partial refresh is still better than none -- but read them.
"""
from pathlib import Path
import argparse
import shutil
import subprocess
import sys
import time
import traceback

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for sub in ("core", "midterms_2026", "midterms_2026/polls", "midterms_2026/models"):
    sys.path.insert(0, str(ROOT / sub))

PROC = ROOT / "data" / "processed"
OUT = ROOT / "midterms_2026" / "outputs"
ELECTION_DAY = pd.Timestamp("2026-11-03")
OVERVIEW_PAGES = ["2026_United_States_Senate_elections", "2026_United_States_gubernatorial_elections",
                  "2026_United_States_House_of_Representatives_elections"]
EXPECTED_RACES = {"house": 435, "senate": 35, "governor": 36}
BIG_MOVE = {"p_house_d": 0.15, "p_senate_d": 0.15, "house_median": 8, "nat_median": 2.0}

warnings: list[str] = []


def step(name: str):
    """Decorator-free step runner: prints timing, records failures as warnings."""
    def run(fn, *args, **kwargs):
        t = time.time()
        print(f"\n>>> {name}")
        try:
            out = fn(*args, **kwargs)
            print(f"    done in {time.time() - t:.0f}s")
            return out
        except Exception as e:  # keep going; a stale input beats no forecast
            warnings.append(f"{name} FAILED: {e!r}")
            traceback.print_exc()
            return None
    return run


def refresh_sources() -> None:
    import scrape_wikipedia_polls as swp
    import build_special_elections as bse
    for page in OVERVIEW_PAGES:
        swp.fetch(page, refresh=True)
    step("Special elections (The Downballot)")(bse.refresh)


def check_freshness(asof: pd.Timestamp) -> None:
    polls = pd.read_csv(PROC / "polls_2026_races.csv", parse_dates=["end_date"])
    gen = pd.read_csv(PROC / "polls_2026_generic.csv", parse_dates=["end_date"])
    for label, df, days in [("race polls", polls, 7), ("generic-ballot polls", gen, 7)]:
        latest = df["end_date"].max()
        if (asof - latest).days > days:
            warnings.append(f"Latest {label} end {latest:%Y-%m-%d}, {(asof - latest).days} days before the forecast date")
    recent = gen[(gen["end_date"] <= asof) & (gen["end_date"] > asof - pd.Timedelta(days=30))]
    if len(recent) < 15:
        warnings.append(f"Only {len(recent)} generic-ballot polls in the last 30 days")
    for name, n in EXPECTED_RACES.items():
        got = len(pd.read_csv(PROC / f"races_2026_{name}.csv"))
        if got != n:
            warnings.append(f"{name}: {got} races (expected {n}) -- a race page may have changed format")


def record(asof: pd.Timestamp) -> pd.DataFrame:
    """Snapshot this run and append its topline to the running history."""
    top = pd.read_csv(OUT / "topline.csv")
    top["run_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    polls = pd.read_csv(PROC / "polls_2026_races.csv", parse_dates=["end_date"])
    gen = pd.read_csv(PROC / "polls_2026_generic.csv", parse_dates=["end_date"])
    top["race_polls"] = int((polls["end_date"] <= asof).sum())
    top["generic_polls_30d"] = int(((gen["end_date"] <= asof) & (gen["end_date"] > asof - pd.Timedelta(days=30))).sum())
    reads = pd.read_csv(OUT / "national_env_reads.csv").set_index("read")
    for r in reads.index:
        top[f"read_{r}"] = reads.loc[r, "dem_margin"]
        top[f"weight_{r}"] = reads.loc[r, "weight"]

    hist_path = OUT / "forecast_history.csv"
    hist = pd.read_csv(hist_path) if hist_path.exists() else pd.DataFrame()
    if len(hist):
        prev = hist[hist["forecast_date"] < str(asof.date())].sort_values("forecast_date").tail(1)
        if len(prev):
            for col, limit in BIG_MOVE.items():
                delta = float(top[col].iloc[0]) - float(prev[col].iloc[0])
                if abs(delta) > limit:
                    warnings.append(f"Big move in {col}: {float(prev[col].iloc[0]):.2f} -> {float(top[col].iloc[0]):.2f} "
                                    f"since {prev['forecast_date'].iloc[0]} -- check what changed")
        hist = hist[hist["forecast_date"] != str(asof.date())]  # rerunning a day replaces it
    hist = pd.concat([hist, top], ignore_index=True).sort_values("forecast_date")
    hist.to_csv(hist_path, index=False)

    snap = OUT / "history" / str(asof.date())
    snap.mkdir(parents=True, exist_ok=True)
    for f in ("race_forecasts.csv", "chamber_summary.csv", "topline.csv", "national_env_reads.csv"):
        shutil.copy(OUT / f, snap / f)
    return top


def build_site() -> None:
    """Test-build the website so a broken page is caught here, not after deploy."""
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        raise RuntimeError("npm not found; skipped the site build")
    r = subprocess.run([npm, "run", "build"], cwd=ROOT / "site", capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise RuntimeError("site build failed")


def push(asof: pd.Timestamp) -> None:
    gh_msg = f"Forecast update {asof.date()}\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode != 0:
        subprocess.run(["git", "commit", "-q", "-m", gh_msg], cwd=ROOT, check=True)
        subprocess.run(["git", "push", "-q"], cwd=ROOT, check=True)
        print("Pushed to GitHub.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="forecast date YYYY-MM-DD (default: today)")
    ap.add_argument("--no-refresh", action="store_true", help="use cached data; only rerun the models")
    ap.add_argument("--push", action="store_true", help="commit and push the results to GitHub")
    args = ap.parse_args()
    asof = pd.Timestamp(args.date) if args.date else pd.Timestamp.today().normalize()
    days_out = (ELECTION_DAY - asof).days
    refresh = not args.no_refresh
    print(f"Forecast as of {asof.date()} ({days_out} days to the election); refresh={refresh}")

    import build_races, scrape_wikipedia_polls, build_polls, build_candidate_quality  # noqa: E401
    import build_special_elections, build_national_history, poll_average_error      # noqa: E401
    import national_env, race_model, export_site_data                               # noqa: E401

    if refresh:
        step("Refresh overview pages + specials")(refresh_sources)
    step("Race list")(build_races.main)
    step("Wikipedia race polls")(scrape_wikipedia_polls.main, refresh)
    step("VoteHub + DDHQ polls")(build_polls.main, refresh)
    step("Candidate quality")(build_candidate_quality.main)
    step("Special elections")(build_special_elections.main)
    step("National history")(build_national_history.main, (asof.month, asof.day))
    step("National environment model")(national_env.main, False)
    step(f"Poll accuracy at {days_out} days out")(poll_average_error.main, max(days_out, 1))
    summary = step("Race simulation")(race_model.simulate, asof)

    step("Checks")(check_freshness, asof)
    top = step("Snapshot + history")(record, asof)
    step("Website data")(export_site_data.main)
    step("Website test build")(build_site)

    print("\n" + "=" * 60)
    if summary is not None:
        for l in summary.itertuples(index=False):
            print(f"{l[0]:<40} {l[1]:>6}   {l[2]}")
    if top is not None:
        print(f"\nInputs: {int(top['race_polls'].iloc[0])} race polls, "
              f"{int(top['generic_polls_30d'].iloc[0])} generic-ballot polls in the last 30 days")
    print("\n" + ("\n".join(f"WARNING: {w}" for w in warnings) if warnings else "No warnings."))
    if args.push:
        step("Push to GitHub")(push, asof)


if __name__ == "__main__":
    main()
