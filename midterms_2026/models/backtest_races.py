"""Race-level backtest: run the full 2026 race model on 2018-2024 as of Sept 22.

Midterms (2018, 2022) are the main test; presidential years (2020, 2024; House
and Senate only -- no governor data) add evidence on systematic biases. No
538 poll archive exists for 2024, so 2024 runs on fundamentals only.

For each test year we rebuild exactly what the model would have known on
Sept 22 of that year, then run the SAME simulation engine used for 2026
(race_model.run_simulation):

  national environment  national_env.py fit without the test year (leave-one-out)
  House lean            presidential results on that year's district lines
                        (2016 pres for 2018; 2020 pres on the new 2022 lines)
  incumbency            previous winner found on the ballot by name
  personal vote         Senate: the incumbent's previous race; Governor 2022: 2018
  polls                 538's archive, only polls taken 42+ days before the election
  candidate quality     not coded for past years -> 0 (a known handicap here)

Scored against actual results:
  - calibration: do races given ~70% go the predicted way ~70% of the time?
  - Brier score (0 = perfect, 0.25 = coin flip) vs. a lean-only baseline
  - share of actual margins inside the 80% ranges (should be ~80%)
  - chamber totals vs. what happened
Excluded: races without a real D-vs-R contest; Pennsylvania House 2018
(court-ordered new map, so 2016 presidential results don't match the lines).
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "midterms_2026" / "models"))
sys.path.insert(0, str(ROOT / "core"))
import race_model as rm  # noqa: E402
import national_env as ne  # noqa: E402
from house_calibration import house_results, _pres, _key  # noqa: E402

PROC, RAW, OUT = ROOT / "data" / "processed", ROOT / "data" / "raw", ROOT / "midterms_2026" / "outputs"
YEARS = {2018: {"pres_year": 2016, "house_pres": ("1VfkHtzB_0.csv", 3, 4, 2), "election": "2018-11-06",
               "skip_states": {"PA"}},          # court-ordered new map in 2018
         2020: {"pres_year": 2016, "house_pres": ("1VfkHtzB_0.csv", 3, 4, 2), "election": "2020-11-03",
               "skip_states": {"PA", "NC"}},    # both redrawn after 2016
         2022: {"pres_year": 2020, "house_pres": ("1CKngqOp_1871835782.csv", 3, 4, 1), "election": "2022-11-08",
               "skip_states": set()},
         2024: {"pres_year": 2020, "house_pres": ("1CKngqOp_1871835782.csv", 3, 4, 1), "election": "2024-11-05",
               "skip_states": {"AL", "GA", "LA", "NY", "NC"}}}  # redrawn between 2022 and 2024
# Governors seeking re-election (hand list; verified against results pages).
GOV_INC = {2018: {"D": ["HI", "NY", "OR", "PA", "RI"],
                  "R": ["AL", "AZ", "AR", "IL", "IA", "MD", "MA", "NE", "NH", "SC", "TX", "VT", "WI"]},
           2022: {"D": ["CA", "CO", "CT", "IL", "KS", "ME", "MI", "MN", "NM", "NY", "OR", "PA", "RI", "WI"],
                  "R": ["AL", "AR", "FL", "GA", "IA", "ID", "NE", "NH", "NV", "OH", "OK", "SC", "SD", "TN", "TX", "VT", "WY"]}}
GOV_NOT_OWN_PRIOR = {2022: {"NY"}}  # Hochul took office mid-term: 2018 was Cuomo's race


def national_draws(year: int) -> np.ndarray:
    df = ne.load()
    reads = ne.fit_reads(df[(df["year"] != year) & df["y"].notna()])
    return ne.predict(reads, df[df["year"] == year].iloc[0], np.random.default_rng(year))["draws"]


def nat_pres_votes(year: int) -> tuple[float, float]:
    p = pd.read_csv(RAW / "medsl" / "president_1976_2024.csv", encoding="latin-1")
    p = p[(p.year == year) & p.party_simplified.isin(["DEMOCRAT", "REPUBLICAN"])]
    return tuple(p.loc[p.party_simplified == x, "candidatevotes"].sum() for x in ("DEMOCRAT", "REPUBLICAN"))


def state_pres(year: int) -> pd.DataFrame:
    p = pd.read_csv(RAW / "medsl" / "president_1976_2024.csv", encoding="latin-1")
    p = p[(p.year == year) & p.party_simplified.isin(["DEMOCRAT", "REPUBLICAN"])]
    st = p.pivot_table(index="state_po", columns="party_simplified", values="candidatevotes", aggfunc="sum")
    return st.rename(columns={"DEMOCRAT": "d24", "REPUBLICAN": "r24"}).reset_index()


def house_races(year: int, cfg: dict) -> pd.DataFrame:
    f, cd_, cr_, skip = cfg["house_pres"]
    raw = pd.read_csv(ROOT / "data" / "raw" / "downballot" / f, header=None, skiprows=skip, dtype=str)
    num = lambda s: pd.to_numeric(s.str.replace(r"[,%]", "", regex=True), errors="coerce")
    pres = pd.DataFrame({"cd": raw[0], "d24": num(raw[cd_]), "r24": num(raw[cr_])})
    pres = pres[pres["cd"].str.match(r"^[A-Z]{2}-(\d{2}|AL)$", na=False)]
    pres["state_po"], pres["district"] = pres["cd"].str[:2], pres["cd"].str[3:].replace("AL", "00").astype(int)
    hr = house_results()
    cur = hr[hr["year"] == year].merge(pres.drop(columns="cd"), on=["state_po", "district"])
    cur = cur[~cur["state_po"].isin(cfg["skip_states"])]
    prev = hr[hr["year"] == year - 2]
    if year != 2022:  # same lines as two years earlier: previous winner of this district
        pw = prev.set_index(["state_po", "district"])[["winner", "winner_side"]]
        inc = [pw.loc[(s, d)] if (s, d) in pw.index else None for s, d in zip(cur.state_po, cur.district)]
        cur["inc_side"] = [0 if w is None or _key(w["winner"]) not in keys else (1 if w["winner_side"] == "D" else -1)
                           for w, keys in zip(inc, cur["cand_keys"])]
    else:             # new lines: any previous winner from the state on this district's ballot
        cur["inc_side"] = 0
        for i, r in cur.iterrows():
            pw = prev[(prev.state_po == r.state_po)]
            hit = pw[[_key(w) in r.cand_keys for w in pw.winner]]
            if len(hit):
                cur.at[i, "inc_side"] = 1 if hit.iloc[0].winner_side == "D" else -1
    cur["race_type"] = np.where(cur["contested"], "standard", "same_party")
    cur["race_note"] = np.where(cur["dem"] > 0, "D", "R")
    cur["actual"] = cur["house_margin"]
    return cur.assign(office="HOUSE", special=False)


def statewide_races(year: int) -> pd.DataFrame:
    cal = pd.read_csv(PROC / "statewide_calibration.csv")
    sp = state_pres(YEARS[year]["pres_year"])
    sen = cal[(cal.office == "SEN") & (cal.year == year)].copy()
    # personal vote: incumbent's previous race edge (any Senate race they won in the prior 6 years)
    prior = cal[(cal.office == "SEN") & (cal.year < year) & (cal.year >= year - 6)]
    edges = []
    for _, r in sen.iterrows():
        e = np.nan
        if r.incumbent_side != 0:
            k = r.dem_key if r.incumbent_side == 1 else r.rep_key
            hit = prior[(prior.state_po == r.state_po) & ((prior.dem_key == k) | (prior.rep_key == k))]
            if len(hit):
                # previous race's D-R residual, turned toward the incumbent's party (as in 2026)
                e = r.incumbent_side * hit.sort_values("year").iloc[-1].resid
        edges.append(e)
    sen["prior_edge"] = edges
    gov = cal[(cal.office == "GOV") & (cal.year == year)].copy()
    gov["incumbent_side"] = 0
    for side, states in GOV_INC.get(year, {}).items():
        gov.loc[gov.state_po.isin(states), "incumbent_side"] = 1 if side == "D" else -1
    prev_gov = cal[(cal.office == "GOV") & (cal.year == year - 4)].set_index("state_po")["resid"]
    gov["prior_edge"] = [s_ * prev_gov[st] if s_ != 0 and st in prev_gov.index and st not in GOV_NOT_OWN_PRIOR.get(year, set())
                         else np.nan for st, s_ in zip(gov.state_po, gov.incumbent_side)]
    out = pd.concat([sen, gov], ignore_index=True).merge(sp, on="state_po")
    out = out.rename(columns={"incumbent_side": "inc_side", "margin": "actual"})
    out["district"] = 0
    out["race_type"], out["race_note"] = "standard", ""
    return out


def poll_summary(races: pd.DataFrame, year: int) -> pd.DataFrame:
    d = pd.read_csv(RAW / "fte" / "raw_polls.csv", low_memory=False)
    d = d[(d.cycle == year) & (d.electiondate == YEARS[year]["election"]) & (d.time_to_election >= 42)
          & d.type_simple.isin(["Sen-G", "Gov-G", "House-G"])]
    d = d[d.cand1_party.isin(["DEM", "REP"]) & d.cand2_party.isin(["DEM", "REP"]) & (d.cand1_party != d.cand2_party)]
    dem_first = d.cand1_party == "DEM"
    d["dem_pct"] = np.where(dem_first, d.cand1_pct, d.cand2_pct)
    d["rep_pct"] = np.where(dem_first, d.cand2_pct, d.cand1_pct)
    d["dem_name"] = np.where(dem_first, d.cand1_name, d.cand2_name)
    d["office"] = d.type_simple.map({"Sen-G": "SEN", "Gov-G": "GOV", "House-G": "HOUSE"})
    d["state_po"] = d.location.str[:2]
    d["district"] = np.where(d.office == "HOUSE", d.location.str.split("-").str[-1], "0")
    d["district"] = pd.to_numeric(d["district"], errors="coerce").fillna(0).astype(int)
    d["partisan"] = d.partisan.map({"DEM": "D", "REP": "R"}).fillna("")
    d["margin"] = rm.two_party(d.dem_pct, d.rep_pct)
    bias = [rm.PARTISAN_BIAS[o].get(p, 0.0) for o, p in zip(d.office, d.partisan)]
    d["adj"] = d.margin - bias
    age = (d.time_to_election - 42).clip(lower=0)
    n = d.samplesize.fillna(600).clip(200, 3000)
    d["w"] = 0.5 ** (age / rm.POLL_HALF_LIFE_DAYS) * np.sqrt(n / 600) * np.where(d.partisan != "", rm.PARTISAN_WEIGHT, 1.0)
    # Match Senate/Gov polls by the Democrat's name so two same-state Senate races stay separate.
    d["dem_key"] = d.dem_name.map(_key)
    rows = []
    for i, r in races.iterrows():
        x = d[(d.office == r.office) & (d.state_po == r.state_po) & (d.district == int(r.district))]
        if r.office == "SEN" and "dem_key" in r and isinstance(r.dem_key, str):
            x = x[x.dem_key == r.dem_key]
        rows.append({"poll_avg": np.average(x.adj, weights=x.w) if len(x) else np.nan,
                     "poll_n_eff": x.w.sum(), "poll_count": len(x)})
    return pd.concat([races.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def score(df: pd.DataFrame, label: str) -> dict:
    y = (df["actual"] > 0).astype(float)
    brier = np.mean((df["p_dem"] - y) ** 2)
    base_p = 1 / (1 + np.exp(-df["lean_only"] / 6))  # lean-only baseline, squashed to a probability
    return {"set": label, "races": len(df), "brier": brier, "brier_lean_only": np.mean((base_p - y) ** 2),
            "correct_calls": np.mean((df["p_dem"] > 0.5) == (y == 1)),
            "inside_80": np.mean((df["actual"] >= df["margin_p10"]) & (df["actual"] <= df["margin_p90"])),
            "mae_margin": np.mean(np.abs(df["margin_median"] - df["actual"]))}


def close_seat_bonus(errors: pd.DataFrame, exclude_year: int) -> float:
    """Estimate the close-seat bonus from OTHER years' no-bonus backtest errors:
    regress env-adjusted House errors on the bump shape (least squares, no intercept)."""
    x = errors[(errors.office == "HOUSE") & (errors.year != exclude_year)]
    bump = np.exp(-(x["lean"] / rm.CLOSE_SEAT_WIDTH) ** 2)
    err = x["actual"] - x["margin_median"] - x["env_miss"]
    return float((bump * err).sum() / (bump ** 2).sum())


def run_all(bonus_for: dict | None = None) -> tuple[pd.DataFrame, list]:
    all_rows, chambers = [], []
    for year, cfg in YEARS.items():
        env = national_draws(year)
        D0, R0 = nat_pres_votes(cfg["pres_year"])
        races = pd.concat([house_races(year, cfg), statewide_races(year)], ignore_index=True)
        races["pres24"] = rm.two_party(races["d24"], races["r24"])
        races["quality_diff"] = 0.0
        races["prior_edge"] = races.get("prior_edge", np.nan)
        races = poll_summary(races, year)
        bonus = 0.0 if bonus_for is None else bonus_for[year]
        live, fixed_r, margin, E, a = rm.run_simulation(races, env, D0, R0, np.random.default_rng(year),
                                                        close_bonus=bonus)
        nat_pres = rm.two_party(D0, R0)
        live["lean"] = live["pres24"] - nat_pres
        live["env_miss"] = ne.load().set_index("year").loc[year, "house_margin"] - np.median(env)
        live["close_bonus_used"] = bonus
        live["lean_only"] = live["pres24"] + (np.median(env) - nat_pres)
        live["year"] = year
        all_rows.append(live)
        win = margin > 0
        for off in ("HOUSE", "SEN", "GOV"):
            m = (live["office"] == off).to_numpy()
            fixed_d = int(((fixed_r["office"] == off) & (fixed_r["race_note"] == "D")).sum())
            sims = win[m].sum(axis=0) + fixed_d
            actual = int((live.loc[m, "actual"] > 0).sum()) + fixed_d
            chambers.append({"year": year, "office": off, "races": int(m.sum()) + int((fixed_r.office == off).sum()),
                             "pred_median_D": np.median(sims), "p10": np.percentile(sims, 10),
                             "p90": np.percentile(sims, 90), "actual_D": actual,
                             "inside_80": np.percentile(sims, 10) <= actual <= np.percentile(sims, 90)})
        print(f"{year}: national env D{np.median(env):+.1f} (actual House vote "
              f"D{ne.load().set_index('year').loc[year, 'house_margin']:+.1f}), close-seat bonus {bonus:.2f}")
    return pd.concat(all_rows, ignore_index=True), chambers


def main() -> None:
    # Pass 1: no close-seat bonus, to measure the errors. Pass 2: each year gets a bonus
    # estimated only from the OTHER years (leave-one-year-out), so the test stays honest.
    first, _ = run_all(None)
    bonus_for = {y: close_seat_bonus(first, y) for y in YEARS}
    print("Leave-one-year-out close-seat bonus:", {y: round(b, 2) for y, b in bonus_for.items()},
          "| all years:", round(close_seat_bonus(first, -1), 2))
    first_scores = score(first[first.office == "HOUSE"], "HOUSE, no bonus")
    res, chambers = run_all(bonus_for)
    res.to_csv(OUT / "backtest_race_forecasts.csv", index=False)
    pd.set_option("display.width", 220)
    print("\n=== Chamber totals (Democratic wins among races modeled) ===")
    ch = pd.DataFrame(chambers)
    print(ch.round(1).to_string(index=False))

    print("\n=== Race-level scores ===")
    scores = [first_scores, score(res, "all")]
    for off in ("HOUSE", "SEN", "GOV"):
        scores.append(score(res[res.office == off], off))
    comp = res[(res.p_dem > 0.05) & (res.p_dem < 0.95)]
    scores.append(score(comp, "competitive (5-95%)"))
    sc = pd.DataFrame(scores)
    print(sc.round(3).to_string(index=False))

    print("\n=== Calibration: predicted D win probability vs. how often D actually won ===")
    res["bin"] = pd.cut(res.p_dem, [0, .1, .3, .5, .7, .9, 1.0], include_lowest=True)
    cal = res.groupby("bin", observed=True).agg(races=("p_dem", "size"), predicted=("p_dem", "mean"),
                                                 actual=("actual", lambda s: (s > 0).mean()))
    print(cal.round(2).to_string())
    sc.to_csv(OUT / "backtest_scores.csv", index=False)
    ch.to_csv(OUT / "backtest_chambers.csv", index=False)
    cal.to_csv(OUT / "backtest_calibration.csv")


if __name__ == "__main__":
    main()
