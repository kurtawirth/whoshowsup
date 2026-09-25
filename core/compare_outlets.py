"""How would Who Shows Up have done against the major forecasters? Head-to-head on past elections.

    .venv/Scripts/python.exe core/compare_outlets.py

Needs: midterms_2026/outputs/backtest_race_forecasts.csv (Sept 22) and _eve.csv (Election Eve)
from backtest_races.py; data/processed/outlet_ratings.csv (core/outlet_ratings.py); and
FiveThirtyEight's archived daily forecasts in data/raw/fte_forecasts/.

Fairness rules
  - Same date: each outlet is compared with our model run on the same day (Sept 22 or the
    eve of the election), using only what was known then.
  - Same races: each head-to-head uses only the races both sides forecast.
  - One shared score for ratings and probabilities alike: "winner called" = share of races
    where the favored side won, with a Toss-up counting as half (a coin flip gets half right).
    Also reported: how many races each side left as Toss-up, and for probabilistic forecasts
    (ours, FiveThirtyEight) the Brier score (mean squared error of the win probability; lower
    is better, 0.25 = always saying 50%).
  - Our probabilities become ratings with the site's bands: Safe >95%, Likely 80-95%,
    Lean 60-80%, Toss-up 40-60%.

Outputs: midterms_2026/outputs/outlet_comparison.csv (one row per outlet x date x race set)
         midterms_2026/outputs/outlet_comparison_races.csv (race-level, for the site)
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "midterms_2026" / "outputs"
PROC = ROOT / "data" / "processed"
FTE = ROOT / "data" / "raw" / "fte_forecasts"
ELECTION = {2018: "2018-11-06", 2020: "2020-11-03", 2022: "2022-11-08", 2024: "2024-11-05"}
REGULAR_CLASS = {2018: 1, 2020: 2, 2022: 3, 2024: 1}   # the Senate class up in a regular election that year
FTE_FLAGSHIP = {2018: "classic", 2020: "_deluxe", 2022: "_deluxe"}  # the version 538 featured
SIDE = {"Safe D": 1, "Likely D": 1, "Lean D": 1, "Toss-up": 0, "Lean R": -1, "Likely R": -1, "Safe R": -1}
KEY = ["year", "office", "state_po", "district", "special"]


def our_rating(p: float) -> str:
    q = max(p, 1 - p)
    side = "D" if p >= 0.5 else "R"
    return "Toss-up" if q < 0.6 else f"{'Safe' if q > 0.95 else 'Likely' if q >= 0.8 else 'Lean'} {side}"


def asof_date(year: int, label: str) -> pd.Timestamp:
    return pd.Timestamp(f"{year}-09-22") if label == "sep22" else pd.Timestamp(ELECTION[year]) - pd.Timedelta(days=1)


def ours() -> pd.DataFrame:
    frames = []
    for label, f in (("sep22", "backtest_race_forecasts.csv"), ("eve", "backtest_race_forecasts_eve.csv")):
        d = pd.read_csv(OUT / f)
        d["asof"] = label
        frames.append(d[KEY + ["asof", "p_dem", "actual"]])
    d = pd.concat(frames, ignore_index=True)
    d["special"] = d["special"].fillna(False).astype(bool)
    d["district"] = d["district"].astype(int)
    return d


def fte() -> pd.DataFrame:
    """FiveThirtyEight's flagship-model P(Democrat wins) per race on each comparison date."""
    rows = []
    # 2018: one row per candidate
    for office, f in (("HOUSE", "2018_house_district_forecast.csv"), ("SEN", "2018_senate_seat_forecast.csv"),
                      ("GOV", "2018_governor_state_forecast.csv")):
        d = pd.read_csv(FTE / f, low_memory=False)
        d = d[d["model"] == FTE_FLAGSHIP[2018]]
        d["date"] = pd.to_datetime(d["forecastdate"])
        for label in ("sep22", "eve"):
            day = asof_date(2018, label)
            x = d[d["date"] <= day]
            if x.empty:
                continue
            x = x[x["date"] == x["date"].max()]
            if office == "SEN":
                x = x.assign(special=x["special"].astype(bool), district=0)
            else:
                x = x.assign(special=False, district=pd.to_numeric(x.get("district", 0), errors="coerce").fillna(0).astype(int))
            g = x.groupby(["state", "district", "special"])
            pd_ = g.apply(lambda s: s.loc[s["party"] == "D", "win_probability"].sum(), include_groups=False)
            for (st, dist, sp), p in pd_.items():
                rows.append({"year": 2018, "office": office, "state_po": st, "district": int(dist), "special": bool(sp),
                             "asof": label, "p_dem": float(p)})
    # 2020 / 2022: one row per race, district codes like "AZ-1", "WI-S3", "AZ-G1"
    for year, office, f in ((2020, "HOUSE", "2020_house_district_toplines_2020.csv"),
                            (2020, "SEN", "2020_senate_state_toplines_2020.csv"),
                            (2022, "HOUSE", "2022_house_district_toplines_2022.csv"),
                            (2022, "SEN", "2022_senate_state_toplines_2022.csv"),
                            (2022, "GOV", "2022_governor_state_toplines_2022.csv")):
        d = pd.read_csv(FTE / f, low_memory=False, usecols=lambda c: c in ("district", "forecastdate", "expression", "winner_Dparty"))
        d = d[d["expression"] == FTE_FLAGSHIP[year]]
        d["date"] = pd.to_datetime(d["forecastdate"], format="%m/%d/%y")
        for label in ("sep22", "eve"):
            day = asof_date(year, label)
            x = d[d["date"] <= day]
            if x.empty:
                continue
            x = x[x["date"] == x["date"].max()]
            for _, r in x.iterrows():
                st, code = r["district"].split("-", 1)
                if office == "HOUSE":
                    dist, sp = (int(code) if code.isdigit() else 0), False
                elif office == "SEN":
                    dist, sp = 0, int(code.lstrip("S")) != REGULAR_CLASS[year]
                else:
                    dist, sp = 0, False
                rows.append({"year": year, "office": office, "state_po": st, "district": dist, "special": sp,
                             "asof": label, "p_dem": float(r["winner_Dparty"])})
    f = pd.DataFrame(rows)
    # at-large House seats: 538 numbers them 1, our data uses 0
    return f


def ratings() -> pd.DataFrame:
    r = pd.read_csv(PROC / "outlet_ratings.csv")
    r = r[r["asof"].isin(["sep22", "eve"])].copy()
    r["special"] = r["special"].astype(bool)
    r["district"] = r["district"].astype(int)
    return r


def score_pair(us: pd.DataFrame, them: pd.DataFrame, name: str, prob: bool) -> dict:
    """`us`/`them`: same races (aligned), columns p_dem/rating, actual."""
    won_d = (us["actual"] > 0).to_numpy()
    def called(ratings):
        side = ratings.map(SIDE).to_numpy()
        return np.where(side == 0, 0.5, (side == 1) == won_d).mean()
    out = {"outlet": name, "races": len(us),
           "ours_called": called(us["rating"]), "theirs_called": called(them["rating"]),
           "ours_tossups": int((us["rating"] == "Toss-up").sum()), "theirs_tossups": int((them["rating"] == "Toss-up").sum()),
           "ours_brier": float(np.mean((us["p_dem"] - won_d) ** 2))}
    if prob:
        out["theirs_brier"] = float(np.mean((them["p_dem"] - won_d) ** 2))
    return out


def main() -> None:
    us = ours()
    us["rating"] = us["p_dem"].map(our_rating)
    at_large = us.groupby(["year", "state_po"])["district"].transform("max") == 0
    f = fte()
    # 538 numbers at-large seats 1; map to 0 where our data says the state has one seat
    single = set(map(tuple, us.loc[(us.office == "HOUSE") & at_large, ["year", "state_po"]].drop_duplicates().to_numpy()))
    f.loc[(f.office == "HOUSE") & f.apply(lambda r: (r.year, r.state_po) in single, axis=1), "district"] = 0
    f["rating"] = f["p_dem"].map(our_rating)
    f["outlet"] = "FiveThirtyEight (model)"
    rt = ratings()
    rt = rt[rt["outlet"] != "FiveThirtyEight"]   # use 538's actual probabilities instead of its category labels

    results, race_rows = [], []
    for label in ("sep22", "eve"):
        u = us[us.asof == label]
        sources = [("FiveThirtyEight (model)", f[f.asof == label], True)]
        for name, g in rt[rt.asof == label].groupby("outlet"):
            sources.append((name, g, False))
        for name, g, prob in sources:
            m = u.merge(g[KEY + ["rating"] + (["p_dem"] if prob else [])], on=KEY, suffixes=("", "_them"))
            if len(m) < 20:
                continue
            them = pd.DataFrame({"rating": m["rating_them"], "p_dem": m["p_dem_them"] if prob else np.nan})
            for subset, mask in (("all", np.ones(len(m), bool)),
                                 ("competitive", ((m["rating"] != "Safe D") & (m["rating"] != "Safe R")) |
                                                 (~m["rating_them"].isin(["Safe D", "Safe R"])))):
                if mask.sum() < 5:
                    continue
                r = score_pair(m[mask].reset_index(drop=True), them[mask].reset_index(drop=True), name, prob)
                r.update({"asof": label, "subset": subset, "years": ",".join(map(str, sorted(m.loc[mask, "year"].unique()))),
                          "offices": ",".join(sorted(m.loc[mask, "office"].unique()))})
                results.append(r)
            race_rows.append(m.assign(outlet=name, asof=label)[KEY + ["asof", "outlet", "p_dem", "rating", "rating_them", "actual"]])
    res = pd.DataFrame(results)
    res.to_csv(OUT / "outlet_comparison.csv", index=False)
    pd.concat(race_rows).to_csv(OUT / "outlet_comparison_races.csv", index=False)
    pd.set_option("display.width", 250)
    for label in ("sep22", "eve"):
        x = res[(res.asof == label)].sort_values(["subset", "races"], ascending=[True, False])
        print(f"\n=== As of {'Sept 22' if label == 'sep22' else 'Election Eve'} ===")
        print(x[["subset", "outlet", "races", "years", "offices", "ours_called", "theirs_called", "ours_tossups",
                 "theirs_tossups", "ours_brier", "theirs_brier"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
