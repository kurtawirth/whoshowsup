"""Combine poll sources into the model's poll datasets.

Sources, in priority order (a poll found in several keeps the first source's row):
  VoteHub open API (api.votehub.com/polls) -- structured, links to each
    original release, flags partisan pollsters and lists sponsors. Primary source.
  Wikipedia race pages (scrape_wikipedia_polls.py) -- fills VoteHub's gaps, including House.
  Decision Desk HQ race pages (votes.decisiondeskhq.com/polls) -- about 20 of the most-polled
    Senate and governor races; often has a new poll a day before the other two.

Outputs (data/processed/):
  polls_2026_races.csv     general-election race polls, both nominees present,
                           deduplicated across sources
  polls_2026_generic.csv   generic congressional ballot (national)
  polls_2026_approval.csv  presidential (Trump) job approval (national)

Every poll keeps: pollster, dates, sample size, population (lv/rv/a/v),
partisan flag (pollster or sponsor tied to a party), sponsors, source, URL.
"""
from pathlib import Path
import json
import re
import sys
import time

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "midterms_2026" / "polls"))
sys.path.insert(0, str(ROOT / "midterms_2026"))
from scrape_wikipedia_polls import bloc_names, name_hits, slot_candidates  # noqa: E402
from build_races import STATE_PO  # noqa: E402

RAW = ROOT / "data" / "raw" / "votehub"
PROC = ROOT / "data" / "processed"
API = "https://api.votehub.com/polls"
PO_STATE = {v: k for k, v in STATE_PO.items()}
DDHQ = "https://votes.decisiondeskhq.com"
RECENT = pd.Timestamp.today().normalize() - pd.Timedelta(days=21)
FAILED: list[str] = []  # sources that could not be downloaded this run (saved copy used)
ISSUES: list[str] = []  # recent polls of a race we forecast that did not match both nominees


def load_votehub(refresh: bool = False) -> pd.DataFrame:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / "polls_all.json"
    if refresh or not path.exists():
        try:
            r = requests.get(API, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
            r.raise_for_status()
            path.write_text(r.text, encoding="utf-8")
        except requests.RequestException as e:
            if not path.exists():
                raise
            FAILED.append(f"VoteHub ({e.__class__.__name__}; the last saved copy was used)")
    df = pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
    for c in ("start_date", "end_date"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["partisan"] = df["partisan"].map({"DEM": "D", "REP": "R"}).fillna("")
    df["sponsors"] = df["sponsors"].map(lambda s: "; ".join(s) if isinstance(s, list) else "")
    return df


def races_table() -> pd.DataFrame:
    parts = []
    for office, f in [("SEN", "senate"), ("GOV", "governor"), ("HOUSE", "house")]:
        df = pd.read_csv(PROC / f"races_2026_{f}.csv").assign(office=office)
        if office == "HOUSE":
            df["special"] = False
        parts.append(df)
    r = pd.concat(parts, ignore_index=True)
    r = r[r["race_type"].isin(["standard", "independent", "rcv_bloc"])].copy()
    slots = r.apply(slot_candidates, axis=1, result_type="expand")
    r["dem_slot"], r["rep_slot"] = slots[0], slots[1]
    blocs = r.apply(bloc_names, axis=1, result_type="expand")
    r["dem_bloc"], r["rep_bloc"] = blocs[0], blocs[1]
    return r


def _answer(answers, name, bloc=()) -> float:
    """The candidate's share; in Alaska's bloc races plus the other candidates of that side."""
    choices = [a["choice"] for a in answers]
    hits = name_hits(choices, name)
    if len(hits) != 1:
        return float("nan")
    used, total = {hits[0]}, next(a["pct"] for a in answers if a["choice"] == hits[0])
    for other in bloc:
        h = name_hits(choices, other)
        if len(h) == 1 and h[0] not in used:
            used.add(h[0])
            total += next(a["pct"] for a in answers if a["choice"] == h[0])
    return total


def _label(r) -> str:
    return (f"{r['office']} {r['state_po']}" + (f"-{int(r['district'])}" if r["office"] == "HOUSE" else "")
            + (" (special)" if r["special"] else ""))


def votehub_race_polls(vh: pd.DataFrame, races: pd.DataFrame) -> pd.DataFrame:
    kinds = {"us-senator": "SEN", "governor": "GOV", "us-representative": "HOUSE"}
    vh = vh[vh["poll_type"].isin(kinds)].copy()
    vh["office"] = vh["poll_type"].map(kinds)
    rows = []
    for _, r in races.iterrows():
        if r["office"] == "HOUSE":
            seat = f"{r['state_po']}-{int(r['district']):02d}" if r["district"] else f"{r['state_po']}-AL"
            cand = vh[(vh["office"] == "HOUSE") & (vh["seat_name"].isin([seat, f"{r['state_po']}-01"] if not r["district"] else [seat]))]
        else:
            cand = vh[(vh["office"] == r["office"]) & (vh["subject"] == f"2026 {PO_STATE[r['state_po']]}")]
        # FL and OH each hold two Senate races; a poll of one is not a miss for the other
        both = r["office"] == "SEN" and ((races["office"] == "SEN") & (races["state_po"] == r["state_po"])).sum() > 1
        for _, p in cand.iterrows():
            d, rp = _answer(p["answers"], r["dem_slot"], r["dem_bloc"]), _answer(p["answers"], r["rep_slot"], r["rep_bloc"])
            if d != d or rp != rp:
                # not a poll of the actual nominees (a primary or hypothetical) -- or names that didn't match
                if p["end_date"] >= RECENT and not both:
                    ISSUES.append(f"{_label(r)}: recent VoteHub poll ({p['pollster']}, {p['end_date']:%b %d}) without "
                                  f"{r['dem_slot']} vs {r['rep_slot']}: {', '.join(a['choice'] for a in p['answers'])}")
                continue
            # Special vs regular Senate in the same state (FL, OH): only the named nominees decide.
            rows.append({
                "office": r["office"], "state_po": r["state_po"], "district": r["district"],
                "special": r["special"], "dem_candidate": r["dem_slot"], "rep_candidate": r["rep_slot"],
                "pollster": p["pollster"], "partisan": p["partisan"], "sponsors": p["sponsors"],
                "start_date": p["start_date"], "end_date": p["end_date"],
                "sample_size": p["sample_size"], "population": str(p["population"]).lower(),
                "dem_pct": d, "rep_pct": rp,
                "other_pct": sum(a["pct"] for a in p["answers"]) - d - rp,
                "source": "votehub", "url": p["url"], "votehub_id": p["id"],
            })
    return pd.DataFrame(rows)


def wikipedia_race_polls() -> pd.DataFrame:
    w = pd.read_csv(PROC / "polls_2026_wikipedia.csv", parse_dates=["start_date", "end_date"])
    return w.assign(
        partisan=w["pollster_party"].fillna(""),
        sponsors=w["sponsored"].map({True: "(partisan client per Wikipedia)", False: ""}),
        population=w["population"].fillna("").str.lower(),
        # the poll's own release (from its Wikipedia footnote) when there is one, else the Wikipedia list
        source="wikipedia", url=w.get("source_url", pd.Series("", index=w.index)).fillna("").where(
            lambda u: u != "", w["source_page"].map(lambda t: f"https://en.wikipedia.org/wiki/{t}")),
    )[["office", "state_po", "district", "special", "dem_candidate", "rep_candidate", "pollster",
       "partisan", "sponsors", "start_date", "end_date", "sample_size", "population",
       "dem_pct", "rep_pct", "other_pct", "undecided_pct", "source", "url"]]


def _pkey(name: str) -> str:
    """Crude pollster key for matching across sources ('The Trafalgar Group' ~ 'Trafalgar Group')."""
    # "The New York Times/Siena University" ~ "Siena Research Institute / The New York Times" -> "siena"
    words = [w for w in re.sub(r"[^a-z ]", " ", str(name).lower()).split()
             if w not in {"the", "group", "research", "polling", "poll", "university", "college", "insights",
                          "institute", "center", "new", "york", "times"}]
    return words[0] if words else ""


def combine(*sources: pd.DataFrame) -> pd.DataFrame:
    """Union of the sources, in priority order. A later source's row is dropped when an earlier
    source already has the poll: same race and pollster key with end dates within 2 days, or
    same race, end date and sample size (one poll listed under different names)."""
    race = ["office", "state_po", "district", "special"]
    out = pd.DataFrame()
    for rank, src in enumerate(sources):
        if src is None or src.empty:
            continue
        src = src.assign(k=src["pollster"].map(_pkey), rank=rank, district=src["district"].fillna(0).astype(int))
        if not out.empty:
            m = src.reset_index().merge(out[race + ["k", "end_date"]], on=race + ["k"], how="left", suffixes=("", "_x"))
            dup = set(m.loc[(m["end_date"] - m["end_date_x"]).abs() <= pd.Timedelta(days=2), "index"])
            n = src[src["sample_size"].notna()].reset_index().merge(
                out.loc[out["sample_size"].notna(), race + ["end_date", "sample_size"]], on=race + ["end_date", "sample_size"])
            src = src.drop(index=list(dup | set(n["index"])))
        out = pd.concat([out, src], ignore_index=True)
    # Second pass: identical toplines in the same race within 2 days are the same poll
    # listed under different names ("Berkeley IGS" vs "UC Berkeley Institute of
    # Governmental Studies", "PennLive" vs its pollster "Bravo Group"). Keep the higher-priority row.
    out = out.sort_values(race + ["dem_pct", "rep_pct", "end_date", "rank"]).reset_index(drop=True)
    same = out[race + ["dem_pct", "rep_pct"]].eq(out[race + ["dem_pct", "rep_pct"]].shift()).all(axis=1)
    close = (out["end_date"] - out["end_date"].shift()).abs() <= pd.Timedelta(days=2)
    out = out[~(same & close)]
    # One version per poll: pollsters often release likely-voter and registered-voter results (or
    # with and without leaners) from the same interviews, and each source may list every version.
    # Counting each would give that poll double weight. Keep likely voters, then registered, then
    # all adults; ties go to the higher-priority source.
    pop = out["population"].fillna("").str.lower().map({"lv": 0, "rv": 1, "v": 2, "a": 3}).fillna(4)
    out = (out.assign(pop=pop).sort_values(["pop", "rank"])
           .drop_duplicates(race + ["k", "start_date", "end_date"]).drop(columns=["k", "rank", "pop"]))
    return out.sort_values(race + ["end_date"]).reset_index(drop=True)


DDHQ_GENERIC = "https://votes.decisiondeskhq.com/polls/generic-ballot/national/lv-rv-adults"
DDHQ_APPROVAL = "https://votes.decisiondeskhq.com/polls/presidential-approval/donald-j-trump-5/national/lv-rv-adults"


def ddhq_generic(refresh: bool = False) -> pd.DataFrame:
    """Generic-ballot polls from Decision Desk HQ's public polling page.

    VoteHub stopped adding national generic-ballot polls after June 2026, while
    DDHQ is current. The page embeds its poll list in Next.js data chunks; each
    poll can carry several population versions (LV / RV / Adults), kept as
    separate rows so the likely-vs-registered gap can be measured."""
    path = ROOT / "data" / "raw" / "ddhq" / "generic-ballot.html"
    if refresh or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(DDHQ_GENERIC, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
        r.raise_for_status()
        path.write_text(r.text, encoding="utf-8")
    t = path.read_text(encoding="utf-8")
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', t, re.S)
    text = "".join(json.loads(f'"{c}"') for c in chunks)
    dec, rows, seen = json.JSONDecoder(), [], set()
    for m in re.finditer(r'\{"base_poll_id":', text):
        try:
            p, _ = dec.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        for meta in p.get("poll_metadata", []):
            if meta.get("poll_type") != "Generic Ballot" or meta["id"] in seen:
                continue
            seen.add(meta["id"])
            vals = {e["label"]: e["value"] for e in meta.get("entries", [])}
            rows.append({
                "pollster": p["pollster_sponsor_name"], "partisan": "D" if p.get("internal_candidate") == "Democrat"
                else "R" if p.get("internal_candidate") == "Republican" else "",
                "sponsors": "", "start_date": pd.to_datetime(p["start_date"]), "end_date": pd.to_datetime(p["end_date"]),
                "sample_size": meta.get("sample_size"),
                "population": {"Adults": "a"}.get(meta.get("population"), str(meta.get("population")).lower()),
                "dem_pct": vals.get("Democrat"), "rep_pct": vals.get("Republican"), "url": p.get("source"),
                "source": "ddhq",
            })
    return pd.DataFrame(rows)


def _ddhq_get(url: str, cache: str, refresh: bool) -> str:
    """A DDHQ page, saved under data/raw/ddhq; if the download fails, the last saved copy."""
    path = ROOT / "data" / "raw" / "ddhq" / cache
    if refresh or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
            r.raise_for_status()
            path.write_text(r.text, encoding="utf-8")
        except requests.RequestException as e:
            FAILED.append(f"Decision Desk page {url} ({e.__class__.__name__})")
        time.sleep(0.3)
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _ddhq_records(url: str, cache: str, refresh: bool):
    """Yield (poll, population-version) records embedded in a DDHQ polling page's Next.js data chunks."""
    t = _ddhq_get(url, cache, refresh)
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', t, re.S)
    text = "".join(json.loads(f'"{c}"') for c in chunks)
    dec, seen = json.JSONDecoder(), set()
    for m in re.finditer(r'\{"base_poll_id":', text):
        try:
            p, _ = dec.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        for meta in p.get("poll_metadata", []):
            if meta["id"] in seen:
                continue
            seen.add(meta["id"])
            yield p, meta


def ddhq_approval(refresh: bool = False) -> pd.DataFrame:
    """Presidential approval polls from Decision Desk HQ (current; VoteHub's national
    approval feed thinned out after June 2026). One row per poll: a poll released for
    several populations keeps its all-adults version (the historical approval series
    is adults), else registered voters, else likely voters."""
    rank = {"Adults": 0, "RV": 1, "LV": 2}
    rows = []
    for p, meta in _ddhq_records(DDHQ_APPROVAL, "approval.html", refresh):
        if meta.get("poll_type") != "Presidential Approval":
            continue
        vals = {e["label"]: e["value"] for e in meta.get("entries", [])}
        if vals.get("Approve") is None or vals.get("Disapprove") is None:
            continue
        rows.append({
            "pollster": p["pollster_sponsor_name"], "partisan": "", "sponsors": "",
            "start_date": pd.to_datetime(p["start_date"]), "end_date": pd.to_datetime(p["end_date"]),
            "sample_size": meta.get("sample_size"),
            "population": {"Adults": "a"}.get(meta.get("population"), str(meta.get("population")).lower()),
            "approve": vals["Approve"], "disapprove": vals["Disapprove"], "url": p.get("source"),
            "source": "ddhq", "_poll": p["base_poll_id"], "_rank": rank.get(meta.get("population"), 3),
        })
    df = pd.DataFrame(rows).sort_values(["_poll", "_rank"]).drop_duplicates("_poll")
    return df.drop(columns=["_poll", "_rank"]).sort_values("end_date").reset_index(drop=True)


def _internal_side(ic, r) -> str:
    """DDHQ marks a campaign's internal poll with that candidate (a dict) or a party name: D, R or ''."""
    if isinstance(ic, str):
        return {"Democrat": "D", "Republican": "R"}.get(ic, "")
    if isinstance(ic, dict):
        name = f"{ic.get('first_name', '')} {ic.get('last_name', '')}"
        if name_hits([name], r["dem_slot"]) or any(name_hits([name], n) for n in r["dem_bloc"]):
            return "D"
        if name_hits([name], r["rep_slot"]) or any(name_hits([name], n) for n in r["rep_bloc"]):
            return "R"
    return ""


def ddhq_race_pages(refresh: bool = False) -> list[str]:
    """Links to every 2026 general-election race page: listed on the polls hub and each state's page."""
    find = lambda html: set(re.findall(r'href="(/polls/general-ballot-test/[^"]+)"', html))
    hub = _ddhq_get(f"{DDHQ}/polls", "hub.html", refresh)
    links = find(hub)
    for st in sorted(set(re.findall(r'href="/polls/([a-z-]+)"', hub)) - {"national"}):
        links |= find(_ddhq_get(f"{DDHQ}/polls/{st}", f"state_{st}.html", refresh))
    return sorted(l for l in links if not re.match(r"/polls/general-ballot-test/20(1\d|2[0-5])-", l))


def ddhq_race_polls(races: pd.DataFrame, refresh: bool = False) -> pd.DataFrame:
    """Senate and governor polls from DDHQ's race pages. A poll released for several populations
    keeps its likely-voter version, else registered voters, else adults."""
    rank = {"LV": 0, "RV": 1, "Adults": 2}
    rows = []
    for link in ddhq_race_pages(refresh):
        slug = link.split("/")[3]
        office = "GOV" if "governor" in slug else "SEN" if ("senate" in slug or slug.endswith("-sen")) else None
        if office is None:
            continue
        best = {}
        for p, meta in _ddhq_records(DDHQ + link, f"race_{slug}.html", refresh):
            if meta.get("poll_type") != "General Ballot Test":
                continue
            k, r = p["base_poll_id"], rank.get(meta.get("population"), 3)
            if k not in best or r < best[k][2]:
                best[k] = (p, meta, r)
        for p, meta, _ in best.values():
            ans = [{"choice": e["label"], "pct": e["value"]} for e in meta.get("entries", []) if e.get("value") is not None]
            end = pd.to_datetime(p["end_date"])
            cand = races[(races["office"] == office) & (races["state_po"] == STATE_PO.get(p.get("geography")))]
            matched = False
            for _, r in cand.iterrows():
                d, rp = _answer(ans, r["dem_slot"], r["dem_bloc"]), _answer(ans, r["rep_slot"], r["rep_bloc"])
                if d != d or rp != rp:
                    continue
                matched = True
                rows.append({
                    "office": office, "state_po": r["state_po"], "district": r["district"], "special": r["special"],
                    "dem_candidate": r["dem_slot"], "rep_candidate": r["rep_slot"],
                    "pollster": p["pollster_sponsor_name"],
                    "partisan": _internal_side(p.get("internal_candidate"), r),
                    "sponsors": "", "start_date": pd.to_datetime(p["start_date"]), "end_date": end,
                    "sample_size": meta.get("sample_size"),
                    "population": {"Adults": "a"}.get(meta.get("population"), str(meta.get("population")).lower()),
                    "dem_pct": d, "rep_pct": rp, "other_pct": sum(a["pct"] for a in ans) - d - rp,
                    "source": "ddhq", "url": p.get("source"),
                })
            if not matched and end >= RECENT and len(cand):
                ISSUES.append(f"{office} {cand['state_po'].iloc[0]}: recent Decision Desk poll ({p['pollster_sponsor_name']}, "
                              f"{end:%b %d}) matched no race: {', '.join(a['choice'] for a in ans)}")
    return pd.DataFrame(rows)


def national(vh: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    def flat(df, keys):
        rows = []
        for _, p in df.iterrows():
            a = {x["choice"]: x["pct"] for x in p["answers"]}
            rows.append({"pollster": p["pollster"], "partisan": p["partisan"], "sponsors": p["sponsors"],
                         "start_date": p["start_date"], "end_date": p["end_date"],
                         "sample_size": p["sample_size"], "population": str(p["population"]).lower(),
                         **{k: a.get(v) for k, v in keys.items()}, "url": p["url"]})
        return pd.DataFrame(rows).sort_values("end_date").reset_index(drop=True)
    gen = flat(vh[vh["poll_type"] == "generic-ballot"], {"dem_pct": "Dem", "rep_pct": "Rep"})
    app = flat(vh[(vh["poll_type"] == "approval") & (vh["subject"] == "Donald Trump")
                  & (vh["end_date"] >= "2025-01-20")], {"approve": "Approve", "disapprove": "Disapprove"})
    return gen, app


def main(refresh: bool = False) -> None:
    FAILED.clear(); ISSUES.clear()
    vh = load_votehub(refresh)
    races = races_table()
    try:
        dd = ddhq_race_polls(races, refresh)
    except Exception as e:  # a page-format change must not cost us the other two sources
        FAILED.append(f"Decision Desk race polls ({e!r})")
        dd = pd.DataFrame()
    path = PROC / "polls_2026_races.csv"
    before = pd.read_csv(path, parse_dates=["start_date", "end_date"]) if path.exists() else None
    polls = combine(votehub_race_polls(vh, races), wikipedia_race_polls(), dd)
    n_dd = len(dd)
    polls.to_csv(path, index=False)
    new_polls_report(before, polls)
    gen, app = national(vh)
    # DDHQ is the primary generic-ballot source; VoteHub rows add polls DDHQ lacks
    # (same pollster key within 2 days of a DDHQ poll = duplicate).
    dd = ddhq_generic(refresh)
    gen = gen.assign(source="votehub", k=gen["pollster"].map(_pkey))
    dd_keys = dd.assign(k=dd["pollster"].map(_pkey))[["k", "end_date"]]
    m = gen.reset_index().merge(dd_keys, on="k", how="left", suffixes=("", "_dd"))
    dup = m.loc[(m["end_date"] - m["end_date_dd"]).abs() <= pd.Timedelta(days=2), "index"].unique()
    gen = pd.concat([dd, gen.drop(index=dup).drop(columns="k")], ignore_index=True).sort_values("end_date")
    gen.to_csv(PROC / "polls_2026_generic.csv", index=False)
    # Approval: DDHQ first, VoteHub fills in polls DDHQ lacks (same duplicate rule as above).
    da = ddhq_approval(refresh)
    app = app.assign(source="votehub", k=app["pollster"].map(_pkey))
    da_keys = da.assign(k=da["pollster"].map(_pkey))[["k", "end_date"]]
    m = app.reset_index().merge(da_keys, on="k", how="left", suffixes=("", "_dd"))
    dup = m.loc[(m["end_date"] - m["end_date_dd"]).abs() <= pd.Timedelta(days=2), "index"].unique()
    app = pd.concat([da, app.drop(index=dup).drop(columns="k")], ignore_index=True).sort_values("end_date")
    app = app[app["end_date"] >= "2025-01-20"]
    app.to_csv(PROC / "polls_2026_approval.csv", index=False)

    print(f"Race polls: {len(polls)}  (by source: {polls['source'].value_counts().to_dict()}; "
          f"Decision Desk had {n_dd} before removing duplicates)")
    print(polls.groupby("office").agg(polls=("pollster", "size"),
                                      races=("state_po", lambda s: len(set(zip(s, polls.loc[s.index, 'district'], polls.loc[s.index, 'special'])))),
                                      since_aug=("end_date", lambda d: (d >= "2026-08-01").sum())))
    print(f"Generic ballot polls: {len(gen)} (latest {gen['end_date'].max():%Y-%m-%d})")
    print(f"Trump approval polls: {len(app)} (latest {app['end_date'].max():%Y-%m-%d})")
    for f in FAILED:
        print("  download failed:", f)
    for i in ISSUES:
        print("  check:", i)


def new_polls_report(before: pd.DataFrame | None, after: pd.DataFrame) -> None:
    """Print the race polls this run added (compared with the previous run's file)."""
    if before is None or before.empty:
        return
    key = ["office", "state_po", "district", "special", "pollster", "end_date", "dem_pct", "rep_pct"]
    norm = lambda df: df[key].assign(district=df["district"].fillna(0).astype(int), end_date=pd.to_datetime(df["end_date"]).dt.date,
                                    dem_pct=df["dem_pct"].round(1), rep_pct=df["rep_pct"].round(1)).astype(str)
    old = set(map(tuple, norm(before).values))
    new = after[[tuple(v) not in old for v in norm(after).values]]
    print(f"New race polls this run: {len(new)}")
    for _, r in new.sort_values("end_date").iterrows():
        m = r["dem_pct"] - r["rep_pct"]
        print(f"  {_label(r):<16} {str(r['pollster'])[:40]:<40} ends {r['end_date']:%b %d}  "
              f"{'D' if m >= 0 else 'R'}+{abs(m):.0f}  ({r['source']})")


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
