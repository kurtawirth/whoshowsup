"""Combine poll sources into the model's poll datasets.

Sources:
  VoteHub open API (api.votehub.com/polls) -- structured, links to each
    original release, flags partisan pollsters and lists sponsors. Primary source.
  Wikipedia race pages (scrape_wikipedia_polls.py) -- fills VoteHub's gaps.

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

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "midterms_2026" / "polls"))
sys.path.insert(0, str(ROOT / "midterms_2026"))
from scrape_wikipedia_polls import last_name, slot_candidates  # noqa: E402
from build_races import STATE_PO  # noqa: E402

RAW = ROOT / "data" / "raw" / "votehub"
PROC = ROOT / "data" / "processed"
API = "https://api.votehub.com/polls"
PO_STATE = {v: k for k, v in STATE_PO.items()}


def load_votehub(refresh: bool = False) -> pd.DataFrame:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / "polls_all.json"
    if refresh or not path.exists():
        r = requests.get(API, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
        r.raise_for_status()
        path.write_text(r.text, encoding="utf-8")
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
    return r


def _answer(answers, name) -> float:
    ln = last_name(name)
    hits = [a["pct"] for a in answers if ln and ln in a["choice"].lower()]
    return hits[0] if len(hits) == 1 else float("nan")


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
        for _, p in cand.iterrows():
            d, rp = _answer(p["answers"], r["dem_slot"]), _answer(p["answers"], r["rep_slot"])
            if d != d or rp != rp:
                continue  # not a poll of the actual nominees (primary or hypothetical)
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
        source="wikipedia", url=w["source_page"].map(lambda t: f"https://en.wikipedia.org/wiki/{t}"),
    )[["office", "state_po", "district", "special", "dem_candidate", "rep_candidate", "pollster",
       "partisan", "sponsors", "start_date", "end_date", "sample_size", "population",
       "dem_pct", "rep_pct", "other_pct", "undecided_pct", "source", "url"]]


def _pkey(name: str) -> str:
    """Crude pollster key for matching across sources ('The Trafalgar Group' ~ 'Trafalgar Group')."""
    words = [w for w in re.sub(r"[^a-z ]", "", str(name).lower()).split()
             if w not in {"the", "group", "research", "polling", "poll", "university", "college", "insights"}]
    return words[0] if words else ""


def combine(vh: pd.DataFrame, wk: pd.DataFrame) -> pd.DataFrame:
    """Union, dropping Wikipedia rows that duplicate a VoteHub poll (same race,
    same pollster key, end dates within 2 days)."""
    race = ["office", "state_po", "district", "special"]
    vh = vh.assign(k=vh["pollster"].map(_pkey))
    wk = wk.assign(k=wk["pollster"].map(_pkey))
    m = wk.reset_index().merge(vh[race + ["k", "end_date"]], on=race + ["k"], how="left", suffixes=("", "_vh"))
    dup_idx = m.loc[(m["end_date"] - m["end_date_vh"]).abs() <= pd.Timedelta(days=2), "index"].unique()
    out = pd.concat([vh, wk.drop(index=dup_idx)], ignore_index=True).drop(columns="k")
    out["district"] = out["district"].fillna(0).astype(int)
    # Second pass: identical toplines in the same race within 2 days are the same poll
    # listed under different names ("Berkeley IGS" vs "UC Berkeley Institute of
    # Governmental Studies", "PennLive" vs its pollster "Bravo Group"). Keep VoteHub's row.
    out = out.sort_values(race + ["dem_pct", "rep_pct", "end_date", "source"]).reset_index(drop=True)
    same = out[race + ["dem_pct", "rep_pct"]].eq(out[race + ["dem_pct", "rep_pct"]].shift()).all(axis=1)
    close = (out["end_date"] - out["end_date"].shift()).abs() <= pd.Timedelta(days=2)
    out = out[~(same & close)]
    return out.sort_values(race + ["end_date"]).reset_index(drop=True)


DDHQ_GENERIC = "https://polls.decisiondeskhq.com/averages/generic-ballot/national/lv-rv-adults"


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
    vh = load_votehub(refresh)
    races = races_table()
    polls = combine(votehub_race_polls(vh, races), wikipedia_race_polls())
    polls.to_csv(PROC / "polls_2026_races.csv", index=False)
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
    app.to_csv(PROC / "polls_2026_approval.csv", index=False)

    print(f"Race polls: {len(polls)}  (by source: {polls['source'].value_counts().to_dict()})")
    print(polls.groupby("office").agg(polls=("pollster", "size"),
                                      races=("state_po", lambda s: len(set(zip(s, polls.loc[s.index, 'district'], polls.loc[s.index, 'special'])))),
                                      since_aug=("end_date", lambda d: (d >= "2026-08-01").sum())))
    print(f"Generic ballot polls: {len(gen)} (latest {gen['end_date'].max():%Y-%m-%d})")
    print(f"Trump approval polls: {len(app)} (latest {app['end_date'].max():%Y-%m-%d})")


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
