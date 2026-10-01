"""The week's facts for The Turnout newsletter, in one Markdown file the Sunday drafting task reads first.

    .venv/Scripts/python.exe scripts/newsletter_factpack.py            # this week (latest forecast vs ~7 days earlier)
    .venv/Scripts/python.exe scripts/newsletter_factpack.py --days 7

Writes newsletter/factpacks/<date>.md (newsletter/ is git-ignored: drafts stay private until published):
  - whether today's forecast ran cleanly
  - the topline now and a week ago
  - races whose odds moved most, with the polls behind each move
  - every new race poll this week (pollster, dates, sample, sponsor, link to the release), for mining the details
  - new national polls (generic ballot, approval) with links
  - races where the forecast and the polling average disagree most
Comparisons never start before 2026-09-25, when a data fix added incumbents' past results to the model (moves across
that date are the fix, not news).
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HIST = ROOT / "midterms_2026" / "outputs" / "history"
PROC = ROOT / "data" / "processed"
SITE = ROOT / "site" / "src" / "data"
OUT = ROOT / "newsletter" / "factpacks"
EARLIEST_BASE = "2026-09-25"
KEY = ["office", "state_po", "district", "special", "pollster", "end_date", "dem_pct", "rep_pct", "population"]


def pct(p: float) -> str:
    return ">99%" if p >= 0.995 else "<1%" if p <= 0.005 else f"{round(100 * p)}%"


def lean(m: float, d: str = "D", r: str = "R") -> str:
    if pd.isna(m):
        return "n/a"
    sp = " " if len(d) > 1 else ""  # "D+6.7" for parties, "Jackson +4.0" for candidates
    return "even" if abs(m) < 0.05 else (f"{d}{sp}+{m:.1f}" if m > 0 else f"{r}{sp}+{-m:.1f}")


def last(name) -> str:
    words = [w for w in str(name or "").split() if w.rstrip(".") not in ("Jr", "Sr", "II", "III")]
    return words[-1] if words else str(name)


def main(days: int = 7) -> Path:
    snaps = sorted(p.name for p in HIST.iterdir() if (p / "race_forecasts.csv").exists())
    now = snaps[-1]
    target = (date.fromisoformat(now) - timedelta(days=days)).isoformat()
    base = max([s for s in snaps if s <= target and s >= EARLIEST_BASE] or [s for s in snaps if s >= EARLIEST_BASE][:1])
    races = {r["race_id"]: r for r in json.loads((SITE / "races.json").read_text(encoding="utf-8"))}
    t1, t0 = (pd.read_csv(HIST / d / "topline.csv").iloc[0] for d in (now, base))
    f1, f0 = (pd.read_csv(HIST / d / "race_forecasts.csv").set_index("race_id") for d in (now, base))
    status = json.loads((ROOT / "midterms_2026" / "outputs" / "run_status.json").read_text(encoding="utf-8"))
    L = [f"# The Turnout fact pack: {now} (compared with {base})", ""]

    L += ["## Forecast run", f"- forecast_date {status.get('forecast_date')}, finished {status.get('finished_at')}, "
          f"failed steps: {status.get('failed_steps') or 'none'}"]
    if status.get("forecast_date") != now:
        L.append("- WARNING: the latest forecast is not from today; say so in the notes to Kurt.")
    L.append("")

    L += ["## Topline (now vs. a week ago)",
          f"- House: Democrats {pct(t1.p_house_d)} (was {pct(t0.p_house_d)}); median {t1.house_median:.0f} D seats "
          f"(80% range {t1.house_p10:.0f}-{t1.house_p90:.0f}); 218 needed",
          f"- Senate: Democrats {pct(t1.p_senate_d)} (was {pct(t0.p_senate_d)}); median {t1.senate_median:.0f} D seats "
          f"(80% range {t1.senate_p10:.0f}-{t1.senate_p90:.0f}); Democrats need 51 (the vice president is a Republican)",
          f"- Governors: median {t1.gov_median:.0f} D of 36 (was {t0.gov_median:.0f})",
          f"- National House vote: {lean(t1.nat_median)} (was {lean(t0.nat_median)}); 80% range "
          f"{lean(t1.nat_p10)} to {lean(t1.nat_p90)}", ""]
    try:
        nat = json.loads((SITE / "national.json").read_text(encoding="utf-8"))
        reads = ", ".join(f"{r['read']} {lean(r['dem_margin'])} ({round(100 * r['weight'])}% weight)" for r in nat["reads"])
        L += [f"- The three national readings: {reads}", ""]
    except Exception:
        pass

    # new race polls this week: in today's poll list but not the baseline's (lists saved daily since 2026-09-29)
    polls = {d: HIST / d / "polls.csv" for d in (now, base)}
    base_polls = polls[base] if polls[base].exists() else next((HIST / s / "polls.csv" for s in snaps if s >= base and (HIST / s / "polls.csv").exists()), None)
    detail = pd.read_csv(PROC / "polls_2026_races.csv", parse_dates=["end_date"], low_memory=False)
    detail["end_date"] = detail["end_date"].dt.strftime("%Y-%m-%d")
    new = pd.DataFrame()
    if polls[now].exists() and base_polls is not None and base_polls != polls[now]:
        a, b = pd.read_csv(base_polls), pd.read_csv(polls[now])
        ka, kb = (x[KEY].map(str).agg("|".join, axis=1) for x in (a, b))
        new = b[~kb.isin(set(ka))].copy()
    if new.empty:  # fall back on end dates
        new = detail[detail["end_date"] >= base][KEY].copy()
    new = new.merge(detail[["office", "state_po", "district", "pollster", "end_date", "start_date", "sample_size", "partisan",
                            "sponsors", "url", "dem_candidate", "rep_candidate"]].drop_duplicates(["office", "state_po", "district", "pollster", "end_date"]),
                    on=["office", "state_po", "district", "pollster", "end_date"], how="left")

    def race_id(r) -> str:
        o = {"SEN": "senate", "GOV": "governor", "HOUSE": "house"}[r["office"]]
        rid = f"{o}-{r['state_po'].lower()}" + (f"-{int(r['district'])}" if r["office"] == "HOUSE" else "")
        if r["office"] == "HOUSE" and int(r["district"]) == 0:
            rid = f"house-{r['state_po'].lower()}-al"
        return rid + ("-special" if str(r["special"]) == "True" else "")

    new["race_id"] = new.apply(race_id, axis=1) if len(new) else []
    by_race = new.groupby("race_id") if len(new) else {}

    # races that moved
    j = f1.join(f0, rsuffix="_0", how="inner")
    j["dp"] = j["p_dem"] - j["p_dem_0"]
    moved = j[((j["p_dem"].between(0.03, 0.97)) | (j["p_dem_0"].between(0.03, 0.97))) & (j["dp"].abs() >= 0.03)]
    moved = moved.reindex(moved["dp"].abs().sort_values(ascending=False).index).head(15)
    L += ["## Races that moved most this week", "(p = Democratic side's chance; margins are the model's expected margin)"]
    for rid, r in moved.iterrows():
        x = races.get(rid, {})
        dn, rn = x.get("dem_name") or r.get("dem_candidate"), x.get("rep_name") or r.get("rep_candidate")
        n_new = len(by_race.get_group(rid)) if len(new) and rid in by_race.groups else 0
        c1, c0 = (0 if pd.isna(r.get(c)) else int(r[c]) for c in ("poll_count", "poll_count_0"))
        n_new = max(n_new, c1 - c0)  # the saved poll lists start 2026-09-29; poll counts cover earlier days
        dfund = r["fundamentals_mean"] - r["fundamentals_mean_0"] if pd.notna(r.get("fundamentals_mean_0")) else 0.0
        dnat = float(t1.nat_median - t0.nat_median)
        if n_new:
            why = f"{n_new} new poll(s)"
        elif abs(dfund - dnat) >= 2.5:
            why = (f"NO new polls, yet its non-poll baseline moved {dfund:+.1f} pts (national estimate moved {dnat:+.1f}): "
                   "PROBABLY A DATA OR MODEL CHANGE, NOT NEWS. Don't report this move as something that happened in the race")
        else:
            why = "no new polls (moved with the national estimate, older polls fading, or campaign money)"
        L.append(f"- {rid} ({dn} vs. {rn}): {pct(r['p_dem_0'])} -> {pct(r['p_dem'])}; expected margin "
                 f"{lean(r['margin_median_0'], last(dn), last(rn))} -> {lean(r['margin_median'], last(dn), last(rn))}; "
                 f"poll avg {lean(r['poll_avg'], last(dn), last(rn))} ({int(r['poll_count']) if pd.notna(r['poll_count']) else 0} polls); {why}. "
                 f"https://whoshowsup.net/race/{rid}")
    L.append("")

    L += ["## New race polls this week (open each release for the details beyond the topline)"]
    if len(new):
        for _, p in new.sort_values(["office", "state_po", "district"]).iterrows():
            spons = f"; sponsor: {p['sponsors']}" if pd.notna(p.get("sponsors")) and str(p.get("sponsors")).strip() else ""
            part = f"; PARTISAN ({p['partisan']}) - the model corrects it toward the other side and counts it half" if pd.notna(p.get("partisan")) else ""
            n = f"n={int(p['sample_size'])} " if pd.notna(p.get("sample_size")) else ""
            L.append(f"- {p['race_id']}: {p['pollster']}, {p.get('start_date', '')} to {p['end_date']}, {n}{str(p['population']).upper()}: "
                     f"{p.get('dem_candidate') or 'D'} {p['dem_pct']:g} - {p.get('rep_candidate') or 'R'} {p['rep_pct']:g}{spons}{part}. "
                     f"Release: {p['url'] if pd.notna(p.get('url')) else 'no link on file; search for it'}")
    else:
        L.append("- none found")
    L.append("")

    for name, f, cols in [("generic ballot", "polls_2026_generic.csv", ("dem_pct", "rep_pct")),
                          ("presidential approval", "polls_2026_approval.csv", ("approve", "disapprove"))]:
        g = pd.read_csv(PROC / f, parse_dates=["end_date"])
        g = g[g["end_date"] >= base].sort_values("end_date")
        L.append(f"## New {name} polls since {base}")
        for _, p in g.iterrows():
            L.append(f"- {p['pollster']}, ending {p['end_date']:%Y-%m-%d}, {str(p['population']).upper()}: {cols[0]} {p[cols[0]]:g}, "
                     f"{cols[1]} {p[cols[1]]:g}{' (partisan)' if pd.notna(p.get('partisan')) else ''}. {p['url'] if pd.notna(p.get('url')) else ''}")
        L.append("")

    gap = f1[(f1["poll_count"] >= 5) & f1["poll_avg"].notna() & f1["p_dem"].between(0.05, 0.95)].copy()
    gap["gap"] = gap["margin_median"] - gap["poll_avg"]
    gap = gap.reindex(gap["gap"].abs().sort_values(ascending=False).index).head(8)
    L += ["## Where the forecast and the polls disagree most (5+ polls, competitive)"]
    for rid, r in gap.iterrows():
        x = races.get(rid, {})
        dn, rn = x.get("dem_name"), x.get("rep_name")
        L.append(f"- {rid}: forecast {lean(r['margin_median'], last(dn), last(rn))} ({pct(r['p_dem'])} for {last(dn)}) vs. poll avg "
                 f"{lean(r['poll_avg'], last(dn), last(rn))} across {int(r['poll_count'])} polls; fundamentals {lean(r['fundamentals_mean'], last(dn), last(rn))}; "
                 f"polls get {round(100 * r['poll_weight'])}% of the weight; 2024 presidential {lean(x.get('pres24', float('nan')))}")
    L.append("")

    key = ["senate-me", "senate-tx", "senate-oh-special", "senate-ia", "senate-ne", "senate-ak", "senate-mi", "senate-nc", "senate-ga",
           "senate-nh", "senate-sc", "senate-ks", "governor-ga", "governor-oh", "governor-nv", "governor-wi", "governor-ak", "governor-tx", "governor-fl"]
    L += ["## Key statewide races now"]
    for rid in key:
        if rid not in f1.index:
            continue
        r, x = f1.loc[rid], races.get(rid, {})
        dn, rn = x.get("dem_name"), x.get("rep_name")
        L.append(f"- {rid}: {dn} vs. {rn}: {pct(r['p_dem'])} D ({x.get('rating')}); expected {lean(r['margin_median'], last(dn), last(rn))}; "
                 f"poll avg {lean(r['poll_avg'], last(dn), last(rn))} ({int(r['poll_count']) if pd.notna(r['poll_count']) else 0} polls); "
                 f"2024 pres {lean(x.get('pres24', float('nan')))}")
    L.append("")

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{now}.md"
    out.write_text("\n".join(L), encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    print(main(ap.parse_args().days))
