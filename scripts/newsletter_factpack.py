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
import sys
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


def turnout_margin(x: float, base: float) -> float:
    """National House margin if one party's voters turn out x better than expected (x > 0 Democrats, x < 0
    Republicans), the same conversion as the site's turnout dial (site/src/components/sims.js)."""
    s0 = (base / 100 + 1) / 2
    d, r = s0 * (1 + max(x, 0)), (1 - s0) * (1 - min(x, 0))
    return (2 * d / (d + r) - 1) * 100


def site_sections(races: dict, t1, now: str) -> list[str]:
    """The site's newer numbers (tipping points, vote's sway, the turnout dial, polling-miss scenarios,
    fundamentals vs. polls) and what's new on the site since the last issue."""
    import numpy as np
    L = []
    cur = pd.read_csv(ROOT / "midterms_2026" / "outputs" / "topline.csv").iloc[0]  # has the newer columns
    t1 = t1 if "senate_tp_gap" in t1 else cur
    R = [r for r in races.values() if r.get("race_type") != "same_party"]
    name = lambda r: (f"{r['state_name']} Senate{' (special)' if r.get('special') else ''}" if r["office"] == "SEN"
                      else f"{r['state_name']} governor" if r["office"] == "GOV" else r["label"])
    link = lambda r: f"https://whoshowsup.net/race/{r['race_id']}"

    L += ["## Tipping point and vote's sway (Senate and House pages; one line on each race page)",
          "Tipping point = how often a race is the one that hands a party control, across 20,000 simulations. Vote's sway = that chance per expected vote, vs. the average voter (1x).",
          f"- The seat that decides control runs about {abs(t1.senate_tp_gap):.0f} points {'more Republican' if t1.senate_tp_gap < 0 else 'more Democratic'} than the national House vote in the Senate "
          f"and about {abs(t1.house_tp_gap):.0f} points in the House (so a national {lean(t1.nat_median)} is about {lean(t1.nat_median + t1.senate_tp_gap)} where the Senate is decided)",
          f"- Simulations where an Osborn win leaves neither party a majority: {pct(t1.p_senate_no_majority)}"]
    for off, label in (("SEN", "Senate"), ("HOUSE", "House")):
        top = sorted([r for r in R if r["office"] == off and r.get("tipping_point")], key=lambda r: -r["tipping_point"])
        L.append(f"- {label} likeliest tipping points: " + "; ".join(f"{name(r)} {r['tipping_point']:.1%} ({link(r)})" for r in top[:6]))
        sway = sorted([r for r in top if r["tipping_point"] >= 0.01], key=lambda r: -r["voter_power"])
        L.append(f"- {label} biggest vote's sway (races with 1%+ tipping chance): " + "; ".join(f"{name(r)} {r['voter_power']:.1f}x" for r in sway[:5]))
    L.append("")

    sims = ROOT / "midterms_2026" / "outputs" / "simulations.npz"
    if sims.exists():
        z = np.load(sims)
        E, sen, house = z["E"], z["sen_d"], z["house_d"]
        L += ["## The turnout dial (https://whoshowsup.net/scenarios): one party's voters turn out X% better than we expect",
              "(simulations weighted toward the national vote that turnout edge implies; the same method as the site)"]
        for x in (-0.05, -0.03, 0.03, 0.05):
            m = turnout_margin(x, t1.nat_median)
            w = np.exp(-0.5 * ((E - m) / 0.6) ** 2)
            ps, ph = np.average(sen >= 51, weights=w), np.average(house >= 218, weights=w)
            who = "Republican" if x < 0 else "Democratic"
            L.append(f"- {who} voters {abs(x):.0%} better than expected -> national vote about {lean(m)}; Senate D {pct(ps)}, House D {pct(ph)}")
        L.append("")

    pm = ROOT / "midterms_2026" / "outputs" / "poll_miss_scenarios.csv"
    if pm.exists():
        s = pd.read_csv(pm)
        L += ["## If 2026's polls miss the way a past year's did (https://whoshowsup.net/scenarios; full model reruns)",
              "statewide_miss = how much that year's final statewide polls overstated Democrats (negative = overstated Republicans)"]
        for x in s.itertuples():
            miss = ("" if x.year == "forecast" else "; statewide polls were about right" if abs(x.statewide_miss) < 0.5
                    else f"; statewide polls overstated {'Democrats' if x.statewide_miss > 0 else 'Republicans'} by {abs(x.statewide_miss):.1f}")
            L.append(f"- {x.year}: Senate D {pct(x.p_senate_d)} ({x.senate_median:.0f} seats), House D {pct(x.p_house_d)} ({x.house_median:.0f} seats){miss}")
        L.append("")

    dis = sorted([r for r in R if r["office"] != "HOUSE" and r.get("p_fund") is not None and r.get("p_poll") is not None
                  and min(r["p_dem"], 1 - r["p_dem"]) > 0.1], key=lambda r: -abs(r["p_fund"] - r["p_poll"]))
    L += ["## Fundamentals alone vs. polls alone (race pages), biggest disagreements among competitive statewide races"]
    for r in dis[:6]:
        L.append(f"- {name(r)}: fundamentals alone {pct(r['p_fund'])} D, polls alone {pct(r['p_poll'])} D, our forecast {pct(r['p_dem'])} D "
                 f"(polls get {round(100 * r['poll_weight'])}% of the weight) {link(r)}")
    L.append("")

    # what's new on the site since the last published issue (newsletter/site_news.md: "- YYYY-MM-DD | what | link")
    news = ROOT / "newsletter" / "site_news.md"
    issues = sorted(p.stem for p in (ROOT / "newsletter" / "issues").glob("*.html") if not p.stem.startswith("test"))
    since = issues[-1] if issues else "2000-01-01"
    if news.exists():
        items = [l[2:].split(" | ") for l in news.read_text(encoding="utf-8").splitlines() if l.startswith("- ")]
        items = [i for i in items if len(i) >= 3 and since < i[0] <= now]
        if items:
            L += [f"## New on the site since the last issue ({since}): give these a short 'New on the site' item, each linked"]
            L += [f"- {i[1]} ({i[2]})" for i in items]
            L.append("")
    return L


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
                            "sponsors", "source", "url", "dem_candidate", "rep_candidate"]].drop_duplicates(["office", "state_po", "district", "pollster", "end_date"]),
                    on=["office", "state_po", "district", "pollster", "end_date"], how="left")

    def race_id(r) -> str:
        o = {"SEN": "senate", "GOV": "governor", "HOUSE": "house"}[r["office"]]
        rid = f"{o}-{r['state_po'].lower()}" + (f"-{int(r['district'])}" if r["office"] == "HOUSE" else "")
        if r["office"] == "HOUSE" and int(r["district"]) == 0:
            rid = f"house-{r['state_po'].lower()}-al"
        return rid + ("-special" if str(r["special"]) == "True" else "")

    new["race_id"] = new.apply(race_id, axis=1) if len(new) else []
    # which polls the model treats as a party's side, decided exactly as the model decides it
    sys.path[:0] = [str(ROOT / "midterms_2026" / "models"), str(ROOT / "midterms_2026"), str(ROOT / "core")]
    from race_model import partisan_side
    new["side"] = partisan_side(new) if len(new) else []
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
        why = f"{n_new} new poll(s)" if n_new else "no new polls (moved with the national estimate, older polls fading, or campaign money)"
        if abs(dfund - dnat) >= 2.5:
            # the non-poll baseline moved far more than the national estimate: a model or data change, whatever
            # else happened (a poll arriving the same week doesn't explain it)
            why = (f"{'NO new polls' if not n_new else f'{n_new} new poll(s), BUT'} its non-poll baseline moved {dfund:+.1f} pts "
                   f"(national estimate moved {dnat:+.1f}): PROBABLY A DATA OR MODEL CHANGE, NOT NEWS. Don't report this move as "
                   "something that happened in the race; at most, report what the new polls themselves showed")
        L.append(f"- {rid} ({dn} vs. {rn}): {pct(r['p_dem_0'])} -> {pct(r['p_dem'])}; expected margin "
                 f"{lean(r['margin_median_0'], last(dn), last(rn))} -> {lean(r['margin_median'], last(dn), last(rn))}; "
                 f"poll avg {lean(r['poll_avg'], last(dn), last(rn))} ({int(r['poll_count']) if pd.notna(r['poll_count']) else 0} polls); {why}. "
                 f"https://whoshowsup.net/race/{rid}")
    L.append("")

    L += ["## New race polls this week (open each release for the details beyond the topline)"]
    if len(new):
        for _, p in new.sort_values(["office", "state_po", "district"]).iterrows():
            sp = str(p.get("sponsors")) if pd.notna(p.get("sponsors")) else ""
            spons = ("; Wikipedia notes a sponsor (may be a news outlet; check the release)" if sp.startswith("(")
                     else f"; sponsor: {sp}" if sp.strip() else "")
            raw = str(p.get("partisan")) if pd.notna(p.get("partisan")) else ""
            part = (f"; MODEL TREATS AS PARTISAN ({p['side']}): corrected toward the other side and counted at half weight" if p["side"]
                    else f"; the source labels the firm {raw}, but the model does NOT treat this poll as partisan (the firm's track record says otherwise)" if raw
                    else "")
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

    L += site_sections(races, t1, now)

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{now}.md"
    out.write_text("\n".join(L), encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    print(main(ap.parse_args().days))
