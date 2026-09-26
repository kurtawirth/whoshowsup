# Who Shows Up

**Live forecast: https://whoshowsup.net/**

An independent, turnout-first forecast of the **November 3, 2026 U.S. midterms**: every House,
Senate and governor race, updated every morning. By Kurt Wirth, Ph.D.

## Approach

- **National mood first.** Three readings of the national House vote (special-election
  overperformance, the generic ballot, and approval-plus-midterm fundamentals), each corrected for
  its historical bias and blended by its historical accuracy in a small Bayesian model.
- **Turnout-shaped swing.** Each simulation mixes a turnout-shaped swing (each party's vote scales
  with its national vote) and a persuasion-shaped swing (every margin moves equally); the mix is
  drawn per simulation because it has varied widely across past elections.
- **Race adjustments** measured from past races: incumbency, Senate/governor personal vote,
  candidate experience, and a close-seat effect found in every backtest year.
- **Polls.** Recency-weighted race poll averages; campaign- and party-sponsored polls are corrected
  for their measured lean and counted at half weight. How far polls move a race depends on how
  accurate poll averages have been at that many days out.
- **20,000 simulations** with correlated national, regional and state errors.
- **Independent.** No pundit ratings, other forecasters' models, or prediction markets as inputs.
- **Backtested** on 2018, 2020, 2022 and 2024 as of late September: 95.7% of 1,691 races called,
  84% of results inside the 80% ranges.

The website (`site/`, Observable Framework) is rebuilt and published by GitHub Actions whenever
the daily forecast run pushes new data.

## Layout

```
core/            shared code: data builders, validation, backtests
data/raw/        downloaded source data (not in git; see data/README.md)
data/processed/  cleaned, validated datasets
midterms_2026/   2026-specific polls, models, outputs
site/            the website (Observable Framework); `npm run dev` / `npm run build`
```

## Running the forecast

```bash
.venv/Scripts/python.exe midterms_2026/run_forecast.py                 # refresh all data, forecast as of today
.venv/Scripts/python.exe midterms_2026/run_forecast.py --no-refresh    # rerun the models on cached data (~1 min)
.venv/Scripts/python.exe midterms_2026/run_forecast.py --date 2026-10-15
.venv/Scripts/python.exe midterms_2026/run_forecast.py --push          # also commit + push the results
```

Outputs land in `midterms_2026/outputs/`: `chamber_summary.csv`, `race_forecasts.csv`,
`forecast_history.csv` (one row per forecast date), and a dated snapshot in `history/`.
Warnings at the end flag stale sources, changed race counts, or unusually big moves.

Validation: `midterms_2026/models/national_env.py` (national backtest, 1996-2024) and
`midterms_2026/models/backtest_races.py` (full race model on 2018-2024).

## Setup

```bash
py -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe core/build_county_results.py
.venv/Scripts/python.exe core/validate_county_results.py
```

## Data sources

Polls: VoteHub (CC BY 4.0), Decision Desk HQ, Wikipedia. Results: MIT Election Data + Science Lab.
District-level presidential results and special elections: The Downballot. Historical polls:
FiveThirtyEight's public archive. Approval history: The American Presidency Project. Eligible-voter
counts: U.S. Census Bureau. Hex layout outlines: us-atlas.
