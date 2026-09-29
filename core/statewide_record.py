"""A challenger's statewide track record: does running ahead of the state before carry over?

    .venv/Scripts/python.exe core/statewide_record.py

The race model already carries part of an INCUMBENT's personal vote into their re-election
(race_model.PERSONAL, core/statewide_personal_vote.py). This asks the same of Senate and governor nominees
who are NOT the incumbent in this race but have run statewide before -- for Senate, governor, or a state's
single at-large U.S. House seat (Alaska, Delaware, Montana until 2022, North Dakota, South Dakota, Vermont,
Wyoming), whose electorate is the whole state. Examples: Mary Peltola (Alaska House 2022-24, Senate 2026),
Kevin Cramer (North Dakota House 2016, Senate 2018), Larry Hogan (Maryland governor 2018, Senate 2024).

Every statewide run's residual is its D-R margin minus (the state's presidential lean + that year's
national House margin), as in core/statewide_calibration.py, less the usual incumbency bonus
(INCUMBENCY) when one of the two was the incumbent then: a record should measure the candidate, not
the office they held or the incumbent they ran against. Races where a third candidate took 30% or more
(Connecticut's 2006 Senate race, with Lieberman as an independent) aren't described by a D-R margin and
are left out. A nominee's record = their most recent statewide run in the same state within
RECORD_WINDOW years, for the same party, turned toward their party.
One row per Senate/governor race (Senate 1996-2024, governors 2008-2024):

    resid = b_inc * incumbent_side + rho * (D nominee's record - R nominee's record) + c * (has_D - has_R)

rho is what the race model adds (race_model.CHALLENGER; `has` is left to the candidate-experience
tiers, which already credit former officeholders). Fit with a Huber line, as the incumbents' personal
vote is, so a few extreme records don't set it. Writes data/processed/statewide_records.csv (every
statewide run) and data/processed/statewide_record_races.csv (the fitting table), prints fits by office,
era and leaving each year out.
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
RECORD_WINDOW = 12
INCUMBENCY = {"SEN": 5.4, "GOV": 4.5, "HOUSE_AL": 2.3}  # race_model.INCUMBENCY
sys.path.insert(0, str(ROOT / "core"))
from house_calibration import _key  # noqa: E402
from statewide_calibration import pres_lean, lean_for  # noqa: E402


def at_large_house() -> pd.DataFrame:
    """Contested general elections for states' single at-large House seat, both nominees named."""
    h = pd.read_csv(RAW / "medsl" / "house_1976_2024.tab", sep=None, engine="python", encoding="latin-1")
    h = h[(h["stage"].str.upper() == "GEN") & ~h["special"].astype(str).str.upper().eq("TRUE") & (h["year"] >= 1994)]
    h["district"] = pd.to_numeric(h["district"], errors="coerce").fillna(0).astype(int)
    seats = h.groupby(["year", "state_po"])["district"].max()
    h = h[h.set_index(["year", "state_po"]).index.isin(seats[seats == 0].index)]
    party = h["party"].astype(str).str.upper()
    h["side"] = np.where(party.str.contains("DEMOCRAT"), "D", np.where(party.eq("REPUBLICAN"), "R", "O"))
    rows = []
    total = h.groupby(["year", "state_po"])["candidatevotes"].sum()
    for (y, st), g in h[h["side"] != "O"].groupby(["year", "state_po"]):
        tot = g.groupby(["candidate", "side"], as_index=False)["candidatevotes"].sum()
        d, r = tot[tot.side == "D"], tot[tot.side == "R"]
        if d.empty or r.empty:
            continue
        dv, rv = d["candidatevotes"].sum(), r["candidatevotes"].sum()
        if min(dv, rv) / (dv + rv) < 0.15 or (dv + rv) / total[(y, st)] < 0.7:
            continue
        rows.append({"year": y, "state_po": st, "office": "HOUSE_AL", "margin": 100 * (dv - rv) / (dv + rv),
                     "dem_key": _key(d.sort_values("candidatevotes").iloc[-1]["candidate"]),
                     "rep_key": _key(r.sort_values("candidatevotes").iloc[-1]["candidate"])})
    df = pd.DataFrame(rows)
    leans = pres_lean()
    nat = pd.read_csv(PROC / "national_history.csv").set_index("year")["house_margin"]
    df = pd.concat([df[df.year == y].merge(lean_for(y, leans), on="state_po") for y in df.year.unique()])
    df["resid"] = df["margin"] - (df["lean"] + df["year"].map(nat))
    inc = pd.read_csv(PROC / "house_personal_edges.csv").query("district == 0").set_index(["year", "state_po"])["incumbent_side"]
    df["incumbent_side"] = inc.reindex(pd.MultiIndex.from_frame(df[["year", "state_po"]])).fillna(0).to_numpy()
    return df


def senate_two_way() -> pd.Series:
    """Share of the Senate vote won by the D and R nominees together, by (year, state, special)."""
    s = pd.read_csv(RAW / "medsl" / "senate_1976_2024.csv", encoding="latin-1")
    s = s[(s["stage"].str.lower() == "gen") & (s["year"] >= 1994)]
    s["special"] = s["special"].astype(str).str.upper().eq("TRUE")
    two = s[s["party_simplified"].isin(["DEMOCRAT", "REPUBLICAN"])].groupby(["year", "state_po", "special"])["candidatevotes"].sum()
    return two / s.groupby(["year", "state_po", "special"])["candidatevotes"].sum()


def runs() -> pd.DataFrame:
    """Every statewide run, one row per nominee: year, state, office, candidate key, party side, edge."""
    cal = pd.read_csv(PROC / "statewide_calibration.csv")
    share = senate_two_way()
    sen = cal.office == "SEN"
    cal = cal[~sen | (share.reindex(pd.MultiIndex.from_frame(cal[["year", "state_po", "special"]])).to_numpy() >= 0.7)]
    cols = ["year", "state_po", "office", "dem_key", "rep_key", "resid", "incumbent_side"]
    races = pd.concat([cal[cols], at_large_house()[cols]])
    races["resid"] = races["resid"] - races["office"].map(INCUMBENCY) * races["incumbent_side"].fillna(0)
    d = races.rename(columns={"dem_key": "key"}).assign(side=1)
    r = races.rename(columns={"rep_key": "key"}).assign(side=-1)
    out = pd.concat([d.drop(columns="rep_key"), r.drop(columns="dem_key")], ignore_index=True)
    out["edge"] = out["side"] * out["resid"]
    return out[["year", "state_po", "office", "key", "side", "edge"]].sort_values(["year", "state_po"])


def record(rn: pd.DataFrame, year: int, state: str, key: str, side: int) -> tuple[float, str]:
    """A nominee's most recent earlier statewide run (same state and party), or NaN."""
    if not isinstance(key, str) or not key:
        return np.nan, ""
    hit = rn[(rn.state_po == state) & (rn.key == key) & (rn.side == side)
             & (rn.year < year) & (rn.year >= year - RECORD_WINDOW)]
    if hit.empty:
        return np.nan, ""
    h = hit.sort_values("year").iloc[-1]
    return float(h.edge), f"{h.office} {h.year}"


def race_table() -> pd.DataFrame:
    cal = pd.read_csv(PROC / "statewide_calibration.csv")
    cal = cal[((cal.office == "SEN") & (cal.year >= 1996)) | ((cal.office == "GOV") & (cal.year >= 2008))].copy()
    rn = runs()
    rows = []
    for r in cal.itertuples():
        inc = int(r.incumbent_side) if pd.notna(r.incumbent_side) else 0
        rec = {}
        for side, key in ((1, r.dem_key), (-1, r.rep_key)):
            # an incumbent's own record is the personal vote the model already uses
            rec[side] = record(rn, r.year, r.state_po, key, side) if side != inc else (np.nan, "")
        rows.append({"year": r.year, "office": r.office, "state_po": r.state_po, "special": r.special,
                     "resid": r.resid, "inc": inc, "rec_d": rec[1][0], "rec_r": rec[-1][0],
                     "from_d": rec[1][1], "from_r": rec[-1][1], "dem_key": r.dem_key, "rep_key": r.rep_key})
    t = pd.DataFrame(rows)
    t["has"] = t["rec_d"].notna().astype(int) - t["rec_r"].notna().astype(int)
    t["rec"] = t["rec_d"].fillna(0) - t["rec_r"].fillna(0)
    return t


def fit(t: pd.DataFrame, robust: bool = True) -> dict:
    m = smf.ols("resid ~ inc + rec + has", data=t).fit()
    line = smf.rlm("resid ~ inc + rec + has", data=t).fit().params if robust else m.params
    return {"rho": float(line["rec"]), "se": float(m.bse["rec"]), "has": float(line["has"]),
            "n": int(m.nobs), "n_rec": int((t["rec"] != 0).sum())}


def main() -> None:
    rn = runs()
    rn.to_csv(PROC / "statewide_records.csv", index=False)
    t = race_table()
    t.to_csv(PROC / "statewide_record_races.csv", index=False)
    pd.set_option("display.width", 220)
    print(t[(t.rec != 0)].sort_values("year")[["year", "office", "state_po", "dem_key", "from_d", "rec_d",
                                               "rep_key", "from_r", "rec_r", "inc", "resid"]].round(1).to_string(index=False))
    for off in ("SEN", "GOV", None):
        x = t if off is None else t[t.office == off]
        f = fit(x)
        print(f"\n{off or 'BOTH'}: rho {f['rho']:.2f} (se {f['se']:.2f}), has-record {f['has']:+.2f}; "
              f"{f['n']} races, {f['n_rec']} with a challenger record")
        for lo, hi in [(1996, 2008), (2010, 2016), (2018, 2024), (2010, 2024)]:
            y = x[x.year.between(lo, hi)]
            if (y.rec != 0).sum() >= 5:
                g = fit(y)
                print(f"   {lo}-{hi}: rho {g['rho']:.2f} (se {g['se']:.2f}), n with record {g['n_rec']}")
    for yr in range(2010, 2025, 2):
        g = fit(t[t.year != yr])
        print(f"   without {yr}: rho {g['rho']:.2f}")


if __name__ == "__main__":
    main()
