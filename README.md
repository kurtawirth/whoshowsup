# politics

A home-built election forecasting model. First target: the **November 3, 2026 U.S. midterms**
(House, Senate, Governors).

## Approach

- **Simulation-based.** Tens of thousands of simulated elections with correlated errors
  (national, regional, demographic), reported as means/medians with intervals.
- **Turnout-first.** A national motivation layer (likely-vs-registered voter gaps, enthusiasm
  crosstabs, special-election overperformance, ...) combined with each district's
  *turnout sensitivity*: its **beta** to national turnout waves, plus **residual volatility**
  that widens its uncertainty.
- **Issue-weighted approval.** Salience-weighted issue approval is tested as a replacement for
  topline presidential approval; the backtest decides.
- **Independent.** No expert ratings or other forecasts as inputs. Prediction markets are shown
  side by side for comparison only.
- **Polls.** Race-level polls where they exist; internal/sponsored polls are included with a
  sponsor-bias correction estimated from historical data and reduced weight.
- **Backtested** on 2018 and 2022.

## Layout

```
core/            shared code: data builders, validation, (soon) model + simulation engine
data/raw/        downloaded source data (not in git; see data/README.md)
data/processed/  cleaned, validated datasets
midterms_2026/   2026-specific polls, models, outputs
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
