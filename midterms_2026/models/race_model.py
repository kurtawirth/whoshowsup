"""2026 race model + simulation: House, Senate, Governor.

For every simulated election s (N_SIMS of them):

  1. National environment E_s  ~ draws from national_env.py (national House
     two-party margin, D-R).
  2. Turnout-vs-persuasion share a_s ~ Beta(mean 0.65): how much of the
     national swing moves each party's VOTE COUNTS proportionally (turnout-
     shaped) versus shifting every margin equally (persuasion-shaped).
     0.65 = average best share across 8 past elections (core/test_turnout_layer.py).
  3. Fundamentals for race i:
        F_i = a_s * shaped_i(E_s) + (1 - a_s) * swing_i(E_s)
              + incumbency + candidate quality (+ independent adjustment)
     shaped_i: scale the 2024 Harris/Trump vote counts so the nation lands on E_s
     swing_i : 2024 presidential margin + (E_s - 2024 national presidential margin)
  4. Polls: a recency- and quality-weighted two-party average P_i, with
     partisan polls corrected and half-weighted. Its historical error
     sqrt(floor^2 + spread^2 / n_eff) (core/poll_average_error.py) sets how
     much it moves the race off its fundamentals (Bayesian precision weighting).
     Polls describe today's environment, so they shift with E_s - mean(E).
  5. Error: a shared state shock (all races in a state), a shared regional
     shock, and race-specific noise, together matching each race's
     calibrated uncertainty.

Outputs (midterms_2026/outputs/):
  race_forecasts.csv      every race: win probability, median margin, 80% range
  chamber_summary.csv     House seats, Senate control, governorships
  simulations_*.npz       raw draws for the dashboard
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "midterms_2026" / "outputs"

N_SIMS = 20000
SEED = 2026
FORECAST_DATE = pd.Timestamp.today().normalize()  # the pipeline passes an explicit date

# ---- calibrated constants (see the core/*_calibration.py scripts) ----
INCUMBENCY = {"HOUSE": 2.3, "SEN": 5.4, "GOV": 4.5}
# Personal vote: an incumbent's previous over/under-performance vs lean + environment
# partly persists. expected edge = intercept + rho * previous edge; the remaining noise
# is smaller than for a generic race. Estimated from re-running incumbents
# (Senate 2012-2024, n=159; Governor 2018->2022, n=26).
PERSONAL = {"SEN": {"intercept": 3.0, "rho": 0.43, "sd": 9.1},
            "GOV": {"intercept": 5.1, "rho": 0.63, "sd": 8.2},
            # House (core/house_personal_vote.py, 1,269 re-running incumbents 2016-2024): the
            # previous race's edge over lean + year, plus a bump for a member's first re-election.
            # Used only when the previous race is found; otherwise the flat INCUMBENCY bonus.
            "HOUSE": {"intercept": -0.13, "rho": 0.53, "first_term": 3.63, "sd": 5.78}}
# The House personal vote moves each incumbent's expected margin but keeps FUND_SD["HOUSE_inc"]:
# also shrinking that spread (by 5.78/7.32, the fit's residual vs. flat-bonus sd) hurt the
# backtest's Brier score and calls at both Sept 22 and Election Eve, because it weakened the
# polls' pull in close races.
# Governors whose previous race was not their own (first elected 2024, or took office mid-term).
GOV_NO_PRIOR = {"NH", "SD"}
FUND_SD = {"HOUSE_inc": 6.0, "HOUSE_open": 7.0, "SEN": 11.0, "GOV": 8.5}
# Poll-average accuracy depends on how far out we are; core/poll_average_error.py writes
# the values for the current forecast date. These defaults are the Sept 22 (42 days) fit.
POLL_FLOOR = {"HOUSE": 9.0, "SEN": 6.0, "GOV": 6.1}
POLL_SPREAD = {"HOUSE": 1.2, "SEN": 6.5, "GOV": 6.2}
ELECTION_DAY = pd.Timestamp("2026-11-03")


def load_poll_error() -> None:
    """Replace the default poll-accuracy constants with the latest fitted values."""
    path = PROC / "poll_average_error.csv"
    if path.exists():
        e = pd.read_csv(path).set_index("office")
        for ours, theirs in [("HOUSE", "House-G"), ("SEN", "Sen-G"), ("GOV", "Gov-G")]:
            POLL_FLOOR[ours], POLL_SPREAD[ours] = float(e.loc[theirs, "floor"]), float(e.loc[theirs, "spread"])
PARTISAN_BIAS = {"HOUSE": {"D": 5.4, "R": -5.6}, "SEN": {"D": 3.4, "R": -3.9}, "GOV": {"D": 4.1, "R": -3.5}}
PARTISAN_WEIGHT = 0.5                  # user decision: corrected partisan polls count half
POLL_WINDOW_DAYS = 100  # polls in this window count fully toward the average's reliability
POLL_HALF_LIFE_DAYS = 14  # best or tied at 42, 21, 14, 7 days out in 538 archive tests (vs 3-60 days, equal)
POP_WEIGHT = {"lv": 1.0, "rv": 0.8, "v": 0.9, "a": 0.6}
# Candidate experience: points of margin per tier of prior-office gap (D tier - R tier; tiers from
# core/candidate_experience.py), by office. QUALITY_FADE[office] = w counts it only near a toss-up,
# fading as exp(-(fundamentals / w)^2); no entry = counts everywhere. Settled by backtest
# (core/experience_effect.py): House and Senate none -- the gap never improved margins (the old
# guess of 1/tier for the Senate raised Brier only by making lopsided races more lopsided, while
# Senate margin error rose 5.5 -> 6.1); Governor ~2.7/tier near a toss-up (2.4-3.0 leaving a year out).
QUALITY_EFFECT = {"HOUSE": 0.0, "SEN": 0.0, "GOV": 2.7}
QUALITY_FADE = {"GOV": 12.0}
# Candidate ideology (core/candidate_ideology.py, DIME CFscores from earlier cycles): points per
# unit of ideology_gap = extremity(R) - extremity(D), near a toss-up only (fade width 12).
# House 3.64 (2.7-4.3 leaving a year out); backtest Brier 0.0306 -> 0.0301 (Sept 22), 0.0317 -> 0.0312
# (eve). Senate: no reliable effect.
IDEOLOGY_EFFECT = {"HOUSE": 3.64, "SEN": 0.0}
IDEOLOGY_FADE = 12.0
# Campaign money (core/fec_money.py, core/money_effect.py): points of margin per unit of
# clip(ln((D money + 25k) / (R money + 25k)), -3, 3) * exp(-(fundamentals / 12)^2), money as of
# the latest FEC report by the forecast date. It only counts near a toss-up. House and Senate
# only (governors aren't in FEC data). All-years fit from core/money_effect.py (leave-one-year-out:
# House 1.5-1.8, Senate 2.9-5.5). Backtest: Brier 0.0318 -> 0.0309 (Sept 22), 0.0332 -> 0.0320 (eve).
MONEY_EFFECT = {"HOUSE": 1.68, "SEN": 4.61}
MONEY_CLIP, MONEY_WIDTH = 3.0, 12.0
TURNOUT_SHARE_MEAN, TURNOUT_SHARE_CONC = 0.65, 6.0
# Close-seat effect: in all four backtest cycles (2018-2024) Democrats ran ~1.5 pts ahead of
# lean + national environment in competitive House districts (not explained by lean
# compression). Applied as a bump that fades with distance from an even district:
# bonus * exp(-(lean / width)^2). Estimated by midterms_2026/models/backtest_races.py.
CLOSE_SEAT_BONUS, CLOSE_SEAT_WIDTH = 1.5, 10.0  # all-years estimate 1.50; leave-one-out 0.8-2.2 (2.4 before the money term, 3.0 before the House personal vote)
STATE_SHOCK_SD, REGION_SHOCK_SD = 2.0, 2.0
# Osborn ran ~15 pts ahead of a generic Democrat's expected margin in NE in 2024;
# shrink toward zero and widen, since independents' appeal is volatile.
INDEPENDENT_ADJ = {("SEN", "NE", 0): (10.0, 6.0), ("HOUSE", "CA", 6): (0.0, 4.0)}
REGION = {**dict.fromkeys(["CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"], "NE"),
          **dict.fromkeys(["IL", "IN", "MI", "OH", "WI", "IA", "KS", "MN", "MO", "NE", "ND", "SD"], "MW"),
          **dict.fromkeys(["DE", "FL", "GA", "MD", "NC", "SC", "VA", "DC", "WV", "AL", "KY", "MS", "TN",
                           "AR", "LA", "OK", "TX"], "S"),
          **dict.fromkeys(["AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY", "AK", "CA", "HI", "OR", "WA"], "W")}


def race_id(r) -> str:
    """Stable URL-friendly id: house-tx-28, senate-oh-special, governor-ga."""
    office = {"HOUSE": "house", "SEN": "senate", "GOV": "governor"}[r["office"]]
    if r["office"] == "HOUSE":
        return f"house-{r['state_po'].lower()}-{'al' if int(r['district']) == 0 else int(r['district'])}"
    return f"{office}-{r['state_po'].lower()}" + ("-special" if bool(r["special"]) else "")


def two_party(d, r):
    return 100 * (d - r) / (d + r)


def load_races() -> pd.DataFrame:
    h = pd.read_csv(PROC / "races_2026_house.csv").assign(office="HOUSE", special=False)
    h = h.rename(columns={"harris24": "d24", "trump24": "r24"})
    p = pd.read_csv(RAW / "medsl" / "president_1976_2024.csv", encoding="latin-1")
    p = p[(p.year == 2024) & p.party_simplified.isin(["DEMOCRAT", "REPUBLICAN"])]
    st = p.pivot_table(index="state_po", columns="party_simplified", values="candidatevotes", aggfunc="sum")
    st = st.rename(columns={"DEMOCRAT": "d24", "REPUBLICAN": "r24"}).reset_index()
    parts = [h]
    for office, f in [("SEN", "senate"), ("GOV", "governor")]:
        r = pd.read_csv(PROC / f"races_2026_{f}.csv").assign(office=office, district=0)
        parts.append(r.drop(columns=["pres24_margin", "pres20_margin"], errors="ignore").merge(st, on="state_po"))
    races = pd.concat(parts, ignore_index=True)
    races["district"] = races["district"].fillna(0).astype(int)
    races["special"] = races["special"].fillna(False).astype(bool)
    races["pres24"] = two_party(races["d24"], races["r24"])
    return races


def incumbency_side(r) -> int:
    if r["race_type"] == "independent" or not bool(r.get("incumbent_running", False)):
        return 0
    return 1 if r["incumbent_party"] == "D" else -1 if r["incumbent_party"] == "R" else 0


def quality_diff(races: pd.DataFrame, year: int = 2026) -> pd.Series:
    """D tier - R tier from core/candidate_experience.py (0 where either is unknown)."""
    q = pd.read_csv(PROC / "candidate_experience.csv")
    q = q[q["year"] == year].rename(columns={"name": "candidate"})
    q["side"] = q["side"].map({"D": "dem", "R": "rep"})
    key_cols = ["office", "state_po", "district", "special"]
    q = q.groupby(key_cols + ["side"])["tier"].max().unstack("side")
    idx = pd.MultiIndex.from_arrays([races["office"], races["state_po"], races["district"].astype(int),
                                     races["special"].astype(bool)])
    diff = q["dem"].reindex(idx).to_numpy() - q["rep"].reindex(idx).to_numpy()
    return pd.Series(diff, index=races.index).fillna(0)


def house_prior_edge(races: pd.DataFrame, year: int = 2026) -> pd.DataFrame:
    """Each House incumbent's edge in their previous race (toward them, points) and whether that
    was their first win (so this is their first re-election). Found by name within the state."""
    import sys
    sys.path.insert(0, str(ROOT / "core"))
    from house_calibration import _key
    e = pd.read_csv(PROC / "house_personal_edges.csv")
    e = e[e["year"] == year - 2]
    out = pd.DataFrame({"prior_edge": np.nan, "first_term": 0}, index=races.index)
    for i, r in races.iterrows():
        if r["office"] != "HOUSE" or r["inc_side"] == 0:
            continue
        name = r["incumbent"] if "incumbent" in r and isinstance(r["incumbent"], str) else None
        keys = [_key(name)] if name else list(r.get("cand_keys", []))
        hit = e[(e["state_po"] == r["state_po"]) & e["winner_key"].isin(keys)
                & (np.where(e["winner_side"] == "D", 1, -1) == r["inc_side"])]
        if len(hit):
            out.at[i, "prior_edge"] = hit.iloc[0]["winner_edge"]
            out.at[i, "first_term"] = int(not hit.iloc[0]["winner_was_incumbent"])
    return out


def prior_edge(races: pd.DataFrame) -> pd.Series:
    """Each incumbent's edge in their previous race (toward them, points)."""
    cal = pd.read_csv(PROC / "statewide_calibration.csv")
    out = pd.Series(np.nan, index=races.index)
    house = house_prior_edge(races)
    out[house.index] = house["prior_edge"]
    races["first_term"] = house["first_term"]
    for i, r in races.iterrows():
        if r["office"] not in ("SEN", "GOV") or r["inc_side"] == 0:
            continue
        side = r["inc_side"]
        if r["office"] == "SEN":
            ln = str(r["incumbent"]).split()[-1].upper()
            prev = cal[(cal.office == "SEN") & (cal.state_po == r["state_po"]) & (cal.year >= 2018)]
            prev = prev[prev["winner"].astype(str).str.upper().str.contains(ln, regex=False)]
        else:
            if r["state_po"] in GOV_NO_PRIOR:
                continue
            prev = cal[(cal.office == "GOV") & (cal.state_po == r["state_po"])]
        if len(prev):
            out[i] = side * prev.sort_values("year").iloc[-1]["resid"]
    return out


def money_ratio(races: pd.DataFrame, year: int = 2026) -> pd.Series:
    """ln((D money + 25k) / (R money + 25k)) for each House/Senate race; NaN where unknown."""
    path = PROC / "fec_money.csv"
    if not path.exists():
        return pd.Series(np.nan, index=races.index)
    m = pd.read_csv(path)
    m = m[m["year"] == year].set_index(["office", "state_po", "district", "special"])["money_log_ratio"]
    idx = pd.MultiIndex.from_arrays([races["office"], races["state_po"], races["district"].astype(int),
                                     races["special"].astype(bool)])
    return pd.Series(m.reindex(idx).to_numpy(), index=races.index)


def ideology_gap(races: pd.DataFrame, year: int = 2026) -> pd.Series:
    """extremity(R) - extremity(D) from core/candidate_ideology.py; 0 where unknown."""
    path = PROC / "candidate_ideology.csv"
    if not path.exists():
        return pd.Series(0.0, index=races.index)
    g = pd.read_csv(path)
    g = g[g["year"] == year].set_index(["office", "state_po", "district", "special"])["ideology_gap"]
    idx = pd.MultiIndex.from_arrays([races["office"], races["state_po"], races["district"].astype(int),
                                     races["special"].astype(bool)])
    return pd.Series(g.reindex(idx).to_numpy(), index=races.index).fillna(0.0)


def poll_summary(races: pd.DataFrame, forecast_date: pd.Timestamp = FORECAST_DATE) -> pd.DataFrame:
    polls = pd.read_csv(PROC / "polls_2026_races.csv", parse_dates=["end_date"])
    polls = polls[polls["end_date"] <= forecast_date]
    # Multi-candidate primary polls (e.g. California's all-party primary) can list both
    # nominees; if the pair holds under 60% it was not a head-to-head general poll.
    polls = polls[(polls["dem_pct"] + polls["rep_pct"]) >= 60]
    # (Alaska's bloc races: the poll builders add up each side's candidates -- three Republicans
    # splitting a first-round poll count together -- so those polls read as bloc vs bloc.)
    polls["partisan"] = polls["partisan"].fillna("")
    polls["margin"] = two_party(polls["dem_pct"], polls["rep_pct"])
    bias = polls.apply(lambda p: PARTISAN_BIAS[p["office"]].get(p["partisan"], 0.0), axis=1)
    polls["adj"] = polls["margin"] - bias
    age = (forecast_date - polls["end_date"]).dt.days.clip(lower=0)
    n = polls["sample_size"].fillna(600).clip(200, 3000)
    quality = (np.sqrt(n / 600)
               * polls["population"].fillna("").map(POP_WEIGHT).fillna(0.8)
               * np.where(polls["partisan"] != "", PARTISAN_WEIGHT, 1.0))
    # Two different jobs, two different weights:
    #  - w: how much each poll counts WITHIN the average (fresh polls win; 14-day half-life)
    #  - n_eff: how much the average as a whole is worth vs. the fundamentals. The poll-error
    #    calibration counted every poll in a ~2-3 month window equally, so we do the same here
    #    (polls older than 100 days fade out). Otherwise a race whose only polls are two months
    #    old would treat them as worthless -- Vermont's governor race did exactly that.
    polls["w"] = 0.5 ** (age / POLL_HALF_LIFE_DAYS) * quality
    polls["q"] = np.where(age <= POLL_WINDOW_DAYS, 1.0, 0.5 ** ((age - POLL_WINDOW_DAYS) / 30)) * quality
    g = polls.groupby(["office", "state_po", "district", "special"])
    summ = pd.DataFrame({
        "poll_avg": g.apply(lambda x: np.average(x["adj"], weights=x["w"]), include_groups=False),
        "poll_n_eff": g["q"].sum(), "poll_count": g.size(),
        "poll_last": g["end_date"].max(),
    }).reset_index()
    return races.merge(summ, on=["office", "state_po", "district", "special"], how="left")


def run_simulation(races: pd.DataFrame, env: np.ndarray, nat_d0: float, nat_r0: float,
                   rng: np.random.Generator, n_sims: int = N_SIMS, close_bonus: float = CLOSE_SEAT_BONUS):
    """The model itself, shared by the 2026 forecast and the backtests.

    `races` needs: office, state_po, district, race_type, race_note, d24/r24 (the
    baseline presidential vote -- counts or percentages; only their ratio matters),
    pres24 (baseline two-party margin), inc_side, quality_diff, prior_edge,
    poll_avg, poll_n_eff. `env` = draws of the national House margin;
    nat_d0/nat_r0 = the baseline presidential election's national D/R votes.
    Returns (live races with forecasts, fixed races, margin draws, E, a)."""
    fixed = races["race_type"] == "same_party"
    E = rng.choice(env, n_sims)
    E_bar = env.mean()
    a = rng.beta(TURNOUT_SHARE_MEAN * TURNOUT_SHARE_CONC, (1 - TURNOUT_SHARE_MEAN) * TURNOUT_SHARE_CONC, n_sims)

    nat_pres = two_party(nat_d0, nat_r0)
    s = (E / 100 + 1) / 2
    ratio = s / (1 - s) * nat_r0 / nat_d0                  # multiply D votes by this to hit E nationally

    live = races[~fixed].reset_index(drop=True)
    d24, r24, pres24 = (live[c].to_numpy(dtype=float)[:, None] for c in ("d24", "r24", "pres24"))
    shaped = two_party(d24 * ratio[None, :], r24)
    swing = pres24 + (E - nat_pres)[None, :]
    base = a[None, :] * shaped + (1 - a[None, :]) * swing

    office = live["office"].to_numpy()
    inc = live["inc_side"].to_numpy() * np.vectorize(INCUMBENCY.get)(office)
    edge = live["prior_edge"].to_numpy(dtype=float)
    adj = np.zeros(len(live))
    lean = live["pres24"].to_numpy(dtype=float) - nat_pres
    adj += np.where(office == "HOUSE", close_bonus * np.exp(-(lean / CLOSE_SEAT_WIDTH) ** 2), 0.0)
    fund_sd = np.where(office == "HOUSE", np.where(live["inc_side"] != 0, FUND_SD["HOUSE_inc"], FUND_SD["HOUSE_open"]),
                       np.vectorize(FUND_SD.get)(np.where(office == "HOUSE", "SEN", office)))
    for i, r in live.iterrows():
        k = (r["office"], r["state_po"], int(r["district"]) if r["office"] == "HOUSE" else 0)
        if k in INDEPENDENT_ADJ and r["race_type"] == "independent":
            shift, extra = INDEPENDENT_ADJ[k]
            adj[i] += shift
            fund_sd[i] = np.hypot(fund_sd[i], extra)
    # Incumbents: replace the flat incumbency bonus with the personal vote.
    first = live["first_term"].fillna(0).to_numpy(dtype=float) if "first_term" in live else np.zeros(len(live))
    for i in range(len(live)):
        o = office[i]
        if o in PERSONAL and live.loc[i, "inc_side"] != 0:
            if o == "HOUSE" and np.isnan(edge[i]):
                continue  # previous race not found (e.g. was unopposed): keep the flat bonus
            p_ = PERSONAL[o]
            prev = 0.0 if np.isnan(edge[i]) else edge[i]
            inc[i] = live.loc[i, "inc_side"] * (p_["intercept"] + p_["rho"] * prev + p_.get("first_term", 0.0) * first[i])
            if not np.isnan(edge[i]):
                fund_sd[i] = fund_sd[i] if o == "HOUSE" else p_["sd"]
    # Campaign money: counts near a toss-up (judged by the fundamentals without it), fades in safe seats.
    money_adj = np.zeros(len(live))
    center = base.mean(axis=1) + inc + adj
    # Candidate experience (see QUALITY_EFFECT)
    q = live["quality_diff"].fillna(0).to_numpy(dtype=float) * np.array([QUALITY_EFFECT.get(o, 0.0) for o in office])
    fade = np.array([(QUALITY_FADE or {}).get(o) or 0.0 for o in office]) if isinstance(QUALITY_FADE, dict)         else np.full(len(live), QUALITY_FADE or 0.0)
    quality_adj = q * np.where(fade > 0, np.exp(-(center / np.where(fade > 0, fade, 1.0)) ** 2), 1.0)
    adj = adj + quality_adj
    ideology_adj = np.zeros(len(live))
    if "ideology_gap" in live:
        coef = np.array([IDEOLOGY_EFFECT.get(o, 0.0) for o in office])
        ideology_adj = coef * live["ideology_gap"].fillna(0).to_numpy(dtype=float) * np.exp(-(center / IDEOLOGY_FADE) ** 2)
        adj = adj + ideology_adj
    if "money_log_ratio" in live:
        ratio = np.clip(live["money_log_ratio"].fillna(0).to_numpy(dtype=float), -MONEY_CLIP, MONEY_CLIP)
        coef = np.array([MONEY_EFFECT.get(o, 0.0) for o in office])
        money_adj = coef * ratio * np.exp(-(center / MONEY_WIDTH) ** 2)
    fund = base + (inc + adj + money_adj)[:, None]

    # ---- polls: Bayesian precision weighting against the fundamentals ----
    has_poll = live["poll_avg"].notna().to_numpy()
    n_eff = live["poll_n_eff"].fillna(0).to_numpy(dtype=float)
    floor = np.vectorize(POLL_FLOOR.get)(office)
    spread = np.vectorize(POLL_SPREAD.get)(office)
    env_sd = env.std()
    poll_sd = np.sqrt(np.maximum(floor ** 2 - env_sd ** 2, 1.0) + spread ** 2 / np.maximum(n_eff, 1e-9))
    w_poll = np.where(has_poll, fund_sd ** 2 / (fund_sd ** 2 + poll_sd ** 2), 0.0)
    poll_now = live["poll_avg"].fillna(0).to_numpy(dtype=float)[:, None] + (E - E_bar)[None, :]
    mean = w_poll[:, None] * poll_now + (1 - w_poll[:, None]) * fund
    post_sd = np.where(has_poll, np.sqrt(fund_sd ** 2 * poll_sd ** 2 / (fund_sd ** 2 + poll_sd ** 2)), fund_sd)

    # ---- correlated error: state + region + race ----
    states = sorted(races["state_po"].unique())
    regions = sorted(set(REGION.values()))
    st_shock = rng.normal(0, STATE_SHOCK_SD, (len(states), n_sims))
    rg_shock = rng.normal(0, REGION_SHOCK_SD, (len(regions), n_sims))
    si = live["state_po"].map({s_: i for i, s_ in enumerate(states)}).to_numpy()
    ri = live["state_po"].map(lambda s_: regions.index(REGION[s_])).to_numpy()
    own_sd = np.sqrt(np.maximum(post_sd ** 2 - STATE_SHOCK_SD ** 2 - REGION_SHOCK_SD ** 2, 2.0 ** 2))
    margin = mean + st_shock[si] + rg_shock[ri] + rng.normal(0, 1, mean.shape) * own_sd[:, None]

    live["p_dem"] = (margin > 0).mean(axis=1)
    live["margin_median"] = np.median(margin, axis=1)
    live["margin_p10"], live["margin_p90"] = np.percentile(margin, [10, 90], axis=1)
    live["fundamentals_mean"] = fund.mean(axis=1)
    live["money_adj"] = money_adj
    live["quality_adj"] = quality_adj
    live["ideology_adj"] = ideology_adj
    live["poll_weight"] = w_poll
    fixed_r = races[fixed].copy()
    fixed_r["p_dem"] = (fixed_r["race_note"] == "D").astype(float)
    return live, fixed_r, margin, E, a


def simulate(forecast_date: pd.Timestamp = FORECAST_DATE) -> pd.DataFrame:
    """Run the 2026 forecast as of `forecast_date`; returns the chamber summary."""
    load_poll_error()
    rng = np.random.default_rng(SEED)
    races = poll_summary(load_races(), forecast_date)
    races["inc_side"] = races.apply(incumbency_side, axis=1)
    races["quality_diff"] = quality_diff(races)
    races["prior_edge"] = prior_edge(races)
    races["money_log_ratio"] = money_ratio(races)
    races["ideology_gap"] = ideology_gap(races)

    env = pd.read_csv(OUT / "national_env_2026_draws.csv")["dem_margin"].to_numpy()
    nat = pd.read_csv(RAW / "medsl" / "president_1976_2024.csv", encoding="latin-1")
    nat = nat[(nat.year == 2024) & nat.party_simplified.isin(["DEMOCRAT", "REPUBLICAN"])]
    D0, R0 = (nat.loc[nat.party_simplified == p, "candidatevotes"].sum() for p in ("DEMOCRAT", "REPUBLICAN"))
    live, fixed_r, margin, E, a = run_simulation(races, env, D0, R0, rng)
    office = live["office"].to_numpy()
    out = pd.concat([live, fixed_r], ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["office", "state_po", "district", "special", "race_type", "incumbent", "incumbent_party", "inc_side",
            "dem_candidate", "rep_candidate", "race_note", "pres24", "quality_diff", "prior_edge", "money_log_ratio", "money_adj", "quality_adj", "ideology_gap", "ideology_adj", "poll_count", "poll_avg",
            "poll_weight", "fundamentals_mean", "margin_median", "margin_p10", "margin_p90", "p_dem"]
    out["race_id"] = out.apply(race_id, axis=1)
    out[["race_id"] + cols].sort_values(["office", "state_po", "district"]).to_csv(OUT / "race_forecasts.csv", index=False)

    # ---- chambers ----
    win = margin > 0
    summ = {}
    for off in ("HOUSE", "SEN", "GOV"):
        m = (office == off)
        fixed_d = int(((fixed_r["office"] == off) & (fixed_r["race_note"] == "D")).sum())
        dem_wins = win[m].sum(axis=0) + fixed_d
        # A win in Nebraska's Senate race goes to Osborn (independent), not a Democrat.
        if off == "SEN":
            ne = ((live["office"] == "SEN") & (live["race_type"] == "independent")).to_numpy()
            osborn = win[ne].sum(axis=0)
            dem_wins = dem_wins - osborn
            summ["SEN_osborn_win"] = osborn.mean()
        summ[off] = dem_wins
    house_d = summ["HOUSE"]
    sen_d = 34 + summ["SEN"]                    # 32 D + 2 D-caucusing independents not up
    np.savez_compressed(OUT / "simulations.npz", house_d=house_d, sen_d=sen_d, gov_d=summ["GOV"], E=E, a=a)

    # ---- per-race detail for the website ----
    # Margin quantiles (for each race's distribution chart) and "leverage": how much
    # the chance of controlling the chamber moves with this one race.
    qs = np.arange(5, 100, 5)
    qtab = pd.DataFrame(np.percentile(margin, qs, axis=1).T, columns=[f"q{q:02d}" for q in qs])
    qtab.insert(0, "race_id", live.apply(race_id, axis=1))
    control = {"HOUSE": house_d >= 218, "SEN": sen_d >= 51}
    lev = np.full(len(live), np.nan)
    for i in range(len(live)):
        ctrl = control.get(office[i])
        w_ = win[i]
        if ctrl is not None and 0.01 < w_.mean() < 0.99:
            lev[i] = ctrl[w_].mean() - ctrl[~w_].mean()
    qtab["control_leverage"] = lev
    qtab.to_csv(OUT / "race_quantiles.csv", index=False)
    lines = [
        ("National House vote (D-R)", f"D{np.median(E):+.1f}", f"D{np.percentile(E, 10):+.1f} to D{np.percentile(E, 90):+.1f}"),
        ("House: Democratic seats", f"{np.median(house_d):.0f}", f"{np.percentile(house_d, 10):.0f}-{np.percentile(house_d, 90):.0f}"),
        ("House: P(Democratic majority, 218+)", f"{(house_d >= 218).mean():.0%}", ""),
        ("Senate: Democratic caucus seats", f"{np.median(sen_d):.0f}", f"{np.percentile(sen_d, 10):.0f}-{np.percentile(sen_d, 90):.0f}"),
        ("Senate: P(Democratic majority, 51+)", f"{(sen_d >= 51).mean():.0%}", ""),
        ("Senate: P(Osborn wins NE)", f"{summ['SEN_osborn_win']:.0%}", ""),
        ("Governors: Democratic wins of 36", f"{np.median(summ['GOV']):.0f}",
         f"{np.percentile(summ['GOV'], 10):.0f}-{np.percentile(summ['GOV'], 90):.0f}"),
    ]
    summary = pd.DataFrame(lines, columns=["measure", "median", "80% range"])
    summary.to_csv(OUT / "chamber_summary.csv", index=False)
    # Machine-readable topline for the run history / dashboard.
    pd.DataFrame([{
        "forecast_date": forecast_date.date(), "nat_median": np.median(E), "nat_p10": np.percentile(E, 10),
        "nat_p90": np.percentile(E, 90), "house_median": np.median(house_d), "house_p10": np.percentile(house_d, 10),
        "house_p90": np.percentile(house_d, 90), "p_house_d": (house_d >= 218).mean(),
        "senate_median": np.median(sen_d), "senate_p10": np.percentile(sen_d, 10), "senate_p90": np.percentile(sen_d, 90),
        "p_senate_d": (sen_d >= 51).mean(), "p_osborn": summ["SEN_osborn_win"],
        "gov_median": np.median(summ["GOV"]), "gov_p10": np.percentile(summ["GOV"], 10), "gov_p90": np.percentile(summ["GOV"], 90),
    }]).to_csv(OUT / "topline.csv", index=False)
    return summary


if __name__ == "__main__":
    for l in simulate().itertuples(index=False):
        print(f"{l[0]:<40} {l[1]:>6}   {l[2]}")
