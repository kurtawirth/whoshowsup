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
FORECAST_DATE = pd.Timestamp("2026-09-22")

# ---- calibrated constants (see the core/*_calibration.py scripts) ----
INCUMBENCY = {"HOUSE": 2.3, "SEN": 5.4, "GOV": 4.5}
# Personal vote: an incumbent's previous over/under-performance vs lean + environment
# partly persists. expected edge = intercept + rho * previous edge; the remaining noise
# is smaller than for a generic race. Estimated from re-running incumbents
# (Senate 2012-2024, n=159; Governor 2018->2022, n=26).
PERSONAL = {"SEN": {"intercept": 3.0, "rho": 0.43, "sd": 9.1},
            "GOV": {"intercept": 5.1, "rho": 0.63, "sd": 8.2}}
# Governors whose previous race was not their own (first elected 2024, or took office mid-term).
GOV_NO_PRIOR = {"NH", "SD"}
FUND_SD = {"HOUSE_inc": 6.0, "HOUSE_open": 7.0, "SEN": 11.0, "GOV": 8.5}
POLL_FLOOR = {"HOUSE": 9.0, "SEN": 6.0, "GOV": 6.1}
POLL_SPREAD = {"HOUSE": 1.2, "SEN": 6.5, "GOV": 6.2}
PARTISAN_BIAS = {"HOUSE": {"D": 5.4, "R": -5.6}, "SEN": {"D": 3.4, "R": -3.9}, "GOV": {"D": 4.1, "R": -3.5}}
PARTISAN_WEIGHT = 0.5                  # user decision: corrected partisan polls count half
POLL_HALF_LIFE_DAYS = 30
POP_WEIGHT = {"lv": 1.0, "rv": 0.8, "v": 0.9, "a": 0.6}
# Candidate quality: points of margin per tier of prior-office advantage. Not estimated
# from our data (would need coded candidates for past cycles) -- a literature-based
# prior, deliberately modest, and swamped by polls wherever polls exist.
QUALITY_PER_TIER = 1.0
TURNOUT_SHARE_MEAN, TURNOUT_SHARE_CONC = 0.65, 6.0
STATE_SHOCK_SD, REGION_SHOCK_SD = 2.0, 2.0
# Osborn ran ~15 pts ahead of a generic Democrat's expected margin in NE in 2024;
# shrink toward zero and widen, since independents' appeal is volatile.
INDEPENDENT_ADJ = {("SEN", "NE", 0): (10.0, 6.0), ("HOUSE", "CA", 6): (0.0, 4.0)}
REGION = {**dict.fromkeys(["CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"], "NE"),
          **dict.fromkeys(["IL", "IN", "MI", "OH", "WI", "IA", "KS", "MN", "MO", "NE", "ND", "SD"], "MW"),
          **dict.fromkeys(["DE", "FL", "GA", "MD", "NC", "SC", "VA", "DC", "WV", "AL", "KY", "MS", "TN",
                           "AR", "LA", "OK", "TX"], "S"),
          **dict.fromkeys(["AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY", "AK", "CA", "HI", "OR", "WA"], "W")}


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


def quality_diff(races: pd.DataFrame) -> pd.Series:
    q = pd.read_csv(PROC / "candidate_quality_2026.csv")
    # Several R candidates on one ballot (Alaska top-four): the bloc's best-known name anchors it.
    q = q.groupby(["office", "state_po", "special", "side"])["tier"].max().unstack("side")
    key = list(zip(races["office"], races["state_po"], races["special"]))
    dem = [q["dem"].get(k, np.nan) if k in q.index else np.nan for k in key]
    rep = [q["rep"].get(k, np.nan) if k in q.index else np.nan for k in key]
    return (pd.Series(dem, index=races.index) - pd.Series(rep, index=races.index)).fillna(0)


def prior_edge(races: pd.DataFrame) -> pd.Series:
    """Each Senate/Governor incumbent's edge in their previous race (toward them, points)."""
    cal = pd.read_csv(PROC / "statewide_calibration.csv")
    out = pd.Series(np.nan, index=races.index)
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


def poll_summary(races: pd.DataFrame) -> pd.DataFrame:
    polls = pd.read_csv(PROC / "polls_2026_races.csv", parse_dates=["end_date"])
    polls = polls[polls["end_date"] <= FORECAST_DATE]
    # Multi-candidate primary polls (e.g. California's all-party primary) can list both
    # nominees; if the pair holds under 60% it was not a head-to-head general poll.
    polls = polls[(polls["dem_pct"] + polls["rep_pct"]) >= 60]
    # Alaska governor: ranked-choice with three Republicans splitting first-round polls,
    # so a head-to-head reading of those polls is meaningless.
    polls = polls[~((polls["office"] == "GOV") & (polls["state_po"] == "AK"))]
    polls["partisan"] = polls["partisan"].fillna("")
    polls["margin"] = two_party(polls["dem_pct"], polls["rep_pct"])
    bias = polls.apply(lambda p: PARTISAN_BIAS[p["office"]].get(p["partisan"], 0.0), axis=1)
    polls["adj"] = polls["margin"] - bias
    age = (FORECAST_DATE - polls["end_date"]).dt.days.clip(lower=0)
    n = polls["sample_size"].fillna(600).clip(200, 3000)
    polls["w"] = (0.5 ** (age / POLL_HALF_LIFE_DAYS)
                  * np.sqrt(n / 600)
                  * polls["population"].fillna("").map(POP_WEIGHT).fillna(0.8)
                  * np.where(polls["partisan"] != "", PARTISAN_WEIGHT, 1.0))
    g = polls.groupby(["office", "state_po", "district", "special"])
    summ = pd.DataFrame({
        "poll_avg": g.apply(lambda x: np.average(x["adj"], weights=x["w"]), include_groups=False),
        "poll_n_eff": g["w"].sum(), "poll_count": g.size(),
        "poll_last": g["end_date"].max(),
    }).reset_index()
    return races.merge(summ, on=["office", "state_po", "district", "special"], how="left")


def simulate() -> None:
    rng = np.random.default_rng(SEED)
    races = poll_summary(load_races())
    races["inc_side"] = races.apply(incumbency_side, axis=1)
    races["quality_diff"] = np.where(races["office"] == "HOUSE", 0.0, quality_diff(races))
    fixed = races["race_type"] == "same_party"

    env = pd.read_csv(OUT / "national_env_2026_draws.csv")["dem_margin"].to_numpy()
    E = rng.choice(env, N_SIMS)
    E_bar = env.mean()
    a = rng.beta(TURNOUT_SHARE_MEAN * TURNOUT_SHARE_CONC, (1 - TURNOUT_SHARE_MEAN) * TURNOUT_SHARE_CONC, N_SIMS)

    # National 2024 presidential baseline (two-party), for the swing and the shaped scaling.
    nat = pd.read_csv(RAW / "medsl" / "president_1976_2024.csv", encoding="latin-1")
    nat = nat[(nat.year == 2024) & nat.party_simplified.isin(["DEMOCRAT", "REPUBLICAN"])]
    D0, R0 = (nat.loc[nat.party_simplified == p, "candidatevotes"].sum() for p in ("DEMOCRAT", "REPUBLICAN"))
    nat_pres = two_party(D0, R0)
    s = (E / 100 + 1) / 2
    ratio = s / (1 - s) * R0 / D0                        # multiply D votes by this to hit E nationally

    live = races[~fixed].reset_index(drop=True)
    d24, r24, pres24 = (live[c].to_numpy()[:, None] for c in ("d24", "r24", "pres24"))
    shaped = two_party(d24 * ratio[None, :], r24)
    swing = pres24 + (E - nat_pres)[None, :]
    base = a[None, :] * shaped + (1 - a[None, :]) * swing

    office = live["office"].to_numpy()
    inc = live["inc_side"].to_numpy() * np.vectorize(INCUMBENCY.get)(office)
    edge = prior_edge(live).to_numpy()
    adj = live["quality_diff"].to_numpy() * QUALITY_PER_TIER
    fund_sd = np.where(office == "HOUSE", np.where(live["inc_side"] != 0, FUND_SD["HOUSE_inc"], FUND_SD["HOUSE_open"]),
                       np.vectorize(FUND_SD.get)(np.where(office == "HOUSE", "SEN", office)))
    for i, r in live.iterrows():
        k = (r["office"], r["state_po"], int(r["district"]) if r["office"] == "HOUSE" else 0)
        if k in INDEPENDENT_ADJ:
            shift, extra = INDEPENDENT_ADJ[k]
            adj[i] += shift if r["race_type"] == "independent" and r["office"] == "SEN" else 0
            fund_sd[i] = np.hypot(fund_sd[i], extra)
    # Senate/Governor incumbents: replace the flat incumbency bonus with the personal vote.
    for i in range(len(live)):
        o = office[i]
        if o in PERSONAL and live.loc[i, "inc_side"] != 0:
            p_ = PERSONAL[o]
            prev = 0.0 if np.isnan(edge[i]) else edge[i]
            inc[i] = live.loc[i, "inc_side"] * (p_["intercept"] + p_["rho"] * prev)
            if not np.isnan(edge[i]):
                fund_sd[i] = p_["sd"]
    live["prior_edge"] = edge
    fund = base + (inc + adj)[:, None]

    # ---- polls: Bayesian precision weighting against the fundamentals ----
    has_poll = live["poll_avg"].notna().to_numpy()
    n_eff = live["poll_n_eff"].fillna(0).to_numpy()
    floor = np.vectorize(POLL_FLOOR.get)(office)
    spread = np.vectorize(POLL_SPREAD.get)(office)
    env_sd = env.std()
    poll_sd = np.sqrt(np.maximum(floor ** 2 - env_sd ** 2, 1.0) + spread ** 2 / np.maximum(n_eff, 1e-9))
    w_poll = np.where(has_poll, fund_sd ** 2 / (fund_sd ** 2 + poll_sd ** 2), 0.0)
    poll_now = live["poll_avg"].fillna(0).to_numpy()[:, None] + (E - E_bar)[None, :]
    mean = w_poll[:, None] * poll_now + (1 - w_poll[:, None]) * fund
    post_sd = np.where(has_poll, np.sqrt(fund_sd ** 2 * poll_sd ** 2 / (fund_sd ** 2 + poll_sd ** 2)), fund_sd)

    # ---- correlated error: state + region + race ----
    states = sorted(races["state_po"].unique())
    regions = sorted(set(REGION.values()))
    st_shock = rng.normal(0, STATE_SHOCK_SD, (len(states), N_SIMS))
    rg_shock = rng.normal(0, REGION_SHOCK_SD, (len(regions), N_SIMS))
    si = live["state_po"].map({s_: i for i, s_ in enumerate(states)}).to_numpy()
    ri = live["state_po"].map(lambda s_: regions.index(REGION[s_])).to_numpy()
    own_sd = np.sqrt(np.maximum(post_sd ** 2 - STATE_SHOCK_SD ** 2 - REGION_SHOCK_SD ** 2, 2.0 ** 2))
    margin = mean + st_shock[si] + rg_shock[ri] + rng.normal(0, 1, mean.shape) * own_sd[:, None]

    live["p_dem"] = (margin > 0).mean(axis=1)
    live["margin_median"] = np.median(margin, axis=1)
    live["margin_p10"], live["margin_p90"] = np.percentile(margin, [10, 90], axis=1)
    live["fundamentals_mean"] = fund.mean(axis=1)
    live["poll_weight"] = w_poll
    fixed_r = races[fixed].copy()
    fixed_r["p_dem"] = (fixed_r["race_note"] == "D").astype(float)
    out = pd.concat([live, fixed_r], ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["office", "state_po", "district", "special", "race_type", "incumbent", "incumbent_party", "inc_side",
            "dem_candidate", "rep_candidate", "race_note", "pres24", "quality_diff", "prior_edge", "poll_count", "poll_avg",
            "poll_weight", "fundamentals_mean", "margin_median", "margin_p10", "margin_p90", "p_dem"]
    out[cols].sort_values(["office", "state_po", "district"]).to_csv(OUT / "race_forecasts.csv", index=False)

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
    pd.DataFrame(lines, columns=["measure", "median", "80% range"]).to_csv(OUT / "chamber_summary.csv", index=False)
    for l in lines:
        print(f"{l[0]:<40} {l[1]:>6}   {l[2]}")


if __name__ == "__main__":
    simulate()
