"""House incumbents' personal vote: does running ahead of your district last time carry over?

The race model gives every House incumbent the same flat bonus (2.3 pts). But some incumbents
run far ahead of their district's presidential lean, like Collin Peterson (D, Trump+31) or
John Katko (R, Biden+9), and do it again and again. Senate and Governor incumbents already get
this "personal vote" (race_model.PERSONAL). This script measures it for the House.

For every contested House race 2014-2024:

    edge = side * (house_margin - pres_margin - year_effect)

where pres_margin is the district's presidential margin on the same lines, the year effect is
that year's average House-vs-president gap (fit with an incumbency term so it isn't skewed
by which party holds more seats), and side = +1 for the Democrat, -1 for the Republican, so
edge is measured toward the winner. Then for incumbents running again:

    edge_next = intercept + rho * edge_prev + first_term_bump * (won the previous race as a non-incumbent)

The previous race is found by the incumbent's name within the state, so members whose
district number changed in redistricting still count. Fit on all years and leave one
year out (for the backtest). Writes data/processed/house_personal_edges.csv and prints the fit.

    .venv/Scripts/python.exe core/house_personal_vote.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "core"))
from house_calibration import house_results, _pres, _key  # noqa: E402

PROC = ROOT / "data" / "processed"

# Presidential margin by district on the lines each House election used.
# (file, D col, R col, header rows to skip, states whose lines differ from the file's)
PRES = {
    2014: [("1VfkHtzB_0.csv", 5, 6, 2, {"FL", "VA", "NC", "PA"})],        # 2012 pres; FL/VA/NC redrawn for 2016, PA 2018
    2016: [("1VfkHtzB_0.csv", 3, 4, 2, {"PA"})],                          # 2016 pres
    2018: [("1XbUXnI9_0.csv", 3, 4, 2, {"NC"}), ("1XbUXnI9_0.csv", 5, 6, 2, {"NC"})],  # avg of 2016 & 2020 pres
    2020: [("1XbUXnI9_0.csv", 3, 4, 2, set())],                           # 2020 pres
    2022: [("1CKngqOp_1871835782.csv", 3, 4, 1, set())],                  # 2020 pres, 2022 lines
    2024: [("tab_620838163.csv", 3, 4, 4, set())],                        # 2024 pres, 2024 lines
}


# The lean a forecaster actually had before each election: the most recent presidential result
# on that year's lines. The race model uses exactly this (2024 pres for 2026), so the carryover
# is fit against it -- a district still moving away from its last presidential result (2018's
# suburbs after 2016) then shows up as a smaller carryover instead of fooling the model.
KNOWN = {
    2016: [("1VfkHtzB_0.csv", 5, 6, 2, set())],                           # 2012 pres on 2016 lines
    2018: [("1XbUXnI9_0.csv", 5, 6, 2, {"NC"})],                          # 2016 pres on 2018 lines
    2020: [("1XbUXnI9_0.csv", 5, 6, 2, set())],                           # 2016 pres on 2020 lines
    2022: [("1CKngqOp_1871835782.csv", 3, 4, 1, set())],                  # 2020 pres, 2022 lines
    2024: [("tab_620838163.csv", 6, 7, 4, set())],                        # 2020 pres, 2024 lines
}


# States that redrew between 2024 and 2026: The Downballot's 2024 sheet is on the NEW lines there,
# so their 2024-lines results come from each state's Wikipedia "2024 presidential election in X"
# page ("By congressional district" table).
REDRAWN_FOR_2026 = {"CA": "California", "TX": "Texas", "FL": "Florida", "OH": "Ohio", "NC": "North_Carolina",
                    "TN": "Tennessee", "AL": "Alabama", "LA": "Louisiana", "UT": "Utah"}


def pres24_on_2024_lines() -> pd.DataFrame:
    import io
    import re
    sys.path.insert(0, str(ROOT / "midterms_2026" / "polls"))
    from scrape_wikipedia_polls import fetch
    rows = []
    for st, name in REDRAWN_FOR_2026.items():
        html = re.sub(r'(rowspan|colspan)="(\d+);?"', r'\1="\2"', fetch(f"2024_United_States_presidential_election_in_{name}"))
        t = [t for t in pd.read_html(io.StringIO(html)) if "District" in t.columns and "Harris" in t.columns][0]
        num = lambda c: pd.to_numeric(t[c].astype(str).str.replace("%", ""), errors="coerce")
        d = pd.DataFrame({"state_po": st, "district": pd.to_numeric(t["District"].astype(str).str.extract(r"(\d+)")[0], errors="coerce"),
                          "pres_margin": 100 * (num("Harris") - num("Trump")) / (num("Harris") + num("Trump"))})
        rows.append(d.dropna().drop_duplicates(["district"]))
    out = pd.concat(rows)
    out["district"] = out["district"].astype(int)
    return out


def district_pres(year: int, table: dict = PRES) -> pd.DataFrame:
    parts = []
    for f, cd, cr, skip, bad in table[year]:
        p = _pres(f, cd, cr, skip)
        parts.append(p[~p["state_po"].isin(bad)])
    out = pd.concat(parts).groupby(["state_po", "district"], as_index=False)["pres_margin"].mean()
    if year == 2024 and table is PRES:
        # that sheet rounds to whole percents; districts unchanged for 2026 have exact figures
        exact = pd.read_csv(PROC / "races_2026_house.csv")
        exact = exact.loc[~exact["lines_changed"], ["state_po", "district", "pres24_margin"]].set_index(["state_po", "district"])
        idx = out.set_index(["state_po", "district"]).index
        out["pres_margin"] = exact["pres24_margin"].reindex(idx).fillna(out.set_index(["state_po", "district"])["pres_margin"]).to_numpy()
        out = pd.concat([out[~out["state_po"].isin(REDRAWN_FOR_2026)], pres24_on_2024_lines()], ignore_index=True)
    return out


def edges() -> pd.DataFrame:
    """One row per contested House race: the winner's edge over lean + year effect."""
    hr = house_results()
    rows = []
    for y in PRES:
        cur = hr[(hr["year"] == y) & hr["contested"]].merge(district_pres(y), on=["state_po", "district"])
        prev = hr[hr["year"] == y - 2]
        # incumbent on the ballot: any previous winner from this state (handles renumbering)
        inc = []
        for s_, keys in zip(cur["state_po"], cur["cand_keys"]):
            hit = prev[(prev["state_po"] == s_) & prev["winner"].map(_key).isin(keys)]
            inc.append(0 if hit.empty else (1 if hit.iloc[0]["winner_side"] == "D" else -1))
        cur["incumbent_side"] = inc
        rows.append(cur)
    df = pd.concat(rows, ignore_index=True)
    # Token opposition (a write-in or paper candidate under 15% of the two-party vote) says
    # nothing about the winner's appeal; neither does Utah against Romney's 2012 home-state vote.
    df = df[(df["house_margin"].abs() <= 70) & ~((df["year"] == 2014) & (df["state_po"] == "UT"))].copy()
    df["resid_raw"] = df["house_margin"] - df["pres_margin"]
    fit = smf.ols("resid_raw ~ C(year) + incumbent_side", data=df).fit()
    fe = {y: fit.params["Intercept"] + fit.params.get(f"C(year)[T.{y}]", 0.0) for y in PRES}
    df["year_effect"] = df["year"].map(fe)
    df["winner_sign"] = np.where(df["winner_side"] == "D", 1, -1)
    df["winner_edge"] = df["winner_sign"] * (df["resid_raw"] - df["year_effect"])
    df["winner_key"] = df["winner"].map(_key)
    df["winner_was_incumbent"] = df["incumbent_side"] == df["winner_sign"]
    # the same race measured against the lean known beforehand (the forecasting target)
    known = pd.concat([district_pres(y, KNOWN).assign(year=y) for y in KNOWN]).rename(columns={"pres_margin": "known_pres"})
    df = df.merge(known, on=["year", "state_po", "district"], how="left")
    k = df[df["known_pres"].notna()].copy()
    k["resid_known"] = k["house_margin"] - k["known_pres"]
    fit_k = smf.ols("resid_known ~ C(year) + incumbent_side", data=k).fit()
    fe_k = {y: fit_k.params["Intercept"] + fit_k.params.get(f"C(year)[T.{y}]", 0.0) for y in KNOWN}
    df["resid_known"] = df["house_margin"] - df["known_pres"] - df["year"].map(fe_k)
    return df


def pairs(df: pd.DataFrame) -> pd.DataFrame:
    """Incumbents running again: this race's edge (toward them) vs. their previous race's edge."""
    out = []
    for _, r in df[df["incumbent_side"] != 0].iterrows():
        prev = df[(df["year"] == r["year"] - 2) & (df["state_po"] == r["state_po"]) & df["winner_key"].isin(r["cand_keys"])]
        if prev.empty:
            continue
        p = prev.iloc[0]
        if (1 if p["winner_side"] == "D" else -1) != r["incumbent_side"]:
            continue  # party switcher
        out.append({"year": r["year"], "state_po": r["state_po"], "district": r["district"],
                    "incumbent": p["winner"], "side": r["incumbent_side"],
                    "edge": r["incumbent_side"] * r["resid_known"],
                    "edge_hindsight": r["incumbent_side"] * (r["resid_raw"] - r["year_effect"]),
                    "prev_edge": p["winner_edge"],
                    "first_term": int(not p["winner_was_incumbent"]),
                    "same_district": int(p["district"] == r["district"])})
    return pd.DataFrame(out).dropna(subset=["edge"])


def fit(pr: pd.DataFrame) -> dict:
    m = smf.ols("edge ~ prev_edge + first_term", data=pr).fit()
    return {"intercept": m.params["Intercept"], "rho": m.params["prev_edge"], "first_term": m.params["first_term"],
            "sd": float(np.sqrt(m.scale)), "n": int(m.nobs), "se_rho": m.bse["prev_edge"]}


def main() -> None:
    df = edges()
    pr = pairs(df)
    df.drop(columns=["cand_keys"]).to_csv(PROC / "house_personal_edges.csv", index=False)
    pr.to_csv(PROC / "house_personal_pairs.csv", index=False)
    f = fit(pr)
    print(f"All years (n={f['n']}): edge = {f['intercept']:.2f} + {f['rho']:.2f} * previous edge "
          f"(se {f['se_rho']:.2f}) + {f['first_term']:.2f} if first re-election; residual sd {f['sd']:.2f}")
    flat = pr["edge"].std()
    print(f"  compare: flat bonus {pr['edge'].mean():.2f} with sd {flat:.2f}")
    for y in sorted(pr["year"].unique()):
        g = fit(pr[pr["year"] != y])
        print(f"  without {y}: intercept {g['intercept']:.2f}, rho {g['rho']:.2f}, first-term {g['first_term']:.2f}, sd {g['sd']:.2f}")
    for y in sorted(pr["year"].unique()):
        s = pr[pr["year"] == y]
        g = fit(s)
        print(f"  {y} alone: n={len(s)}, rho {g['rho']:.2f}, intercept {g['intercept']:.2f}, first-term {g['first_term']:.2f}, "
              f"sd {g['sd']:.2f} (flat sd {s.edge.std():.2f}); same district {s.same_district.mean():.0%}")
    big = pr.reindex(pr["prev_edge"].abs().sort_values(ascending=False).index).head(12)
    print("\nBiggest previous edges:\n", big.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
