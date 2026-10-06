# Does voter registration predict election results? (test run 2026-10-06)

Question (Kurt): do (a) changes in the Democratic-minus-Republican share of registered voters and (b) growth in total
registration predict real results beyond what the Who Shows Up model already uses? Test only; the model is frozen
until after the election and nothing here changed it.

**Bottom line: no for statewide and county-level forecasting. Maybe a little for poll-less House races on
unchanged lines (about 0.2 points of RMSE, mostly California), probably a stand-in for multi-cycle trends.**

## Data (about 138 MB, official sources, in data/raw/registration/, git-ignored)
| Source | What | Size |
|---|---|---|
| Florida Division of Elections | bookclosing by county and congressional district 2016-24, plus the 1994-2014 archive | 0.4 MB + 26.7 MB |
| California Secretary of State | Report of Registration county and congressional files 2010-24, plus the historical PDF | 0.8 MB |
| North Carolina State Board of Elections | 9 general-election voter_stats files | 37.8 MB |
| Iowa open data | monthly registration by county | 2.7 MB |
| Colorado Secretary of State | November statistics 2010-24 | 6.1 MB |
| Pennsylvania Department of State | 8 general-election PDFs | 0.8 MB |
| U.S. EAC (EAVS) | total registration by jurisdiction 2010-24 | 63.6 MB |

2008 registration only for FL, NC, IA. County midterm results from MEDSL precinct files on disk (2018 and 2022
Senate and governor; Iowa's 2018 governor race and California's 2022 Senate race missing).

## Stage 1: counties in six states (1,631 county-cycles, relative to each state's own swing)
- In sample, change in D-R registration share goes with relative swing: b = +0.36 (SE 0.10); 2016+ b = +0.21
  (SE 0.06), R^2 +0.07 beyond previous swing and baseline margin.
- It fades: 2012-16 +0.87, 2016-20 +0.25, 2020-24 +0.12.
- Registration lags the vote: 2016-20 registration change correlates .58 with the PREVIOUS cycle's swing vs .37
  with the same cycle's; 2020-24 .43 vs .32. It does not predict the next swing (b = +0.08, SE 0.09). This is
  ancestral-Democrat re-registration catching up to how people already vote.
- Only late registration carries signal: change in the two years after a presidential election -0.15 (SE 0.18);
  change from the midterm to the eve of the election +0.62 (SE 0.16). What a forecaster would know early carries
  nothing.
- Strict forward test 2020-24: RMSE 3.21 -> 3.15 unweighted, worse vote-weighted; 2016-20 worse.
- Midterm counties (closest to the model's job): b = -0.09 (SE 0.14), R^2 +0.002; cross-year fits slightly worse.

## Stage 2: the model's backtest misses (actual minus forecast)
- Statewide Senate and governor races (n = 47): b = +0.59 (SE 0.40), R^2 0.03; held-out years mixed with 4-11
  races each. Noise.
- House districts on unchanged lines in CA, CO, FL (n = 333, two-thirds CA): a 1-point relative registration shift
  goes with the model missing ~0.9 points toward that party (SE 0.21); +0.77 (SE 0.19) controlling for lean,
  incumbency and state-year. Held-out RMSE change: 2014 +0.12, 2016 -0.21, 2018 -0.30, 2020 -0.12, 2024 -0.24
  (about -0.2 points, ~3%, 2018+). By state: CA +1.0; FL +0.5 (SE 0.35), not clear.
- Given Stage 1, probably a proxy for a multi-cycle trend rather than an independent signal.

## Stage 3: total registration growth (EAVS, ~2,900 counties per cycle)
- Turnout: same-window growth predicts turnout-rate change (b = +0.35), largely mechanical (EAVS counts as of the
  election; shared CVAP denominator). Growth known two years early predicts nothing (b = +0.02).
- Swing: about 0 in every version.

## If worth revisiting after the election
1. Test whether a two-election presidential trend term on the same district lines absorbs the House effect.
2. Score 2026 FL, CA and CO districts whose lines match the registration reports.
3. Adopt nothing unless the effect holds with the same sign and size (~0.8 points of margin per point of
   registration shift), and only with Kurt's approval.

Code: build_registration.py, build_midterm_county.py, common.py, stage1_county.py, stage1b_midterm.py,
stage2_race.py, stage3_eavs.py; outputs stage*_results.txt and the derived CSVs in this folder.
