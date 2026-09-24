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
    f["state_name"] = f["state_po"].map(STATE_NAMES)
    f["rating"] = f["p_dem"].map(rating)
    f["label"] = np.where(f["office"] == "HOUSE",
                          f["state_po"] + "-" + np.where(f["district"] == 0, "AL", f["district"].astype(str)),
                          f["state_name"] + np.where(f["special"], " (special)", ""))
    return f


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
                         "specials_implied"]].to_dict("records"),
        "generic": gen[["end_date", "pollster", "population", "margin", "dem_pct", "rep_pct", "url"]].to_dict("records"),
        "approval": app[["end_date", "pollster", "approve", "disapprove"]].dropna().to_dict("records"),
        "specials": spec[spec["year"] >= 2017][["date", "state_po", "district", "chamber", "special_margin",
                                                "pres_margin", "overperformance", "year", "flipped"]].to_dict("records"),
    }


def track_record() -> dict:
    out = {}
    for name in ("backtest_scores", "backtest_chambers", "backtest_calibration", "national_env_backtest"):
        p = OUT / f"{name}.csv"
        if p.exists():
            out[name] = pd.read_csv(p).to_dict("records")
    return out


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
            "incumbent", "incumbent_party", "inc_side", "dem_candidate", "rep_candidate", "pres24", "pres20_margin",
            "lines_changed", "quality_diff", "prior_edge", "poll_count", "poll_avg", "poll_weight",
            "fundamentals_mean", "margin_median", "margin_p10", "margin_p90", "p_dem", "rating", "control_leverage"]
    write("races.json", f[cols].to_dict("records"))
    write("race_detail.json", race_detail(f))
    write("national.json", national())
    write("track_record.json", track_record())
    hexmap = json.loads((PROC / "house_hexmap.json").read_text())
    write("hexmap.json", hexmap)
    write("states.json", {"names": STATE_NAMES, "fips": FIPS})
    sizes = {p.name: f"{p.stat().st_size / 1024:.0f} KB" for p in sorted(SITE.glob("*.json"))}
    print("wrote", sizes)


if __name__ == "__main__":
    main()
