"""One row per federal election year (1976-2026): the national signals as they
stood on the forecast date, and the actual national House result.

Everything is measured AS OF the same calendar day (default Sept 22) so a
backtest only sees what was knowable on that day in each year.

Columns
  house_margin        actual national House two-party margin, D-R points (MEDSL)
  pres_party          party holding the White House ("D"/"R"); midterm flag
  approval, net_approval   president's job approval as of the forecast date:
                      Gallup (APP) through 2016; all-pollster average from 2017
  generic_margin      generic-ballot average D-R: 538's average through 2016,
                      our own per-pollster average of raw polls from 2018
  generic_lv_margin / generic_rv_margin   same, likely- vs registered-voter polls only
  specials_overperf   mean Democratic overperformance in D-vs-R specials so far this cycle
  last_pres_margin    national presidential two-party margin of the previous presidential election
  specials_implied    last_pres_margin + specials_overperf (a turnout-driven read on the environment)
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
FORECAST_MMDD = (9, 22)
WINDOW_DAYS = 30

# Party in the White House during each election year's campaign.
PRES_PARTY = {1976: "R", 1978: "D", 1980: "D", 1982: "R", 1984: "R", 1986: "R", 1988: "R", 1990: "R",
              1992: "R", 1994: "D", 1996: "D", 1998: "D", 2000: "D", 2002: "R", 2004: "R", 2006: "R",
              2008: "R", 2010: "D", 2012: "D", 2014: "D", 2016: "D", 2018: "R", 2020: "R", 2022: "D",
              2024: "D", 2026: "R"}


def asof(year: int) -> pd.Timestamp:
    return pd.Timestamp(year, *FORECAST_MMDD)


def house_margins() -> pd.Series:
    h = pd.read_csv(RAW / "medsl" / "house_1976_2024.tab", sep=None, engine="python", encoding="latin-1")
    h = h[(h["stage"].str.upper() == "GEN") & ~h["special"].astype(str).str.upper().eq("TRUE")]
    p = h["party"].astype(str).str.upper()
    d = h[p.str.contains("DEMOCRAT")].groupby("year")["candidatevotes"].sum()
    r = h[p.eq("REPUBLICAN")].groupby("year")["candidatevotes"].sum()
    return (100 * (d - r) / (d + r)).rename("house_margin")


def pres_margins() -> pd.Series:
    p = pd.read_csv(RAW / "medsl" / "president_1976_2024.csv", encoding="latin-1")
    g = p[p["party_simplified"].isin(["DEMOCRAT", "REPUBLICAN"])].groupby(["year", "party_simplified"])["candidatevotes"].sum().unstack()
    return 100 * (g["DEMOCRAT"] - g["REPUBLICAN"]) / (g["DEMOCRAT"] + g["REPUBLICAN"])


def _pollster_average(df: pd.DataFrame, day: pd.Timestamp, cols: list[str]) -> pd.Series:
    """Average of polls ending in the window before `day`, first averaging within
    each pollster so daily trackers don't dominate. If the window is empty
    (sparse early Gallup years), widen it to 60 days."""
    w = df[(df["end_date"] <= day) & (df["end_date"] > day - pd.Timedelta(days=WINDOW_DAYS))]
    if w.empty:
        w = df[(df["end_date"] <= day) & (df["end_date"] > day - pd.Timedelta(days=2 * WINDOW_DAYS))]
    if w.empty:
        return pd.Series({c: np.nan for c in cols} | {"n_polls": 0})
    per = w.groupby("pollster")[cols].mean()
    return pd.Series(per.mean().to_dict() | {"n_polls": len(w)})


def gallup_approval() -> pd.DataFrame:
    frames = []
    for f in (RAW / "app_approval").glob("g_*.csv"):
        d = pd.read_csv(f)
        d["end_date"] = pd.to_datetime(d["End Date"], format="mixed", errors="coerce")
        frames.append(d.rename(columns={"Approving": "approve", "Disapproving": "disapprove"}))
    d = pd.concat(frames).dropna(subset=["end_date"])
    return d.assign(pollster="Gallup")[["pollster", "end_date", "approve", "disapprove"]]


def modern_approval() -> pd.DataFrame:
    frames = []
    for f in ["president_approval_polls_historical.csv", "president_approval_polls.csv"]:
        d = pd.read_csv(RAW / "fte" / f, low_memory=False)
        d["end_date"] = pd.to_datetime(d["end_date"], format="%m/%d/%y")
        d = d.drop_duplicates("poll_id")  # one row per poll (several population versions exist)
        frames.append(d.rename(columns={"yes": "approve", "no": "disapprove"}))
    v = pd.read_csv(PROC / "polls_2026_approval.csv", parse_dates=["end_date"])
    frames.append(v)
    return pd.concat(frames)[["pollster", "end_date", "approve", "disapprove"]]


def generic_polls() -> pd.DataFrame:
    g = pd.read_csv(RAW / "fte" / "generic_ballot_polls_historical.csv", low_memory=False)
    g["end_date"] = pd.to_datetime(g["end_date"], format="%m/%d/%y")
    g = g[g["partisan"].isna()]  # nonpartisan only
    g = g.rename(columns={"dem": "dem_pct", "rep": "rep_pct"})[["pollster", "end_date", "population", "dem_pct", "rep_pct"]]
    v = pd.read_csv(PROC / "polls_2026_generic.csv", parse_dates=["end_date"])
    v = v[v["partisan"].isna()][["pollster", "end_date", "population", "dem_pct", "rep_pct"]]
    out = pd.concat([g, v])
    out["margin"] = out["dem_pct"] - out["rep_pct"]
    return out


def main() -> None:
    years = list(range(1976, 2027, 2))
    hm, pm = house_margins(), pres_margins()
    gal, mod, gen = gallup_approval(), modern_approval(), generic_polls()
    top = pd.read_csv(RAW / "fte" / "generic_topline_historical.csv")
    top["date"] = pd.to_datetime(top["modeldate"])
    spec = pd.read_csv(PROC / "special_elections.csv", parse_dates=["date"])

    rows = []
    for y in years:
        day = asof(y)
        appr_src = gal if y <= 2016 else mod
        a = _pollster_average(appr_src, day, ["approve", "disapprove"])
        row = {"year": y, "pres_party": PRES_PARTY[y], "midterm": y % 4 == 2,
               "house_margin": hm.get(y, np.nan),
               "approval": a["approve"], "net_approval": a["approve"] - a["disapprove"],
               "last_pres_margin": pm.get(y - 2 if y % 4 == 2 else y - 4, np.nan)}
        if y <= 2016:
            t = top[top["date"] == day]
            row["generic_margin"] = float(t["dem_estimate"].iloc[0] - t["rep_estimate"].iloc[0]) if len(t) else np.nan
        else:
            row["generic_margin"] = _pollster_average(gen, day, ["margin"])["margin"]
            for pop in ("lv", "rv"):
                row[f"generic_{pop}_margin"] = _pollster_average(gen[gen["population"] == pop], day, ["margin"])["margin"]
        cyc = spec[(spec["date"] >= pd.Timestamp(y - 1, 1, 1)) & (spec["date"] <= day)]
        row["specials_n"] = len(cyc)
        row["specials_overperf"] = cyc["overperformance"].mean() if len(cyc) >= 10 else np.nan
        rows.append(row)
    df = pd.DataFrame(rows)
    df["specials_implied"] = df["last_pres_margin"] + df["specials_overperf"]
    # Everything from the president's party's point of view (+ = good for the president's party).
    sign = np.where(df["pres_party"] == "D", 1, -1)
    df["house_margin_pres_party"] = sign * df["house_margin"]
    df.to_csv(PROC / "national_history.csv", index=False)
    pd.set_option("display.width", 220)
    print(df.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
