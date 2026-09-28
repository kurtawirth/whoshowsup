"""Race-level backtest: run the full 2026 race model on 2010-2024 as of Sept 22.

    .venv/Scripts/python.exe midterms_2026/models/backtest_races.py          # as of Sept 22 (the standard test)
    .venv/Scripts/python.exe midterms_2026/models/backtest_races.py --eve    # as of Election Eve (outlet comparison)

--eve rebuilds the inputs as they stood right before each election: national history as of
Nov 1 (1-7 days before every election since 1976), all polls through the day before, and the
poll-accuracy fit for 1 day out. It writes *_eve.csv outputs and restores the live forecast's
processed files afterwards.

2018-2024 run with every ingredient and are the headline test; 2010-2016 run without campaign
money, candidate experience, ideology and special elections, and with 538's last-~60-day poll
archive, and are scored separately. Governor results come from core/governor_results.py.

For each test year we rebuild exactly what the model would have known on
Sept 22 of that year, then run the SAME simulation engine used for 2026
(race_model.run_simulation):

  national environment  national_env.py fit without the test year (leave-one-out)
  House lean            presidential results on that year's district lines
                        (2016 pres for 2018; 2020 pres on the new 2022 lines)
  incumbency            previous winner found on the ballot by name
  personal vote         Senate / Governor: the incumbent's own previous race (matched by name)
                        House: the incumbent's previous race (core/house_personal_vote.py), fit without the test year
  polls                 538's full-season poll lists (core/poll_archive.py), only polls ending 42+
                        days before the election, weighted and counted as the live model does
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
from house_calibration import house_results, _pres, _key, same_person  # noqa: E402

PROC, RAW, OUT = ROOT / "data" / "processed", ROOT / "data" / "raw", ROOT / "midterms_2026" / "outputs"
# House lean: the latest presidential result on each year's lines (The Downballot / Daily Kos Elections).
# 1l7W130t: 2008 pres on 2006-2010 lines; 1VfkHtzB: 2008/2012/2016 pres on 2016 lines (= 2012 lines
# except FL, NC, VA, redrawn for 2016); 1zLNAuRq: 2016 pres on 2018 lines (PA's court map; NC redrawn 2020).
YEARS = {2010: {"pres_year": 2008, "house_pres": ("1l7W130t_429358610.csv", 3, 4, 2), "election": "2010-11-02",
               "skip_states": set()},
         2012: {"pres_year": 2008, "house_pres": ("1VfkHtzB_0.csv", 7, 8, 2), "election": "2012-11-06",
               "skip_states": {"FL", "NC", "VA", "CA"}},  # CA: no 2008 results computed on its 2012 map
         2014: {"pres_year": 2012, "house_pres": ("1VfkHtzB_0.csv", 5, 6, 2), "election": "2014-11-04",
               "skip_states": {"FL", "NC", "VA"}},
         2016: {"pres_year": 2012, "house_pres": ("1VfkHtzB_0.csv", 5, 6, 2), "election": "2016-11-08",
               "skip_states": set()},
         2018: {"pres_year": 2016, "house_pres": ("1zLNAuRq_0.csv", 3, 4, 2), "election": "2018-11-06",
               "skip_states": set()},
         2020: {"pres_year": 2016, "house_pres": ("1zLNAuRq_0.csv", 3, 4, 2), "election": "2020-11-03",
               "skip_states": {"NC"}},          # redrawn for 2020
         2022: {"pres_year": 2020, "house_pres": ("1CKngqOp_1871835782.csv", 3, 4, 1), "election": "2022-11-08",
               "skip_states": set()},
         2024: {"pres_year": 2020, "house_pres": ("1CKngqOp_1871835782.csv", 3, 4, 1), "election": "2024-11-05",
               "skip_states": {"AL", "GA", "LA", "NY", "NC"}}}  # redrawn between 2022 and 2024


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


# Era-sensitive pieces (the close-seat bonus, the House personal vote) are learned from the recent era
# for tests from 2018 on, as the live model is; older test years learn from all the other years.
RECENT_ERA = 2018

# Years (or states) whose House lines changed from two years earlier: incumbents found by name statewide.
NEW_LINES = {2012: "all", 2016: {"FL", "NC", "VA"}, 2018: {"PA"}, 2022: "all"}


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
    new_lines = NEW_LINES.get(year, set())
    if new_lines != "all":  # same lines as two years earlier: previous winner of this district
        pw = prev.set_index(["state_po", "district"])[["winner", "winner_side"]]
        inc = [pw.loc[(s, d)] if (s, d) in pw.index else None for s, d in zip(cur.state_po, cur.district)]
        cur["inc_side"] = [0 if w is None or not same_person(_key(w["winner"]), keys) else (1 if w["winner_side"] == "D" else -1)
                           for w, keys in zip(inc, cur["cand_keys"])]
        for i, r in cur[cur.state_po.isin(new_lines)].iterrows():  # this state redrew: match by name
            hit = prev[(prev.state_po == r.state_po) & prev.winner.map(lambda w: same_person(_key(w), r.cand_keys))]
            cur.at[i, "inc_side"] = 0 if hit.empty else (1 if hit.iloc[0].winner_side == "D" else -1)
    else:             # new lines: any previous winner from the state on this district's ballot
        cur["inc_side"] = 0
        for i, r in cur.iterrows():
            pw = prev[(prev.state_po == r.state_po)]
            hit = pw[[same_person(_key(w), r.cand_keys) for w in pw.winner]]
            if len(hit):
                cur.at[i, "inc_side"] = 1 if hit.iloc[0].winner_side == "D" else -1
    cur["race_type"] = np.where(cur["contested"], "standard", "same_party")
    cur["race_note"] = np.where(cur["dem"] > 0, "D", "R")
    cur["actual"] = cur["house_margin"]
    return cur.assign(office="HOUSE", special=False)


def statewide_races(year: int) -> pd.DataFrame:
    cal = pd.read_csv(PROC / "statewide_calibration.csv")
    sp = state_pres(YEARS[year]["pres_year"])
    parts = []
    for office, window in (("SEN", 6), ("GOV", 4)):
        cur = cal[(cal.office == office) & (cal.year == year)].copy()
        # personal vote: the incumbent's own previous race for this office (by name) in the prior term
        prior = cal[(cal.office == office) & (cal.year < year) & (cal.year >= year - window)]
        edges = []
        for _, r in cur.iterrows():
            e = np.nan
            if r.incumbent_side != 0:
                k = r.dem_key if r.incumbent_side == 1 else r.rep_key
                hit = prior[(prior.state_po == r.state_po) & ((prior.dem_key == k) | (prior.rep_key == k))]
                if len(hit):
                    # previous race's D-R residual, turned toward the incumbent's party (as in 2026)
                    e = r.incumbent_side * hit.sort_values("year").iloc[-1].resid
            edges.append(e)
        cur["prior_edge"] = edges
        parts.append(cur)
    out = pd.concat(parts, ignore_index=True).merge(sp, on="state_po")
    out = out.rename(columns={"incumbent_side": "inc_side", "margin": "actual"})
    out["district"] = 0
    out["race_type"], out["race_note"] = "standard", ""
    return out


import house_personal_vote as hpv  # noqa: E402
HOUSE_PERSONAL = True  # House incumbents' personal vote (False = the old flat bonus, for comparison)
HOUSE_PAIRS = pd.read_csv(PROC / "house_personal_pairs.csv")
MONEY = True  # campaign money term (core/money_effect.py), leave-one-year-out coefficients
MONEY_OFFICES = ("HOUSE", "SEN")
QUALITY = True  # candidate experience tiers (core/candidate_experience.py); weights are rm.QUALITY_EFFECT
IDEOLOGY = True  # House ideology term (core/candidate_ideology.py), leave-one-year-out weight
UNDECIDED = "--no-undecided" not in sys.argv  # undecided voters (core/undecided_break.py), leave-one-cycle-out
# --und=pull,spread turns on only those pieces (pull toward even, lean by kind of year, spread by share)
PARTS = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--und=")), ["pull", "lean", "spread"])
TAG = "" if not UNDECIDED else ("" if len(PARTS) == 3 else "_und-" + "-".join(PARTS))
# --df=N: each race's own error drawn from Student's t with N degrees of freedom (same spread)
DF = next((int(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--df=")), None)
if DF:
    rm.RACE_ERROR_DF = DF
    TAG += f"_df{DF}"
if "--house" in sys.argv:  # pollster house effects (core/pollster_house_effects.py)
    rm.POLLSTER_HOUSE = True
    TAG += "_house"
if "--house-centered" in sys.argv:  # ... relative to the cycle's poll mix (no net shift)
    rm.POLLSTER_HOUSE, rm.POLLSTER_HOUSE_CENTERED = True, True
    TAG += "_housec"
UNDECIDED_KIND = {2010: "mid_Dpres", 2012: "pres_Dpres", 2014: "mid_Dpres", 2016: "pres_Dpres",
                  2018: "mid_Rpres", 2020: "pres_Rpres", 2022: "mid_Dpres", 2024: "pres_Dpres"}
GOV_QUALITY = rm.QUALITY_EFFECT["GOV"]  # the governor weight is refit leaving each test year out

CUTOFF_DAYS = 42  # polls must end at least this many days before the election (42 ~ Sept 22)


def polls_2024() -> pd.DataFrame:
    """Wikipedia's 2024 race polls (core/polls_2024.py) in the archive's shape."""
    d = pd.read_csv(PROC / "polls_2024_backtest.csv")
    d["time_to_election"] = (pd.Timestamp(YEARS[2024]["election"]) - pd.to_datetime(d.end_date)).dt.days
    d["race_id"] = d.office + d.state_po + d.district.astype(str) + d.special.astype(str)
    return d.rename(columns={"sample_size": "samplesize"}).assign(
        partisan=d.pollster_party.fillna(""), dem_name=d.dem_name.fillna(""))


# Polls as the live model sees them (user decision 2026-09-28): every poll of the season from 538's
# full lists (core/poll_archive.py, 2018-2024), weighted and counted (n_eff) exactly as the live model
# does. --polls=legacy: raw_polls.csv (last ~60 days) + Wikipedia for 2024, with decayed n_eff.
POLLS_538 = NEFF_LIVE = "--polls=legacy" not in sys.argv
ARCHIVE_YEARS = (2018, 2020, 2022, 2024)
if not POLLS_538:
    TAG += "_legacypolls"
# --trust=full: poll-average accuracy (floor, spread) from core/poll_trust.py, fit on full-season
# polls leaving the test year out
TRUST_FULL = "--trust=full" in sys.argv
if TRUST_FULL:
    TAG += "_trustfull"


def set_trust(year: int) -> None:
    if not TRUST_FULL:
        return
    t = pd.read_csv(PROC / "poll_trust.csv")
    t = t[t.left_out.astype(str) == str(year)]
    for r in t.itertuples():
        rm.POLL_FLOOR[r.office], rm.POLL_SPREAD[r.office] = float(r.floor), float(r.spread)


def polls_538(year: int) -> pd.DataFrame:
    d = pd.read_csv(PROC / "poll_archive_538.csv")
    d = d[d.cycle == year].copy()
    d["race_id"] = d.office + d.state_po + d.district.astype(str) + d.special.astype(str)
    d["partisan"] = d.partisan.map({"DEM": "D", "REP": "R"}).fillna("")
    return d.rename(columns={"days": "time_to_election", "sample_size": "samplesize"})


def poll_summary(races: pd.DataFrame, year: int) -> pd.DataFrame:
    if POLLS_538 and year in ARCHIVE_YEARS:
        d = polls_538(year)
        d = d[d.time_to_election >= CUTOFF_DAYS].copy()
    elif year == 2024:  # 538's archive stops at 2022
        d = polls_2024()
        d = d[d.time_to_election >= CUTOFF_DAYS].copy()
    else:
        d = pd.read_csv(RAW / "fte" / "raw_polls.csv", low_memory=False)
        d = d[(d.cycle == year) & (d.electiondate == YEARS[year]["election"]) & (d.time_to_election >= CUTOFF_DAYS)
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
    d["undecided"] = rm.undecided_share(d.dem_pct, d.rep_pct)
    bias = [rm.PARTISAN_BIAS[o].get(p, 0.0) for o, p in zip(d.office, d.partisan)]
    d["adj"] = (d.margin - bias + rm.undecided_shift(d.margin, d.undecided, UNDECIDED_KIND[year],
                                                     typical=rm.typical_share(d.race_id, d.undecided))
                + d.undecided * rm.undecided_composition(d.office, d.state_po, year)
                + rm.pollster_house_adj(d.pollster, f"h_loo_{year}", races=d.race_id))  # track records from other cycles
    age = (d.time_to_election - CUTOFF_DAYS).clip(lower=0)
    n = d.samplesize.fillna(600).clip(200, 3000)
    d["w"] = 0.5 ** (age / rm.POLL_HALF_LIFE_DAYS) * np.sqrt(n / 600) * np.where(d.partisan != "", rm.PARTISAN_WEIGHT, 1.0)
    d["q"] = d["w"]
    if NEFF_LIVE:
        pop = d["population"].fillna("").astype(str).str.lower() if "population" in d else pd.Series("", index=d.index)
        quality = np.sqrt(n / 600) * pop.map(rm.POP_WEIGHT).fillna(0.8) * np.where(d.partisan != "", rm.PARTISAN_WEIGHT, 1.0)
        d["w"] = 0.5 ** (age / rm.POLL_HALF_LIFE_DAYS) * quality
        d["q"] = np.where(age <= rm.POLL_WINDOW_DAYS, 1.0, 0.5 ** ((age - rm.POLL_WINDOW_DAYS) / 30)) * quality
    # Match Senate/Gov polls by the Democrat's name so two same-state Senate races stay separate.
    d["dem_key"] = d.dem_name.map(_key)
    rows = []
    for i, r in races.iterrows():
        x = d[(d.office == r.office) & (d.state_po == r.state_po) & (d.district == int(r.district))]
        if r.office == "SEN" and "dem_key" in r and isinstance(r.dem_key, str):
            x = x[x.dem_key == r.dem_key]
        rows.append({"poll_avg": np.average(x.adj, weights=x.w) if len(x) else np.nan,
                     "poll_n_eff": x.q.sum(), "poll_count": len(x),
                     "poll_undecided": np.average(x.undecided, weights=x.w) if len(x) else np.nan})
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
    if exclude_year >= RECENT_ERA or exclude_year == -1:  # recent tests (and the live model) learn from the recent era
        x = x[x.year >= RECENT_ERA]
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
        races["quality_diff"] = rm.quality_diff(races, year) if QUALITY else 0.0
        if QUALITY and (PROC / "experience_effect.csv").exists():
            ee = pd.read_csv(PROC / "experience_effect.csv")
            ee = ee[(ee["office"] == "GOV") & (ee["form"] == "x_close") & (ee["left_out"].astype(str) == str(year))]
            rm.QUALITY_EFFECT["GOV"] = float(ee["b"].iloc[0]) if len(ee) else GOV_QUALITY  # fit without the test year
        races["prior_edge"] = races.get("prior_edge", np.nan)
        races["first_term"] = 0
        if HOUSE_PERSONAL:
            hp = rm.house_prior_edge(races.assign(incumbent=None), year)
            h = races["office"] == "HOUSE"
            races.loc[h, "prior_edge"], races.loc[h, "first_term"] = hp.loc[h, "prior_edge"], hp.loc[h, "first_term"]
            # leave the test year out; since 2018 only the recent era (2016 on), as the live model is fit,
            # because incumbency has become worth less (core/house_personal_vote.py)
            pr = HOUSE_PAIRS[(HOUSE_PAIRS["year"] != year) & ((HOUSE_PAIRS["year"] >= 2016) | (year <= 2016))]
            f = hpv.fit(pr)
            rm.PERSONAL["HOUSE"] = {k: f[k] for k in ("intercept", "rho", "first_term", "sd")}
        races["money_log_ratio"] = rm.money_ratio(races, year)
        races["ideology_gap"] = rm.ideology_gap(races, year)
        if IDEOLOGY and (PROC / "ideology_effect.csv").exists():
            ie = pd.read_csv(PROC / "ideology_effect.csv")
            ie = ie[ie["left_out"].astype(str) == str(year)]
            rm.IDEOLOGY_EFFECT["HOUSE"] = float(ie["b"].iloc[0]) if len(ie) else 0.0  # fit without the test year
        else:
            rm.IDEOLOGY_EFFECT["HOUSE"] = 0.0
        if MONEY:
            me = pd.read_csv(PROC / "money_effect.csv")
            me = me[me["left_out"].astype(str) == str(year)].set_index("group")["b"]  # fit without the test year
            rm.MONEY_EFFECT.update({g: float(me.get(g, 0.0)) if g in MONEY_OFFICES else 0.0 for g in rm.MONEY_EFFECT})
        else:
            rm.MONEY_EFFECT.update({g: 0.0 for g in rm.MONEY_EFFECT})
        rm.UNDECIDED, rm.UNDECIDED_PARTS = UNDECIDED, set(PARTS)
        if UNDECIDED:
            ub = pd.read_csv(PROC / "undecided_break.csv")
            ub = ub[(ub["form"] == "model") & (ub["left_out"].astype(str) == str(year))]
            if len(ub):  # fitted without the test year (2024 isn't in the archive: all-years fit)
                rm.UNDECIDED_PULL = float(ub["w*m"].iloc[0])
                rm.UNDECIDED_LEAN = {k: float(ub[f"w*{k}"].iloc[0]) for k in rm.UNDECIDED_LEAN}
            uc = pd.read_csv(PROC / "undecided_composition.csv")
            uc = uc[uc["left_out"].astype(str) == str(year)]
            if len(uc):
                rm.UNDECIDED_COMPOSITION.update({k: float(uc[k].iloc[0]) for k in ("hisp", "black")})
        races = poll_summary(races, year)
        set_trust(year)
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


def main(tag: str = "") -> None:
    # Pass 1: no close-seat bonus, to measure the errors. Pass 2: each year gets a bonus
    # estimated only from the OTHER years (leave-one-year-out), so the test stays honest.
    first, _ = run_all(None)
    bonus_for = {y: close_seat_bonus(first, y) for y in YEARS}
    print("Leave-one-year-out close-seat bonus:", {y: round(b, 2) for y, b in bonus_for.items()},
          "| all years:", round(close_seat_bonus(first, -1), 2))
    first_scores = score(first[(first.office == "HOUSE") & (first.year >= RECENT_ERA)], "HOUSE, no bonus")
    res, chambers = run_all(bonus_for)
    res.to_csv(OUT / f"backtest_race_forecasts{tag}.csv", index=False)
    pd.set_option("display.width", 220)
    print("\n=== Chamber totals (Democratic wins among races modeled) ===")
    ch = pd.DataFrame(chambers)
    print(ch.round(1).to_string(index=False))

    # The headline sets are 2018-2024, the years with every ingredient (campaign money, candidate
    # experience and ideology are coded from 2018; special elections read from 2017). 2010-2016 run
    # without them and are scored as their own set.
    print("\n=== Race-level scores (2018-2024; older years scored separately) ===")
    full = res[res.year >= RECENT_ERA]
    scores = [first_scores, score(full, "all")]
    for off in ("HOUSE", "SEN", "GOV"):
        scores.append(score(full[full.office == off], off))
    comp = full[(full.p_dem > 0.05) & (full.p_dem < 0.95)]
    scores.append(score(comp, "competitive (5-95%)"))
    if (res.year < RECENT_ERA).any():
        scores.append(score(res[res.year < RECENT_ERA], "older years (2010-2016)"))
    sc = pd.DataFrame(scores)
    print(sc.round(3).to_string(index=False))

    print("\n=== Calibration: predicted D win probability vs. how often D actually won ===")
    res["bin"] = pd.cut(res.p_dem, [0, .1, .3, .5, .7, .9, 1.0], include_lowest=True)
    cal = res[res.year >= RECENT_ERA].groupby("bin", observed=True).agg(races=("p_dem", "size"), predicted=("p_dem", "mean"),
                                                 actual=("actual", lambda s: (s > 0).mean()))
    print(cal.round(2).to_string())
    sc.to_csv(OUT / f"backtest_scores{tag}.csv", index=False)
    ch.to_csv(OUT / f"backtest_chambers{tag}.csv", index=False)
    cal.to_csv(OUT / f"backtest_calibration{tag}.csv")


def main_eve() -> None:
    """Same backtest, as of Election Eve. Swaps in eve-dated inputs, then restores the live ones."""
    global CUTOFF_DAYS
    import shutil
    import build_national_history
    import poll_average_error
    live = [PROC / "national_history.csv", PROC / "poll_average_error.csv"]
    saved = {f: f.with_suffix(".live_backup") for f in live}
    for f, b in saved.items():
        shutil.copy(f, b)
    try:
        build_national_history.main((11, 1))
        poll_average_error.main(1)
        rm.load_poll_error()
        CUTOFF_DAYS = 1
        main("_eve" + ("" if UNDECIDED else "_nound") + TAG)
    finally:
        for f, b in saved.items():
            shutil.move(b, f)
        rm.load_poll_error()


if __name__ == "__main__":
    main_eve() if "--eve" in sys.argv else main(("" if UNDECIDED else "_nound") + TAG)
