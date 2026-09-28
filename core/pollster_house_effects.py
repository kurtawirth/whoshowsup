"""Pollster house effects: does correcting each pollster's own lean make polls more accurate?

    .venv/Scripts/python.exe core/pollster_house_effects.py

538's archive of race polls in the final two months (1998-2022; 2024 from its full poll lists). Each poll's two-party margin is first
put on the model's footing (the undecided shift and the campaign-sponsor correction the model already
applies), then two kinds of house effect are tested:

  A  track record   the pollster's average miss against actual results in OTHER cycles, relative to
                    that cycle's overall miss (the national model's job), shrunk toward zero:
                    h = sum(miss) / (n + k)
  B  this cycle     how the pollster's polls compare with other pollsters' polls of the same races in the
                    same cycle (no results needed, so usable in real time), shrunk the same way

Scored like the other layers: within each held-out cycle, after removing that cycle's average miss,
per poll and per race average (each race's polls averaged, the way the model reads them). Lower is better.

Findings (2026-09-27): A helps the race averages the model uses (error 6.93 -> 6.75 with k = 10, better
in 2014, 2016, 2018, 2020 and 2022); B helps single polls but adds almost nothing to race averages
(averaging many firms already cancels their relative leans), nor on top of A. The model uses A.

Writes data/processed/pollster_house_effects.csv (the scores), data/processed/pollster_track_record.csv
(each firm's lean with k = 10: all cycles, and leaving each cycle out) and prints the findings.
"""
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "midterms_2026" / "models"))
sys.path.insert(0, str(ROOT / "core"))
import race_model as rm  # noqa: E402
import undecided_break as ub  # noqa: E402
import poll_archive as pa  # noqa: E402

PROC = ROOT / "data" / "processed"
STOP = {"the", "inc", "llc", "group", "research", "polling", "poll", "polls", "associates", "and", "of", "for", "at",
        "university", "college", "center", "centre", "institute", "survey", "surveys", "communications", "consulting",
        "company", "co", "partners", "analytics", "insights", "public", "opinion", "politics", "project"}
BRANDS = ["siena", "yougov", "emerson", "marist", "quinnipiac", "monmouth", "surveyusa", "rasmussen", "trafalgar",
          "insideradvantage", "fabrizio", "suffolk", "ipsos", "cnn", "fox", "gallup", "mason-dixon", "selzer"]


def house_key(name: str) -> str:
    """One key per polling firm across sources: 'The New York Times/Siena University' and 'Siena Research
    Institute / The New York Times' -> 'siena'; 'Public Policy Polling' -> 'ppp'."""
    s = str(name).lower()
    for b in BRANDS:
        if b in s:
            return b
    if "public policy polling" in s or s.strip() == "ppp":
        return "ppp"
    if "public opinion strategies" in s:
        return "pos"
    first = re.split(r"\s*/\s*|\s+for\s+|\s+\(", s)[0]
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", first).split() if w not in STOP]
    return " ".join(words[:2]) if words else s.strip()


KIND = {c: ("mid_" if c % 4 == 2 else "pres_") + ("Dpres" if p == "D" else "Rpres") for c, p in ub.PRES_PARTY.items()}


def data() -> pd.DataFrame:
    raw = pa.raw_polls()
    d = ub.polls()
    keep = raw[raw.type_simple.isin(["Sen-G", "Gov-G", "House-G"]) & raw.cycle.isin(ub.PRES_PARTY)
               & raw.time_to_election.between(0, 61)]
    keep = keep[keep.cand1_party.isin(["DEM", "REP"]) & keep.cand2_party.isin(["DEM", "REP"]) & (keep.cand1_party != keep.cand2_party)]
    # ub.polls() keeps rows in the same order before its own filters; rebuild them with the pollster attached
    dem1 = keep.cand1_party == "DEM"
    D = np.where(dem1, keep.cand1_pct, keep.cand2_pct)
    R = np.where(dem1, keep.cand2_pct, keep.cand1_pct)
    Da, Ra = np.where(dem1, keep.cand1_actual, keep.cand2_actual), np.where(dem1, keep.cand2_actual, keep.cand1_actual)
    d = pd.DataFrame({"cycle": keep.cycle.to_numpy(), "race": keep.race_id.to_numpy(), "office": keep.type_simple.str[:3].to_numpy(),
                      "pollster": keep.pollster.to_numpy(), "partisan": keep.partisan.map({"DEM": "D", "REP": "R"}).fillna("").to_numpy(),
                      "u": 100 - D - R, "m": 100 * (D - R) / (D + R), "actual": 100 * (Da - Ra) / (Da + Ra)})
    d = d[(d.u >= 0) & (d.u <= 40) & d.actual.abs().lt(60) & d.m.abs().lt(60)].copy()
    d["house"] = d.pollster.map(house_key)
    d["w"] = d.u / 100
    # the model's footing: undecided shift (relative lean for the cycle's kind of year) and sponsor correction
    office = d.office.map({"Sen": "SEN", "Gov": "GOV", "Hou": "HOUSE"})
    adj = np.zeros(len(d))
    for c, g in d.groupby("cycle"):
        idx = g.index
        adj[d.index.get_indexer(idx)] = rm.undecided_shift(g.m, g.w, KIND[c], typical=rm.typical_share(g.race, g.w)).to_numpy()
    bias = [rm.PARTISAN_BIAS[o].get(p, 0.0) for o, p in zip(office, d.partisan)]
    d["adj"] = d.m + adj - np.array(bias)
    d["gap"] = d.actual - d.adj
    d["wt"] = 1 / d.groupby(["cycle", "race"])["m"].transform("size")
    d["resid"] = d.gap - d.groupby("cycle").gap.transform(lambda s: np.average(s, weights=d.loc[s.index, "wt"]))
    return d.reset_index(drop=True)


def track_record(train: pd.DataFrame, k: float) -> pd.Series:
    """Each firm's average miss vs results (cycle's own average miss removed), shrunk: sum / (n + k).
    Positive = the firm's polls ran too Republican (results came in more Democratic)."""
    g = train.groupby("house").resid
    return g.sum() / (g.size() + k)


def this_cycle(cyc: pd.DataFrame, k: float) -> pd.Series:
    """Each firm's lean vs other firms' polls of the same races in the same cycle, shrunk. No results used.
    Positive = the firm's polls run more Democratic than other firms' polls of the same races."""
    race_sum = cyc.groupby(["race", "house"]).adj.agg(["sum", "size"]).reset_index()
    tot = race_sum.groupby("race")[["sum", "size"]].sum()
    race_sum = race_sum.join(tot, on="race", rsuffix="_race")
    others = race_sum.size_race - race_sum["size"]
    race_sum = race_sum[others > 0]
    race_sum["dev"] = race_sum["sum"] / race_sum["size"] - (race_sum.sum_race - race_sum["sum"]) / others[others > 0]
    g = race_sum.groupby("house")
    return (g.apply(lambda x: (x.dev * x["size"]).sum(), include_groups=False) / (g["size"].sum() + k))


def evaluate(d: pd.DataFrame, form: str, kA: float = 20, kB: float = 5) -> dict:
    pred = np.zeros(len(d))
    for c in d.cycle.unique():
        te = (d.cycle == c).to_numpy()
        if form in ("A", "A+B"):
            hA = track_record(d[~te], kA)
            pred[te] += d.house[te].map(hA).fillna(0).to_numpy()  # add the firm's usual miss
        if form in ("B", "A+B"):
            hB = this_cycle(d[te], kB)
            pred[te] -= d.house[te].map(hB).fillna(0).to_numpy()  # remove the firm's lean vs its peers
    x = d.assign(err=d.resid - pred)
    x["err"] = x.err - x.groupby("cycle").err.transform(lambda s: np.average(s, weights=x.loc[s.index, "wt"]))
    race = x.groupby(["cycle", "race"]).agg(err=("err", "mean"))
    return {"form": form, "kA": kA, "kB": kB,
            "rmse_poll": float(np.sqrt(np.average(x.err ** 2, weights=x.wt))),
            "rmse_race_avg": float(np.sqrt((race.err ** 2).mean())),
            **{f"race_avg_{c}": float(np.sqrt((race.loc[c].err ** 2).mean())) for c in (2014, 2016, 2018, 2020, 2022)}}


def build(k: float = 10) -> pd.DataFrame:
    """The model's table: each firm's track-record lean (all cycles, and leaving out each cycle)."""
    d = data()
    t = pd.DataFrame({"n_polls": d.groupby("house").size(), "h_all": track_record(d, k)})
    for c in sorted(d.cycle.unique()):
        t[f"h_loo_{c}"] = track_record(d[d.cycle != c], k)
    t = t.fillna(0.0).rename_axis("house").reset_index()
    t.to_csv(PROC / "pollster_track_record.csv", index=False)
    return t


def main() -> None:
    build()
    d = data()
    print(f"{len(d):,} polls, {d.house.nunique():,} polling firms, {d.cycle.nunique()} cycles")
    rows = [evaluate(d, "none")]
    rows += [evaluate(d, "A", kA=k) for k in (5, 10, 20, 40, 80)]
    rows += [evaluate(d, "B", kB=k) for k in (1, 3, 5, 10, 20)]
    rows += [evaluate(d, "A+B", kA=kA, kB=kB) for kA in (20, 40) for kB in (3, 5, 10)]
    res = pd.DataFrame(rows)
    res.to_csv(PROC / "pollster_house_effects.csv", index=False)
    pd.set_option("display.width", 200)
    print(res.round(3).to_string(index=False))
    h = track_record(d, 20).sort_values()
    n = d.groupby("house").size()
    big = h[n.reindex(h.index) >= 40]
    print("\nLargest track-record leans among firms with 40+ polls (+ = polls ran too Republican):")
    print(pd.concat([big.head(8), big.tail(8)]).round(2).to_string())


if __name__ == "__main__":
    main()
