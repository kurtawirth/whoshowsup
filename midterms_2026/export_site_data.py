"""Package model outputs into compact JSON files for the website (site/src/data/).

Run after the forecast (run_forecast.py calls it). Every file is plain JSON the
pages load directly; nothing here changes the model.

  topline.json      latest headline numbers + as-of date
  history.json      topline for every forecast date (the "over time" chart)
  seats.json        seat-count distributions (House, Senate, governors)
  races.json        one row per race: forecast, inputs, candidates
  race_detail.json  per race: polls, margin quantiles, forecast history, past results
  national.json     national environment: three reads, generic ballot, approval, specials
  track_record.json backtests: national and race-level calibration
  hexmap.json       House hex layout
  markets.json      PredictIt prices matched to our races (display only)
  changes.json      what moved since the previous daily run, and why (front page)
  counties.json     county results 2000-2024, eligible adults and turnout wave sensitivity (Past results page)
"""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "midterms_2026" / "models"))
from race_model import race_id, two_party, PARTISAN_BIAS  # noqa: E402

PROC, RAW = ROOT / "data" / "processed", ROOT / "data" / "raw"
OUT = ROOT / "midterms_2026" / "outputs"
SITE = ROOT / "site" / "src" / "data"
STATE_NAMES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
               "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
               "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
               "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
               "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
               "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
               "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
               "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
               "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
               "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"}
FIPS = {"AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10", "FL": "12",
        "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21", "LA": "22",
        "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29", "MT": "30", "NE": "31",
        "NV": "32", "NH": "33", "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39", "OK": "40",
        "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50",
        "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56"}


def clean(obj):
    """NaN -> None and numpy scalars -> Python, rounded, for compact valid JSON."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return None if np.isnan(obj) else round(float(obj), 3)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if obj is pd.NaT:
        return None
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    return obj


def write(name: str, obj) -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / name).write_text(json.dumps(clean(obj), separators=(",", ":")), encoding="utf-8")


def rating(p: float) -> str:
    """Our own probability bands (not anyone's ratings): Safe >95%, Likely 80-95, Lean 60-80, Toss-up."""
    if p >= 0.95: return "Safe D"
    if p >= 0.80: return "Likely D"
    if p >= 0.60: return "Lean D"
    if p > 0.40: return "Toss-up"
    if p > 0.20: return "Lean R"
    if p > 0.05: return "Likely R"
    return "Safe R"


def races() -> pd.DataFrame:
    f = pd.read_csv(OUT / "race_forecasts.csv")
    q = pd.read_csv(OUT / "race_quantiles.csv")
    f = f.merge(q[["race_id", "control_leverage"]], on="race_id", how="left")
    house = pd.read_csv(PROC / "races_2026_house.csv")[["state_po", "district", "lines_changed", "pres20_margin", "status_text"]]
    f = f.merge(house.assign(office="HOUSE"), on=["office", "state_po", "district"], how="left")
    money_path = PROC / "fec_money.csv"
    if money_path.exists():  # campaign money as of the June 30 FEC reports (House and Senate)
        m = pd.read_csv(money_path)
        m = m[m["year"] == 2026][["office", "state_po", "district", "special", "dem_money", "rep_money"]]
        f = f.merge(m, on=["office", "state_po", "district", "special"], how="left")
    else:
        f["dem_money"] = f["rep_money"] = np.nan
    f["state_name"] = f["state_po"].map(STATE_NAMES)
    f["rating"] = f["p_dem"].map(rating)
    f["label"] = np.where(f["office"] == "HOUSE",
                          f["state_po"] + "-" + np.where(f["district"] == 0, "AL", f["district"].astype(str)),
                          f["state_name"] + np.where(f["special"], " (special)", ""))
    f["dem_name"], f["rep_name"] = lead_names(f)
    return f


def lead_names(f: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """The one name to show for each side. Where a side has several candidates on the ballot (Alaska's
    top four, Louisiana's jungle races), use the one this race's polls test most often, else the
    incumbent if they're on that side, else the first listed."""
    polls = pd.read_csv(PROC / "polls_2026_races.csv")
    polls["special"] = polls["special"].astype(bool)
    out = {"D": [], "R": []}
    for r in f.itertuples():
        pr = polls[(polls["office"] == r.office) & (polls["state_po"] == r.state_po)
                   & (polls["district"] == r.district) & (polls["special"] == bool(r.special))]
        for side, col, sign in (("D", "dem_candidate", 1), ("R", "rep_candidate", -1)):
            names = [n.strip() for n in str(getattr(r, col) or "").split(";") if n.strip() and n.strip() != "nan"]
            name = names[0] if names else None
            if len(names) > 1 and r.race_type == "same_party":
                name = " / ".join(names)  # both finalists are from this party: show both
            elif len(names) > 1:
                tested = pr[col][pr[col].isin(names)].value_counts()
                if len(tested):
                    name = tested.index[0]
                elif r.inc_side == sign and isinstance(r.incumbent, str):
                    name = next((n for n in names if n.split()[-1] == r.incumbent.split()[-1]), r.incumbent)
            out[side].append(name)
    return pd.Series(out["D"], index=f.index), pd.Series(out["R"], index=f.index)


def poll_label(pollster: str, sponsors) -> str:
    """"YouGov for University of Texas": name the sponsor, since the link usually goes to the sponsor's release."""
    if not isinstance(sponsors, str) or not sponsors.strip() or sponsors.startswith("("):
        return pollster
    names = [x.strip() for x in sponsors.split(";") if x.strip()]
    if any(n.lower() in pollster.lower() for n in names):
        return pollster
    who = names[0] if len(names) == 1 else f"{names[0]} and {names[1]}" if len(names) == 2 else f"{names[0]} and others"
    return f"{pollster} for {who}"


def race_detail(f: pd.DataFrame) -> dict:
    polls = pd.read_csv(PROC / "polls_2026_races.csv", parse_dates=["end_date", "start_date"])
    polls["race_id"] = polls.apply(race_id, axis=1)
    polls["margin"] = two_party(polls["dem_pct"], polls["rep_pct"])
    # sponsored polls: the same correction the model applies (measured historical lean toward the sponsor)
    polls["bias"] = polls.apply(lambda x: PARTISAN_BIAS[x["office"]].get(x["partisan"], 0.0)
                                if isinstance(x["partisan"], str) else 0.0, axis=1)
    polls["adj"] = polls["margin"] - polls["bias"]
    q = pd.read_csv(OUT / "race_quantiles.csv").set_index("race_id")
    # forecast history per race from the dated snapshots
    snaps = []
    for d in sorted((OUT / "history").glob("*")):
        s = pd.read_csv(d / "race_forecasts.csv")
        if "race_id" in s:
            snaps.append(s[["race_id", "p_dem", "margin_median"]].assign(date=d.name))
    hist = pd.concat(snaps) if snaps else pd.DataFrame(columns=["race_id", "p_dem", "margin_median", "date"])
    past = past_results()
    out = {}
    for _, r in f.iterrows():
        rid = r["race_id"]
        p = polls[polls["race_id"] == rid].sort_values("end_date", ascending=False)
        out[rid] = {
            "polls": [{"pollster": poll_label(x.pollster, x.sponsors), "end": x.end_date, "start": x.start_date, "n": x.sample_size,
                       "pop": x.population, "partisan": x.partisan if isinstance(x.partisan, str) else "",
                       "sponsors": x.sponsors if isinstance(x.sponsors, str) else "", "d": x.dem_pct,
                       "r": x.rep_pct, "margin": x.margin, "adj": x.adj, "url": x.url, "source": x.source}
                      for x in p.itertuples()],
            "quantiles": q.loc[rid].drop("control_leverage").tolist() if rid in q.index else None,
            "history": hist[hist["race_id"] == rid][["date", "p_dem", "margin_median"]].to_dict("records"),
            "past": past.get((r["office"], r["state_po"], int(r["district"])), []),
        }
    return out


def past_results() -> dict:
    """Past results to show on each race page: statewide presidential, Senate, and governor
    margins for Senate/Governor races; presidential margins for House districts."""
    out = {}
    p = pd.read_csv(RAW / "medsl" / "president_1976_2024.csv", encoding="latin-1")
    p = p[(p.year >= 2000) & p.party_simplified.isin(["DEMOCRAT", "REPUBLICAN"])]
    pres = p.pivot_table(index=["state_po", "year"], columns="party_simplified", values="candidatevotes", aggfunc="sum")
    pres["m"] = two_party(pres["DEMOCRAT"], pres["REPUBLICAN"])
    cal = pd.read_csv(PROC / "statewide_calibration.csv")
    for st in STATE_NAMES:
        rows = [{"year": int(y), "office": "President", "margin": m} for (s_, y), m in pres["m"].items() if s_ == st]
        # Skip races an independent won (e.g. Angus King in Maine): a D-vs-R margin misdescribes them.
        sen = cal[(cal.office == "SEN") & (cal.state_po == st) & (cal.year >= 2000) & (cal.winner_side != "O")]
        rows += [{"year": int(r.year), "office": "Senate" + (" (special)" if r.special else ""), "margin": r.margin}
                 for r in sen.itertuples()]
        rows += [{"year": int(r.year), "office": "Governor", "margin": r.margin}
                 for r in cal[(cal.office == "GOV") & (cal.state_po == st)].itertuples()]
        rows = sorted(rows, key=lambda x: (-x["year"], x["office"]))
        out[("SEN", st, 0)] = out[("GOV", st, 0)] = rows
    h = pd.read_csv(PROC / "races_2026_house.csv")
    for r in h.itertuples():
        rows = [{"year": 2024, "office": "President", "margin": r.pres24_margin}]
        if not np.isnan(r.pres20_margin):
            rows.append({"year": 2020, "office": "President", "margin": r.pres20_margin})
        out[("HOUSE", r.state_po, int(r.district))] = rows
    return out


def national() -> dict:
    hist = pd.read_csv(PROC / "national_history.csv")
    reads = pd.read_csv(OUT / "national_env_reads.csv")
    draws = pd.read_csv(OUT / "national_env_2026_draws.csv")["dem_margin"]
    gen = pd.read_csv(PROC / "polls_2026_generic.csv", parse_dates=["end_date"])
    gen = gen[gen["end_date"] >= "2025-06-01"].copy()
    gen["margin"] = two_party(gen["dem_pct"], gen["rep_pct"])
    app = pd.read_csv(PROC / "polls_2026_approval.csv", parse_dates=["end_date"])
    app = app[app["end_date"] >= "2025-01-20"]
    spec = pd.read_csv(PROC / "special_elections.csv", parse_dates=["date"])
    return {
        "reads": reads.to_dict("records"),
        "env": {"median": draws.median(), "p10": draws.quantile(.1), "p90": draws.quantile(.9),
                "hist": np.histogram(draws, bins=np.arange(-6, 20.5, 0.5))[0].tolist(), "hist_start": -6, "hist_step": 0.5},
        "history": hist[["year", "pres_party", "midterm", "house_margin", "net_approval", "generic_margin",
                         "specials_implied", "specials_n", "specials_overperf", "last_pres_margin"]].to_dict("records"),
        "generic": gen[["end_date", "pollster", "population", "margin", "dem_pct", "rep_pct", "url"]].to_dict("records"),
        "approval": app[["end_date", "pollster", "approve", "disapprove"]].dropna().to_dict("records"),
        "specials": spec[spec["year"] >= 2017][["date", "state_po", "district", "chamber", "special_margin",
                                                "pres_margin", "overperformance", "year", "flipped", "held_by", "winner",
                                                "pres_baseline"]].to_dict("records"),
    }


def track_record() -> dict:
    out = {}
    for name in ("backtest_scores", "backtest_chambers", "backtest_calibration", "national_env_backtest"):
        p = OUT / f"{name}.csv"
        if p.exists():
            out[name] = pd.read_csv(p).to_dict("records")
    return out


# Display order and kind for the comparison page. "model" = publishes a statistical forecast.
OUTLET_ORDER = [("Cook Political Report", "Cook", "rater"), ("Sabato's Crystal Ball", "Sabato", "rater"),
                ("Inside Elections", "Inside Elections", "rater"), ("Silver Bulletin", "Silver Bulletin", "model"),
                ("The Economist", "Economist", "model"), ("Split Ticket", "Split Ticket", "model"),
                ("DDHQ", "DDHQ", "model"), ("FiftyPlusOne", "FiftyPlusOne", "model"),
                ("RealClearPolitics", "RCP", "rater"), ("Fox News", "Fox News", "rater")]


def outlets(f: pd.DataFrame) -> dict:
    """Other forecasters' current ratings next to ours (display only -- never a model input),
    plus the past head-to-head results from core/compare_outlets.py."""
    path = PROC / "outlet_ratings.csv"
    out = {"outlets": [], "races": {}, "track": [], "track_races": []}
    if path.exists():
        r = pd.read_csv(path)
        r = r[(r["year"] == 2026) & (r["asof"] == "current")].copy()
        if len(r):
            r["special"] = r["special"].astype(bool)
            r["race_id"] = r.apply(race_id, axis=1)
            r = r[r["race_id"].isin(set(f["race_id"]))]
            present = set(r["outlet"])
            order = [o for o in OUTLET_ORDER if o[0] in present] + [(o, o, "rater") for o in sorted(present - {x[0] for x in OUTLET_ORDER})]
            for name, short, kind in order:
                x = r[r["outlet"] == name]
                dates = x["rated_on"].dropna() if "rated_on" in x else pd.Series(dtype=str)
                out["outlets"].append({"name": name, "short": short, "kind": kind, "races": int(len(x)),
                                       "rated_on": dates.max() if len(dates) else None})
            for rid, g in r.groupby("race_id"):
                out["races"][rid] = {row.outlet: row.rating for row in g.itertuples()}
    comp = OUT / "outlet_comparison.csv"
    if comp.exists():
        out["track"] = pd.read_csv(comp).to_dict("records")
    return out


def markets() -> dict:
    """PredictIt prices matched to our races (core/predictit_markets.py) -- display only, never a model input."""
    path = PROC / "markets_predictit.csv"
    if not path.exists():
        return {"asof": None, "races": {}, "history": []}
    m = pd.read_csv(path)
    last = m["date"].max()
    cur = m[m["date"] == last]
    ctrl = m[m["race_id"].str.startswith("control-")].pivot_table(index="date", columns="race_id", values="p_dem")
    return {"asof": last,
            "races": {r.race_id: {"p": r.p_dem, "url": r.url} for r in cur.itertuples()},
            "history": [{"date": d, "house": row.get("control-house"), "senate": row.get("control-senate")}
                        for d, row in ctrl.iterrows()]}


POLL_KEY = ["office", "state_po", "district", "special", "pollster", "end_date", "dem_pct", "rep_pct", "population"]


def changes(min_move: float = 0.02, top_n: int = 8) -> dict:
    """What moved since the previous daily run, and roughly why. A race's forecast margin is about
    w x poll average + (1 - w) x fundamentals (w = the polls' weight), so a change splits into: polls
    (new polls, or older ones fading), the national estimate, campaign money, candidate factors
    (experience, ideology), and anything else, each in points of margin toward the Democratic side."""
    hist = OUT / "history"
    days = sorted(p.name for p in hist.iterdir() if (p / "race_forecasts.csv").exists())
    if len(days) < 2:
        return {}
    d0, d1 = days[-2], days[-1]
    t0, t1 = (pd.read_csv(hist / d / "topline.csv").iloc[0] for d in (d0, d1))
    f0, f1 = (pd.read_csv(hist / d / "race_forecasts.csv").set_index("race_id") for d in (d0, d1))
    f = f1.join(f0, rsuffix="_0", how="inner")
    f = f[f["race_type"] != "same_party"]
    dnat = float(t1["nat_median"] - t0["nat_median"])
    polls = {d: pd.read_csv(hist / d / "polls.csv") if (hist / d / "polls.csv").exists() else None for d in (d0, d1)}
    new_polls = None
    if polls[d0] is not None and polls[d1] is not None:
        a, b = (polls[d][POLL_KEY].map(str).agg("|".join, axis=1) for d in (d0, d1))  # map(str): blanks become "nan", not NaN
        new_polls = polls[d1][~b.isin(set(a))]
    rows = []
    for rid, r in f.iterrows():
        dp = float(r["p_dem"] - r["p_dem_0"])
        if abs(dp) < min_move:
            continue
        w1, w0 = (0.0 if pd.isna(x) else float(x) for x in (r["poll_weight"], r["poll_weight_0"]))
        pa1, pa0 = (0.0 if pd.isna(x) else float(x) for x in (r["poll_avg"], r["poll_avg_0"]))
        g = lambda c: (0.0 if pd.isna(r.get(c)) else float(r[c])) - (0.0 if pd.isna(r.get(c + "_0")) else float(r[c + "_0"]))  # noqa: E731
        parts = {"polls": w1 * pa1 - w0 * pa0 - (w1 - w0) * float(r["fundamentals_mean_0"]),
                 "national": (1 - w1) * dnat,
                 "money": (1 - w1) * g("money_adj"),
                 "candidates": (1 - w1) * (g("quality_adj") + g("ideology_adj"))}
        dm = float(r["margin_median"] - r["margin_median_0"])
        parts["other"] = dm - sum(parts.values())
        n_new = int(r["poll_count"] - r["poll_count_0"]) if pd.notna(r["poll_count"]) and pd.notna(r["poll_count_0"]) else 0
        names = []
        if new_polls is not None:
            m = new_polls[(new_polls["office"] == r["office"]) & (new_polls["state_po"] == r["state_po"])
                          & (new_polls["district"] == r["district"]) & (new_polls["special"].astype(str) == str(r["special"]))]
            n_new, names = len(m), sorted(set(m["pollster"].astype(str)))
        rows.append({"race_id": rid, "p0": float(r["p_dem_0"]), "p1": float(r["p_dem"]), "m0": float(r["margin_median_0"]),
                     "m1": float(r["margin_median"]), "new_polls": n_new, "pollsters": names[:4],
                     "parts": {k: round(v, 2) for k, v in parts.items()}})
    rows.sort(key=lambda x: -abs(x["p1"] - x["p0"]))
    return {"date": d1, "prev": d0, "nat0": float(t0["nat_median"]), "nat1": float(t1["nat_median"]),
            "house0": float(t0["p_house_d"]), "house1": float(t1["p_house_d"]),
            "senate0": float(t0["p_senate_d"]), "senate1": float(t1["p_senate_d"]),
            "moved": len(rows), "races": rows[:top_n]}


def counties() -> dict:
    """County-level results for the Past results page (display only): presidential 2000-2024, Senate and
    governor 2018-2024 (core/build_county_results.py); eligible adults (Census CVAP, 2008 on, as in
    core/turnout_sensitivity.py) for turnout; and each county's turnout wave sensitivity
    (core/turnout_sensitivity.py). Alaska reports by legislative district rather than borough, so it has
    no county rows. Compact: {fips: {"PRES-2024": [dem, rep, total], ...}}."""
    res = pd.read_parquet(PROC / "county_results.parquet")
    res = res[res["county_fips"].notna()]
    res["key"] = res["office"] + "-" + res["year"].astype(str) + np.where(res["special"], "-special", "")
    res["fips"] = res["county_fips"].astype(int).astype(str).str.zfill(5)
    out = {}
    for r in res.itertuples():
        out.setdefault(r.fips, {})[r.key] = [int(r.dem), int(r.rep), int(r.total)]
    import sys
    sys.path.insert(0, str(ROOT / "core"))
    from turnout_sensitivity import load_cvap
    cv = load_cvap()
    cvap = {}
    for r in cv.dropna(subset=["cvap", "county_fips", "year"]).itertuples():
        cvap.setdefault(str(int(r.county_fips)).zfill(5), {})[str(int(r.year))] = int(round(r.cvap))
    sens = {}
    sp = PROC / "county_turnout_sensitivity.parquet"
    if sp.exists():
        s = pd.read_parquet(sp)
        for r in s.itertuples():
            if pd.notna(r.dem_beta) and pd.notna(r.rep_beta):
                sens[str(int(r.county_fips)).zfill(5)] = [round(float(r.dem_beta), 2), round(float(r.rep_beta), 2)]
    elections = (res.drop_duplicates("key")[["key", "year", "office", "special"]]
                 .sort_values(["year", "office"]).to_dict("records"))
    names = {str(int(r.county_fips)).zfill(5): str(r.name).split(",")[0] for r in cv.dropna(subset=["name"]).drop_duplicates("county_fips", keep="last").itertuples()}
    # Alaska reports by state legislative district, not borough, so it's shown as one statewide unit ("02000")
    ak = [f for f in out if f.startswith("02")]
    if ak:
        agg = {}
        for f in ak:
            for k, v in out.pop(f).items():
                agg[k] = [a + b for a, b in zip(agg.get(k, [0, 0, 0]), v)]
        # MEDSL's statewide presidential totals, not the districts added up: its 2004 district file sums to
        # about 1.5 times Alaska's real vote (every other year matches)
        pres = pd.read_csv(RAW / "medsl" / "president_1976_2024.csv", encoding="latin-1")
        pres = pres[(pres["state_po"] == "AK") & (pres["year"] >= 2000)]
        for y, g in pres.groupby("year"):
            d_ = int(g.loc[g["party_simplified"] == "DEMOCRAT", "candidatevotes"].sum())
            r_ = int(g.loc[g["party_simplified"] == "REPUBLICAN", "candidatevotes"].sum())
            agg[f"PRES-{y}"] = [d_, r_, int(g["totalvotes"].iloc[0])]
        # the 2020 Senate race (Sullivan vs. Gross) isn't in the precinct files used above: MEDSL's statewide file
        sen = pd.read_csv(RAW / "medsl" / "senate_1976_2024.csv", encoding="latin-1")
        sen = sen[(sen["state_po"] == "AK") & (sen["year"] == 2020) & (sen["stage"].str.lower() == "gen")]
        if len(sen) and "SEN-2020" not in agg:
            agg["SEN-2020"] = [int(sen.loc[sen["party_simplified"] == "DEMOCRAT", "candidatevotes"].sum()),
                               int(sen.loc[sen["party_simplified"] == "REPUBLICAN", "candidatevotes"].sum()),
                               int(sen["totalvotes"].iloc[0])]
        out["02000"] = agg
        years = {y for f in cvap if f.startswith("02") for y in cvap[f]}
        cvap["02000"] = {y: sum(cvap[f].get(y, 0) for f in list(cvap) if f.startswith("02") and f != "02000") for y in years}
        names["02000"] = "Alaska (statewide)"
    return {"elections": elections, "results": out, "cvap": cvap, "sensitivity": sens, "names": names}


def early_vote() -> dict:
    """Early and absentee voting by state (core/early_vote.py, civicAPI): the latest counts, the daily
    series of ballots cast, and each state's 2022 turnout (all U.S. House votes) for scale."""
    path = PROC / "early_vote.csv"
    if not path.exists():
        return {"states": [], "series": []}
    d = pd.read_csv(path)
    d = d[d["date"] <= f"{pd.Timestamp.today():%Y-%m-%d}"]
    wide = d.pivot_table(index=["state_po", "date"], columns="category", values="total", aggfunc="last")
    wide = wide.reindex(columns=["requested", "returned", "inperson"])
    # states don't report every day: carry each state's last count forward over the days it skipped
    days = pd.date_range(d["date"].min(), d["date"].max()).strftime("%Y-%m-%d")
    wide = wide.reindex(pd.MultiIndex.from_product([wide.index.levels[0], days], names=["state_po", "date"]))
    wide = wide.groupby(level=0).ffill().fillna(0)
    wide["cast"] = wide["returned"] + wide["inperson"]
    series = wide.reset_index()[["date", "state_po", "cast"]]
    # party registration of ballots cast (returned + in person), where the state records party
    cast = d[d["category"].isin(["returned", "inperson"]) & d["dem"].notna()]
    latest_date = d.groupby("state_po")["date"].max()
    cast = cast[cast["date"] == cast["state_po"].map(latest_date)]
    party = cast.groupby("state_po")[["dem", "rep", "other"]].sum()
    h = pd.read_csv(RAW / "medsl" / "house_1976_2024.tab", sep=None, engine="python", encoding="latin-1")
    h = h[(h["year"] == 2022) & (h["stage"].str.upper() == "GEN")]
    t22 = h.groupby("state_po")["candidatevotes"].sum()
    last = wide.groupby(level=0).tail(1).reset_index()
    rows = []
    for r in last.itertuples():
        row = {"state_po": r.state_po, "state_name": STATE_NAMES.get(r.state_po, r.state_po), "date": r.date,
               "requested": int(r.requested), "returned": int(r.returned), "inperson": int(r.inperson),
               "cast": int(r.cast), "turnout22": int(t22.get(r.state_po, 0))}
        if r.state_po in party.index and party.loc[r.state_po].sum() > 0:
            row.update({k: int(party.loc[r.state_po, k]) for k in ("dem", "rep", "other")})
        rows.append(row)
    mode_path = PROC / "early_vote_by_mode.csv"  # core/early_vote_history.py (Cooperative Election Study)
    by_mode = pd.read_csv(mode_path).to_dict("records") if mode_path.exists() else []
    return {"as_of": str(d["date"].max()), "states": rows, "series": series.to_dict("records"), "by_mode": by_mode}


def seats() -> dict:
    s = np.load(OUT / "simulations.npz")
    def dist(a, lo, hi):
        vals, counts = np.unique(a, return_counts=True)
        m = dict(zip(vals.tolist(), counts.tolist()))
        return [{"seats": k, "p": m.get(k, 0) / len(a)} for k in range(lo, hi + 1)]
    return {"house": dist(s["house_d"], int(s["house_d"].min()), int(s["house_d"].max())),
            "senate": dist(s["sen_d"], int(s["sen_d"].min()), int(s["sen_d"].max())),
            "governor": dist(s["gov_d"], int(s["gov_d"].min()), int(s["gov_d"].max()))}


def main() -> None:
    top = pd.read_csv(OUT / "topline.csv").iloc[0].to_dict()
    top["election_day"] = "2026-11-03"
    p = pd.read_csv(RAW / "medsl" / "president_1976_2024.csv", encoding="latin-1")
    p = p[(p.year == 2024) & p.party_simplified.isin(["DEMOCRAT", "REPUBLICAN"])]
    d, r = (p.loc[p.party_simplified == x, "candidatevotes"].sum() for x in ("DEMOCRAT", "REPUBLICAN"))
    top["nat_pres24"] = two_party(d, r)  # baseline the national shift is measured from
    write("topline.json", top)
    hist_path = OUT / "forecast_history.csv"
    write("history.json", pd.read_csv(hist_path).to_dict("records") if hist_path.exists() else [])
    write("seats.json", seats())
    f = races()
    cols = ["race_id", "label", "office", "state_po", "state_name", "district", "special", "race_type", "race_note",
            "incumbent", "incumbent_party", "inc_side", "dem_candidate", "rep_candidate", "dem_name", "rep_name", "pres24", "pres20_margin",
            "lines_changed", "quality_diff", "prior_edge", "dem_money", "rep_money", "money_adj", "quality_adj", "ideology_adj", "poll_count", "poll_avg", "poll_undecided", "poll_weight",
            "fundamentals_mean", "margin_median", "margin_p10", "margin_p90", "p_dem", "rating", "control_leverage"]
    write("races.json", f[cols].to_dict("records"))
    write("race_detail.json", race_detail(f))
    write("national.json", national())
    write("track_record.json", track_record())
    write("outlets.json", outlets(f))
    hexmap = json.loads((PROC / "house_hexmap.json").read_text())
    write("hexmap.json", hexmap)
    write("states.json", {"names": STATE_NAMES, "fips": FIPS})
    write("early_vote.json", early_vote())
    write("markets.json", markets())
    write("changes.json", changes())
    write("counties.json", counties())
    import share_card  # the preview image for shared links, with today's odds
    share_card.make()
    sizes = {p.name: f"{p.stat().st_size / 1024:.0f} KB" for p in sorted(SITE.glob("*.json"))}
    print("wrote", sizes)


if __name__ == "__main__":
    main()
