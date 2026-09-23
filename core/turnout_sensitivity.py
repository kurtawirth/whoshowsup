"""County turnout sensitivity: how strongly each county amplifies turnout waves.

For each party P and county c we look at every pair of consecutive elections
(president -> president, president -> midterm, midterm -> president) and
compute the change in that party's turnout rate:

    y[c, t] = change in log(P votes / eligible citizens) in county c
    x[s, t] = the same change for the county's whole state

Then, per county, regress y on x:

    y[c, t] = alpha_c + beta_c * x[s, t] + e[c, t]

  beta_c     "wave sensitivity": beta > 1 means the county swings harder than
             its state when that party's turnout surges or collapses.
  (also computed for TOTAL votes: party-blind turnout, which voters switching
  sides cannot move -- a check on how much of a party beta is really persuasion)
  resid_sd_c residual volatility: how noisy the county is beyond what the
             statewide wave explains. Used later to widen uncertainty.

With only ~8 transitions per county, raw betas are noisy, so we apply
empirical-Bayes shrinkage: each beta is pulled toward the average (1.0 by
construction) in proportion to how uncertain it is. Small counties with
erratic data get pulled in a lot; big counties with clean data barely move.

Eligible citizens = Census CVAP (citizen voting-age population) 5-year
estimates. A release ending in year Y is centered on Y-2, so election year E
uses the release ending E+2 (2024 is extrapolated from the last two releases).
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"

ELECTIONS = [2008, 2012, 2016, 2018, 2020, 2022, 2024]
MIN_TRANSITIONS = 4


def load_cvap() -> pd.DataFrame:
    """County CVAP by election year (county_fips, year, cvap, name)."""
    rows = []
    for f in sorted((RAW / "cvap").glob("county_cvap_*.csv")):
        end = int(f.stem.split("_")[-1])
        df = pd.read_csv(f, encoding="latin-1").rename(columns=str.lower)
        df = df[df["lnnumber"] == 1]  # the "Total" line (all races)
        rows.append(pd.DataFrame({
            "county_fips": df["geoid"].str[-5:].astype(int),
            "year": end - 2,
            "cvap": df["cvap_est"],
            "name": df["geoname"],
        }))
    cv = pd.concat(rows)
    # Extrapolate 2024 from the 2020 -> 2022 growth rate.
    wide = cv.pivot_table(index="county_fips", columns="year", values="cvap")
    extra = (wide[2022] * wide[2022] / wide[2020]).rename("cvap").reset_index().assign(year=2024)
    names = cv.drop_duplicates("county_fips", keep="last")[["county_fips", "name"]]
    return pd.concat([cv.drop(columns="name"), extra]).merge(names, on="county_fips")


def top_of_ticket(results: pd.DataFrame) -> pd.DataFrame:
    """One race per county-year: President in presidential years; otherwise the
    statewide race with the most votes (Senate or Governor)."""
    r = results[~results["special"] & results["year"].isin(ELECTIONS)]
    r = r[(r["office"] == "PRES") | ~r["year"].isin([2008, 2012, 2016, 2020, 2024])]
    g = r.groupby(["year", "state_po", "office"])
    r = r.assign(state_tot=g["total"].transform("sum"),
                 dem_share=g["dem"].transform("sum") / g["total"].transform("sum"),
                 rep_share=g["rep"].transform("sum") / g["total"].transform("sum"))
    # A race without a real Democrat or Republican (CA 2018 D-vs-D Senate, UT 2022
    # McMullin, VT Sanders) would look like a turnout collapse for the missing party.
    r = r[(r["dem_share"] > 0.15) & (r["rep_share"] > 0.15)]
    r = r.sort_values("state_tot", ascending=False)
    return r.drop_duplicates(["year", "county_fips"])[["year", "state_po", "county_fips", "office", "dem", "rep", "total"]]


def transitions(df: pd.DataFrame, party: str) -> pd.DataFrame:
    """Consecutive-election changes in log(party votes / CVAP), county and state."""
    df = df.sort_values(["county_fips", "year"]).copy()
    df["rate"] = np.log(df[party].clip(lower=1) / df["cvap"])
    st = df.groupby(["state_po", "year"])[[party, "cvap"]].sum()
    st["st_rate"] = np.log(st[party] / st["cvap"])
    df = df.merge(st["st_rate"].reset_index(), on=["state_po", "year"])
    df = df.sort_values(["county_fips", "year"])
    g = df.groupby("county_fips")
    df["prev_year"] = g["year"].shift()
    df["y"] = df["rate"] - g["rate"].shift()
    df["x"] = df["st_rate"] - g["st_rate"].shift()
    # Only adjacent elections in our calendar (a missing midterm must not create a 4-year jump).
    nxt = dict(zip(ELECTIONS[:-1], ELECTIONS[1:]))
    df = df[df["prev_year"].map(nxt) == df["year"]]
    return df.dropna(subset=["x", "y"])


def fit_county(g: pd.DataFrame) -> pd.Series:
    x, y = g["x"].to_numpy(), g["y"].to_numpy()
    n = len(x)
    xc = x - x.mean()
    sxx = (xc ** 2).sum()
    beta = (xc * (y - y.mean())).sum() / sxx
    resid = y - y.mean() - beta * xc
    s2 = (resid ** 2).sum() / max(n - 2, 1)
    return pd.Series({"n": n, "beta_raw": beta, "se": np.sqrt(s2 / sxx), "resid_sd": np.sqrt(s2)})


def shrink(est: pd.DataFrame) -> pd.DataFrame:
    """Empirical-Bayes shrinkage of beta toward the (weighted) mean."""
    w = 1 / est["se"] ** 2
    mu = np.average(est["beta_raw"], weights=w)
    # Method of moments: true between-county variance = observed variance - average noise.
    tau2 = max(est["beta_raw"].var() - (est["se"] ** 2).median(), 1e-4)
    k = tau2 / (tau2 + est["se"] ** 2)  # 1 = trust the county's own data, 0 = use the mean
    return est.assign(beta=mu + k * (est["beta_raw"] - mu), shrink_weight=k, beta_mean=mu, tau=np.sqrt(tau2))


def county_panel() -> pd.DataFrame:
    res = pd.read_parquet(PROC / "county_results.parquet")
    return top_of_ticket(res).merge(load_cvap(), on=["county_fips", "year"], how="inner")


def compute(df: pd.DataFrame, exclude_years: tuple = (), min_transitions: int = MIN_TRANSITIONS) -> pd.DataFrame:
    """Betas and residual volatility per county. `exclude_years` drops every
    transition into or out of those elections -- used for honest backtests, so
    the election being predicted never informs the betas."""
    out = []
    # "total" = all votes cast: pure turnout, immune to voters switching parties.
    for party in ("dem", "rep", "total"):
        tr = transitions(df, party)
        tr = tr[~tr["year"].isin(exclude_years) & ~tr["prev_year"].isin(exclude_years)]
        est = tr.groupby("county_fips").apply(fit_county, include_groups=False)
        est = shrink(est[est["n"] >= min_transitions].dropna())
        out.append(est.add_prefix(f"{party}_"))
    sens = pd.concat(out, axis=1).reset_index()
    names = df.drop_duplicates("county_fips")[["county_fips", "state_po", "name"]]
    return names.merge(sens, on="county_fips")


def main() -> None:
    df = county_panel()
    sens = compute(df)
    sens.to_parquet(PROC / "county_turnout_sensitivity.parquet", index=False)

    pd.set_option("display.width", 200)
    for p in ("dem", "rep", "total"):
        print(f"\n{p.upper()}: mean beta {sens[f'{p}_beta_mean'].iloc[0]:.2f}, "
              f"between-county sd (tau) {sens[f'{p}_tau'].iloc[0]:.2f}, counties {sens[f'{p}_beta'].notna().sum()}")
        print(sens[f"{p}_beta"].describe(percentiles=[.05, .25, .5, .75, .95]).round(2).to_string())


if __name__ == "__main__":
    main()
