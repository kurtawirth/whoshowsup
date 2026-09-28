"""Primary turnout as an enthusiasm signal: does a party's primary turnout predict its general election?

    .venv/Scripts/python.exe core/primary_turnout.py

Source: the FEC's "Federal Elections" results books (2006-2022; data/raw/fec_results/), which list every
House and Senate candidate's primary and general votes.

Measure: the Democratic share of the two parties' House primary votes, counting only districts where
BOTH parties' primaries have a vote count (so an unopposed candidate left off one party's ballot doesn't
swing the share). Top-two / jungle primary states (CA, WA, LA; AK from 2022) are out. Three tests:

  1  state swings   a state's change in primary share (vs two years earlier, relative to the nation) vs
                    its change in the House general vote
  2  model misses   a district's primary share relative to its partisanship vs what the backtest model
                    (Sept 22) missed, fitted on the other years and applied to the held-out year
  3  national       the nation's primary share vs the national model's miss, leaving each year out

Findings (2026-09-27): 1 is real but modest (correlation +0.03 to +0.60, positive every year; 10 points
of primary share ~ 1 point of general vote). But the model already knows it: 2 doesn't help competitive
races in any year (error 4.89 -> 5.02 in 2018, 4.50 -> 4.51 in 2020, 5.06 -> 5.11 in 2022), and the
slope flips sign between years. 3 helps a hair across five midterms (1.07 -> 1.01) and hurts across all
nine years (2.25 -> 2.70; presidential primaries swamp it). Not in the model.

Writes data/processed/primary_turnout.csv (state table) and primary_turnout_tests.csv.
"""
from pathlib import Path
import re

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "fec_results"
PROC = ROOT / "data" / "processed"
YEARS = range(2006, 2023, 2)
SHEETS = {2006: "2006 US House & Senate Results", 2008: "2008 House and Senate Results",
          2010: "2010 US House & Senate Results", 2012: "2012 US House & Senate Resuts",
          2014: "2014 US House Results by State", 2016: "2016 US House Results by State",
          2018: "2018 US House Results by State", 2020: "13. US House Results by State",
          2022: "8. US House Results by State"}
SEN_SHEETS = {2014: "2014 US Senate Results by State", 2016: "2016 US Senate Results by State",
              2018: "2018 US Senate Results by State", 2020: "12. US Senate Results by State",
              2022: "7. US Senate Results by State"}
NONPARTISAN = {"CA", "WA", "LA"}


def _col(d: pd.DataFrame, *pats: str) -> str:
    for p in pats:
        for c in d.columns:
            if re.fullmatch(p, str(c).strip(), flags=re.I):
                return c
    raise KeyError(pats)


def _num(v) -> float:
    if isinstance(v, (int, float, np.integer, np.floating)) and not pd.isna(v):
        return float(v)
    return np.nan


def _party(p) -> str:
    s = re.sub(r"[^A-Z()]", "", str(p).upper())
    if s.startswith("W") or s.startswith("N("):  # write-ins, nominated by other parties
        return ""
    return {"DEM": "D", "D": "D", "DFL": "D", "REP": "R", "R": "R"}.get(s, "")


def candidates(year: int, senate: bool = False) -> pd.DataFrame:
    """One row per candidate: state, district ('S' for Senate), party (D/R/''), primary and general votes."""
    f = RAW / f"federalelections{year}.{'xls' if year < 2016 else 'xlsx'}"
    sheet = SEN_SHEETS.get(year) if senate else SHEETS[year]
    if sheet is None:  # 2006-2012: House and Senate share one sheet
        sheet = SHEETS[year]
    d = pd.read_excel(f, sheet_name=sheet)
    st, dist = _col(d, "STATE ABBREVIATION"), _col(d, "DISTRICT", "D")
    name = _col(d, "CANDIDATE NAME", "CANDIDATE NAME \\(Last, First\\)", "LAST NAME, FIRST")
    pri, gen = _col(d, "PRIMARY VOTES", "PRIMARY"), _col(d, "GENERAL VOTES", "GENERAL")
    party = _col(d, "PARTY")
    nm = d[name].astype(str).str.strip()
    keep = d[name].notna() & ~nm.str.contains(r"scatter|all others|total|votes|none of", case=False) & d[st].notna()
    d = d[keep]
    out = pd.DataFrame({"year": year, "state_po": d[st].astype(str).str.strip(),
                        "district": d[dist].astype(str).str.strip().str.upper(),
                        "name": nm[keep], "party": d[party].map(_party),
                        "primary": d[pri].map(_num), "primary_raw": d[pri].astype(str),
                        "general": d[gen].map(_num)})
    is_sen = out.district.str.startswith("S")
    return out[is_sen] if senate else out[~is_sen]


def district_table() -> pd.DataFrame:
    """Per district and year: each party's primary votes (NaN when no count) and general votes."""
    rows = []
    for y in YEARS:
        c = candidates(y)
        c = c[c.party != ""]
        g = c.groupby(["year", "state_po", "district", "party"]).agg(
            primary=("primary", lambda s: s.sum(min_count=1)), general=("general", lambda s: s.sum(min_count=1)),
            n=("name", "size")).unstack("party")
        g.columns = [f"{a}_{b}" for a, b in g.columns]
        rows.append(g.reset_index())
    d = pd.concat(rows, ignore_index=True)
    for c in ["primary_D", "primary_R", "general_D", "general_R"]:
        if c not in d:
            d[c] = np.nan
    return d


def state_table(d: pd.DataFrame) -> pd.DataFrame:
    x = d[~d.state_po.isin(NONPARTISAN) & ~((d.state_po == "AK") & (d.year >= 2022))].copy()
    both_pri = (x.primary_D > 0) & (x.primary_R > 0)
    both_gen = (x.general_D > 0) & (x.general_R > 0)
    p = x[both_pri].groupby(["year", "state_po"]).agg(pD=("primary_D", "sum"), pR=("primary_R", "sum"),
                                                     n_pri=("district", "size"))
    g = x[both_gen].groupby(["year", "state_po"]).agg(gD=("general_D", "sum"), gR=("general_R", "sum"))
    n = x.groupby(["year", "state_po"]).size().rename("n_dist")
    s = p.join(g, how="outer").join(n).reset_index()
    s["pri_share"] = 100 * s.pD / (s.pD + s.pR)
    s["gen_share"] = 100 * s.gD / (s.gD + s.gR)
    s["pri_turnout_ratio"] = (s.pD + s.pR) / (s.gD + s.gR)
    return s


def district_primary(d: pd.DataFrame) -> pd.DataFrame:
    x = d[(d.primary_D > 0) & (d.primary_R > 0) & ~d.state_po.isin(NONPARTISAN)].copy()
    x["district"] = pd.to_numeric(x.district.str.extract(r"(\d+)")[0], errors="coerce").fillna(0).astype(int)
    x["pri_share"] = 100 * x.primary_D / (x.primary_D + x.primary_R)
    return x[["year", "state_po", "district", "pri_share"]]


def main() -> None:
    d = district_table()
    s = state_table(d).set_index(["state_po", "year"])
    s.reset_index().to_csv(PROC / "primary_turnout.csv", index=False)
    rows = []

    # 1. Raw swings: the state's primary-share change vs its general-share change (both relative to the nation)
    for y in range(2008, 2023, 2):
        a, b = s.xs(y, level="year"), s.xs(y - 2, level="year")
        j = pd.DataFrame({"dp": a.pri_share - b.pri_share, "dg": a.gen_share - b.gen_share}).dropna()
        j = j - j.mean()
        rows.append({"test": "state swing", "year": y, "n": len(j), "corr": j.dp.corr(j.dg)})

    # 2. The model's misses (backtest, Sept 22): district primary share vs district partisanship, fitted on
    #    the other years, added to the held-out year's forecasts (centered, so no net shift)
    r = pd.read_csv(ROOT / "midterms_2026" / "outputs" / "backtest_race_forecasts.csv")
    r = r[r.office == "HOUSE"].merge(district_primary(d), on=["year", "state_po", "district"])
    r["x"] = r.pri_share - r.pres24
    r["x"] -= r.groupby("year").x.transform("mean")
    r["res"] = r.actual - r.margin_median
    r["res"] -= r.groupby("year").res.transform("mean")
    for label, sub in [("model miss, all races", r), ("model miss, competitive", r[r.margin_median.abs() < 15])]:
        for y in sorted(sub.year.unique()):
            tr, te = sub[sub.year != y], sub[sub.year == y]
            b = float((tr.x * tr.res).sum() / (tr.x ** 2).sum())
            rows.append({"test": label, "year": y, "n": len(te), "slope": b,
                         "rmse_before": float(np.sqrt((te.res ** 2).mean())),
                         "rmse_after": float(np.sqrt(((te.res - b * te.x) ** 2).mean()))})

    # 3. National: the Democratic share of all primary votes (states with counts every year) vs the national
    #    model's miss, leaving each year out
    keep = s.dropna(subset=["pri_share"]).reset_index().groupby("state_po").year.nunique()
    keep = keep[keep == len(YEARS)].index
    n = s.reset_index()
    n = n[n.state_po.isin(keep)].groupby("year")[["pD", "pR"]].sum()
    n["pri"] = 100 * n.pD / (n.pD + n.pR)
    e = pd.read_csv(ROOT / "midterms_2026" / "outputs" / "national_env_backtest.csv").set_index("year")
    n["miss"] = e.actual - e.predicted
    for label, sub in [("national, midterms", n[n.index % 4 == 2]), ("national, all years", n)]:
        e0, e1 = [], []
        for y in sub.index:
            tr = sub.drop(y)
            b = np.polyfit(tr.pri, tr.miss, 1)
            e0.append(sub.miss[y])
            e1.append(sub.miss[y] - np.polyval(b, sub.pri[y]))
        rows.append({"test": label, "year": "LOO", "n": len(sub), "rmse_before": float(np.sqrt(np.mean(np.square(e0)))),
                     "rmse_after": float(np.sqrt(np.mean(np.square(e1))))})

    out = pd.DataFrame(rows)
    out.to_csv(PROC / "primary_turnout_tests.csv", index=False)
    pd.set_option("display.width", 200)
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
