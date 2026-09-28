"""538's complete race-poll lists, 2018-2024, as one head-to-head row per poll, with the actual result.

    .venv/Scripts/python.exe core/poll_archive.py

Source: FiveThirtyEight's senate_polls_historical.csv, house_polls_historical.csv and
governor_polls_historical.csv (Internet Archive snapshots of projects.fivethirtyeight.com/polls-page/data/,
taken after the 2024 election; data/raw/fte/). Unlike raw_polls.csv (the pollster-ratings file, which
keeps only each campaign's last ~60 days), these list every poll of the season.

Rows are answers (one per candidate per question). For each question we keep the general-election
matchup between the eventual Democratic and Republican nominees (matched by last name to the official
results), not hypothetical, first-round only. One version per poll: likely voters, then registered
voters, then all voters, then adults; then the question with the fullest ballot.

Also gives raw_polls(): 538's raw_polls.csv (1998-2022) plus 2024 from these lists in the same shape and
window (last 61 days), for the layers fit on past polls.

Output: data/processed/poll_archive_538.csv
"""
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FTE = ROOT / "data" / "raw" / "fte"
PROC = ROOT / "data" / "processed"
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "midterms_2026"))
from build_races import STATE_PO  # noqa: E402
from house_calibration import house_results  # noqa: E402

FILES = {"SEN": "senate_polls_historical.csv", "HOUSE": "house_polls_historical.csv", "GOV": "governor_polls_historical.csv"}
ELECTION = {2018: "2018-11-06", 2020: "2020-11-03", 2022: "2022-11-08", 2024: "2024-11-05"}
POP_RANK = {"lv": 0, "rv": 1, "v": 2, "a": 3}


def surname(name) -> str:
    parts = re.sub(r"[^a-z\- ]", " ", str(name).lower().replace("-", " - ")).split()
    parts = [p for p in parts if p not in {"jr", "sr", "ii", "iii", "iv", "-"}]
    return parts[-1] if parts else ""


def results() -> pd.DataFrame:
    """Nominees and two-party result of every 2018-2024 race: office, state, district, special."""
    rows = []
    s = pd.read_csv(ROOT / "data" / "raw" / "medsl" / "senate_1976_2024.csv", encoding="latin-1")
    s = s[(s.year >= 2018) & (s.stage.str.lower() == "gen")]
    s["special"] = s["special"].astype(str).str.upper().eq("TRUE")
    for (y, st, sp), g in s.groupby(["year", "state_po", "special"]):
        v = lambda p: g[g.party_simplified == p].groupby("candidate").candidatevotes.sum().sort_values()
        d, r = v("DEMOCRAT"), v("REPUBLICAN")
        if len(d) and len(r):
            rows.append({"cycle": y, "office": "SEN", "state_po": st, "district": 0, "special": sp,
                         "dem": d.index[-1], "rep": r.index[-1], "actual_dem": d.sum(), "actual_rep": r.sum()})
    h = house_results()
    h = h[(h.year >= 2018) & h.contested]
    raw = pd.read_csv(ROOT / "data" / "raw" / "medsl" / "house_1976_2024.tab", sep=None, engine="python", encoding="latin-1")
    raw = raw[(raw.year >= 2018) & (raw.stage.str.upper() == "GEN")]
    raw["party"] = raw.party.astype(str).str.upper()
    top = lambda cond: raw[cond].sort_values("candidatevotes").groupby(["year", "state_po", "district"]).candidate.last()
    dn, rn = top(raw.party.str.contains("DEMOCRAT")), top(raw.party.eq("REPUBLICAN"))
    for r in h.itertuples():
        k = (r.year, r.state_po, r.district)
        if k in dn.index and k in rn.index:
            rows.append({"cycle": r.year, "office": "HOUSE", "state_po": r.state_po, "district": r.district, "special": False,
                         "dem": dn[k], "rep": rn[k], "actual_dem": r.dem, "actual_rep": r.rep})
    g = pd.read_csv(PROC / "governor_results.csv")
    for r in g[(g.year >= 2018) & g.margin.notna()].itertuples():
        rows.append({"cycle": r.year, "office": "GOV", "state_po": r.state_po, "district": 0, "special": False,
                     "dem": r.dem, "rep": r.rep, "actual_dem": r.dem_pct, "actual_rep": r.rep_pct})
    out = pd.DataFrame(rows)
    out["dem_sn"], out["rep_sn"] = out.dem.map(surname), out.rep.map(surname)
    return out


def head_to_heads() -> pd.DataFrame:
    res = results()
    at_large = set(res[(res.office == "HOUSE")].groupby("state_po").district.max().loc[lambda s: s == 0].index)
    out = []
    for office, f in FILES.items():
        d = pd.read_csv(FTE / f, low_memory=False, encoding="latin-1")
        d = d[(d.stage == "general") & ~d.hypothetical.fillna(False).astype(bool)
              & ~d.ranked_choice_reallocated.fillna(False).astype(bool) & d.cycle.isin(ELECTION)]
        d["state_po"] = d.state.map(STATE_PO)
        d = d[d.state_po.notna()]
        d["district"] = 0 if office != "HOUSE" else np.where(d.state_po.isin(at_large), 0, d.seat_number.fillna(0)).astype(int)
        n_ans = d.groupby("question_id").size().rename("n_answers")
        dem = d[d.party == "DEM"].groupby("question_id").filter(lambda x: len(x) == 1)
        rep = d[d.party == "REP"].groupby("question_id").filter(lambda x: len(x) == 1)
        q = dem.merge(rep[["question_id", "candidate_name", "pct"]], on="question_id", suffixes=("_d", "_r"))
        q = q.join(n_ans, on="question_id")
        q["dem_sn"], q["rep_sn"] = q.candidate_name_d.map(surname), q.candidate_name_r.map(surname)
        q = q.merge(res[res.office == office], on=["cycle", "state_po", "district", "dem_sn", "rep_sn"], how="inner")
        out.append(q.assign(office=office))
    q = pd.concat(out, ignore_index=True)
    q["end"] = pd.to_datetime(q.end_date, format="%m/%d/%y")
    q["start"] = pd.to_datetime(q.start_date, format="%m/%d/%y")
    q["days"] = (pd.to_datetime(q.cycle.map(ELECTION)) - q.end).dt.days
    q["pop_rank"] = q.population.map(POP_RANK).fillna(4)
    q = q.sort_values(["pop_rank", "n_answers"], ascending=[True, False])
    q = q.drop_duplicates(["poll_id", "office", "state_po", "district", "special"])
    keep = {"poll_id": "poll_id", "question_id": "question_id", "cycle": "cycle", "office": "office",
            "state_po": "state_po", "district": "district", "special": "special", "pollster": "pollster",
            "display_name": "display_name", "partisan": "partisan", "internal": "internal",
            "population": "population", "sample_size": "sample_size", "start": "start_date", "end": "end_date",
            "days": "days", "candidate_name_d": "dem_name", "candidate_name_r": "rep_name",
            "pct_d": "dem_pct", "pct_r": "rep_pct", "n_answers": "n_answers",
            "actual_dem": "actual_dem", "actual_rep": "actual_rep"}
    q = q[list(keep)].rename(columns=keep)
    return q.sort_values(["cycle", "office", "state_po", "district", "end_date"]).reset_index(drop=True)


def raw_polls() -> pd.DataFrame:
    """538's raw_polls.csv (1998-2022, last ~61 days) plus 2024 from the full lists, same columns and window."""
    rp = pd.read_csv(FTE / "raw_polls.csv", low_memory=False)
    a = pd.read_csv(PROC / "poll_archive_538.csv")
    a = a[(a.cycle == 2024) & a.days.between(0, 61)]
    tot = a.actual_dem + a.actual_rep
    loc = np.where(a.office == "HOUSE", a.state_po + "-" + a.district.astype(str).str.zfill(2), a.state_po)
    add = pd.DataFrame({
        "poll_id": a.poll_id, "question_id": a.question_id, "cycle": a.cycle,
        "race_id": "2024" + a.office + a.state_po + a.district.astype(str) + a.special.astype(str),
        "location": loc, "type_simple": a.office.map({"SEN": "Sen-G", "GOV": "Gov-G", "HOUSE": "House-G"}),
        "pollster": a.display_name.fillna(a.pollster), "partisan": a.partisan.where(a.partisan.isin(["DEM", "REP"])),
        "samplesize": a.sample_size, "cand1_name": a.dem_name, "cand1_party": "DEM", "cand1_pct": a.dem_pct,
        "cand2_name": a.rep_name, "cand2_party": "REP", "cand2_pct": a.rep_pct,
        "cand1_actual": 100 * a.actual_dem / tot, "cand2_actual": 100 * a.actual_rep / tot,
        "electiondate": ELECTION[2024], "time_to_election": a.days, "polldate": a.end_date})
    add["race"] = "2024_" + add.type_simple + "_" + add.location
    add["margin_poll"] = add.cand1_pct - add.cand2_pct
    add["margin_actual"] = add.cand1_actual - add.cand2_actual
    return pd.concat([rp, add], ignore_index=True)


def main() -> None:
    q = head_to_heads()
    q.to_csv(PROC / "poll_archive_538.csv", index=False)
    print(f"{len(q)} head-to-head polls")
    print(q.groupby(["cycle", "office"]).agg(polls=("poll_id", "size"), races=("state_po", lambda s: 0))
          .drop(columns="races").unstack("office"))
    rp = pd.read_csv(FTE / "raw_polls.csv", low_memory=False)
    rp = rp[rp.type_simple.isin(["Sen-G", "Gov-G", "House-G"]) & rp.cycle.isin(ELECTION)]
    print("\nraw_polls.csv (last ~61 days only), same years:", rp.groupby("cycle").size().to_dict())
    print("full lists, 42+ days out:", q[q.days >= 42].groupby("cycle").size().to_dict())


if __name__ == "__main__":
    main()
