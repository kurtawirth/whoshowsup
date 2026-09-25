"""How far do Senate and Governor results stray from partisan lean + environment?

For each D-vs-R race:
    expected = state presidential lean + national House margin that year
    state lean = state pres margin - national pres margin (most recent pres election)
    resid = actual margin - expected
    resid = inc_effect * incumbent_side + noise

Senate: 2000-2024 (MEDSL state results). Governor: 2018 and 2022 (our county
data summed to state; incumbency only for 2022, from 2018 winners).
Incumbent = a candidate matching a previous winner of that office in the
state within the prior term.
"""
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
sys.path.insert(0, str(ROOT / "core"))
from house_calibration import _key  # noqa: E402


def pres_lean() -> pd.DataFrame:
    p = pd.read_csv(RAW / "medsl" / "president_1976_2024.csv", encoding="latin-1")
    p = p[p["party_simplified"].isin(["DEMOCRAT", "REPUBLICAN"])]
    st = p.groupby(["year", "state_po", "party_simplified"])["candidatevotes"].sum().unstack()
    st["m"] = 100 * (st["DEMOCRAT"] - st["REPUBLICAN"]) / (st["DEMOCRAT"] + st["REPUBLICAN"])
    nat = p.groupby(["year", "party_simplified"])["candidatevotes"].sum().unstack()
    nat_m = 100 * (nat["DEMOCRAT"] - nat["REPUBLICAN"]) / (nat["DEMOCRAT"] + nat["REPUBLICAN"])
    st = st.reset_index()
    st["lean"] = st["m"] - st["year"].map(nat_m)
    return st[["year", "state_po", "lean"]]


def lean_for(year: int, leans: pd.DataFrame) -> pd.DataFrame:
    py = year if year % 4 == 0 else year - 2
    return leans[leans["year"] == py][["state_po", "lean"]]


def senate() -> pd.DataFrame:
    s = pd.read_csv(RAW / "medsl" / "senate_1976_2024.csv", encoding="latin-1")
    s = s[(s["stage"].str.lower() == "gen") & (s["year"] >= 1994)]
    s["side"] = np.where(s["party_simplified"] == "DEMOCRAT", "D", np.where(s["party_simplified"] == "REPUBLICAN", "R", "O"))
    s["special"] = s["special"].astype(str).str.upper().eq("TRUE")
    # Fusion voting (New York): minor-party lines count for the nominee who holds them.
    major = s[s["side"] != "O"].groupby(["year", "state_po", "special", "candidate"])["side"].first()
    k = pd.MultiIndex.from_frame(s[["year", "state_po", "special", "candidate"]])
    s["side"] = np.where(s["side"] == "O", major.reindex(k).fillna("O").to_numpy(), s["side"])
    rows = []
    for (y, st, sp), g in s.groupby(["year", "state_po", "special"]):
        d, r = g.loc[g.side == "D", "candidatevotes"].sum(), g.loc[g.side == "R", "candidatevotes"].sum()
        if d == 0 or r == 0 or min(d, r) / (d + r) < 0.15:
            continue  # need a real D-vs-R contest
        w = g.groupby(["candidate", "side"], as_index=False)["candidatevotes"].sum().sort_values("candidatevotes").iloc[-1]
        rows.append({"year": y, "state_po": st, "special": sp, "margin": 100 * (d - r) / (d + r),
                     "winner": w["candidate"], "winner_side": w["side"],
                     "dem_key": _key(g.loc[g.side == "D"].sort_values("candidatevotes").iloc[-1]["candidate"]),
                     "rep_key": _key(g.loc[g.side == "R"].sort_values("candidatevotes").iloc[-1]["candidate"])})
    df = pd.DataFrame(rows)
    # Incumbent = the D or R nominee won a Senate race in this state in the previous 6 years.
    prior = s[s["candidatevotes"] == s.groupby(["year", "state_po", "special"])["candidatevotes"].transform("max")]
    def inc(r):
        past = prior[(prior.state_po == r.state_po) & (prior.year < r.year) & (prior.year >= r.year - 6)]
        keys = {_key(c) for c in past["candidate"]}
        return 1 if r.dem_key in keys else -1 if r.rep_key in keys else 0
    df["incumbent_side"] = df.apply(inc, axis=1)
    return df.assign(office="SEN")


def governor() -> pd.DataFrame:
    c = pd.read_parquet(PROC / "county_results.parquet")
    g = c[c["office"] == "GOV"].groupby(["year", "state_po"])[["dem", "rep"]].sum().reset_index()
    g = g[(g[["dem", "rep"]].min(axis=1) / (g["dem"] + g["rep"])) > 0.15]
    g["margin"] = 100 * (g["dem"] - g["rep"]) / (g["dem"] + g["rep"])
    # 2022 incumbency: did the 2018 winner's party hold... we only know party, not names, from county
    # data, so incumbents come from a short hand list of 2022 governors who ran for re-election.
    inc22 = {"D": ["CA", "CO", "CT", "IL", "KS", "ME", "MI", "MN", "NM", "NY", "OR", "PA", "RI", "WI"],
             "R": ["AL", "AR", "FL", "GA", "IA", "ID", "NE", "NH", "NV", "OH", "OK", "SC", "SD", "TN", "TX", "VT", "WY"]}
    g["incumbent_side"] = np.nan
    for side, states in inc22.items():
        g.loc[(g.year == 2022) & g.state_po.isin(states), "incumbent_side"] = 1 if side == "D" else -1
    g.loc[(g.year == 2022) & g.incumbent_side.isna(), "incumbent_side"] = 0
    return g.assign(office="GOV", special=False)[["year", "state_po", "special", "margin", "incumbent_side", "office"]]


def main() -> None:
    leans = pres_lean()
    nat = pd.read_csv(PROC / "national_history.csv").set_index("year")["house_margin"]
    df = pd.concat([senate(), governor()], ignore_index=True)
    df = pd.concat([df[df.year == y].merge(lean_for(y, leans), on="state_po") for y in df.year.unique()])
    df["expected"] = df["lean"] + df["year"].map(nat)
    df["resid"] = df["margin"] - df["expected"]
    df.to_csv(PROC / "statewide_calibration.csv", index=False)
    pd.set_option("display.width", 200)
    for off in ("SEN", "GOV"):
        d = df[(df.office == off) & df.incumbent_side.notna()]
        m = smf.ols("resid ~ incumbent_side", data=d).fit()
        print(f"{off}: n={len(d)}, incumbency {m.params['incumbent_side']:.2f} (se {m.bse['incumbent_side']:.2f}), "
              f"residual sd {m.resid.std():.2f}; all races resid sd {df[df.office == off].resid.std():.2f}")
        recent = d[d.year >= 2012]
        if off == "SEN" and len(recent) > 20:
            mr = smf.ols("resid ~ incumbent_side", data=recent).fit()
            print(f"   SEN since 2012: n={len(recent)}, incumbency {mr.params['incumbent_side']:.2f}, residual sd {mr.resid.std():.2f}")


if __name__ == "__main__":
    main()
