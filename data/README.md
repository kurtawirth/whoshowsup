# Data sources

Raw files live in `data/raw/` and are not committed (size, and some sources ask users to register).
To rebuild from scratch, place these files as shown.

| Path | Source | Notes |
|---|---|---|
| `raw/medsl/house_1976_2024.tab` | [MIT Election Lab – U.S. House 1976–2024](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/IG0UN2) | Requires Dataverse guestbook form (manual download) |
| `raw/medsl/countypres_2000-2024.csv` | [MIT Election Lab – County Presidential 2000–2024](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/VOQCHQ) | Requires guestbook form (manual download) |
| `raw/medsl/senate_1976_2024.csv` | [MIT Election Lab – U.S. Senate 1976–2024](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/PEJ5QU) | State level; used for validation |
| `raw/medsl/president_1976_2024.csv` | [MIT Election Lab – U.S. President 1976–2024](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/42MVDX) | State level; used for validation |
| `raw/medsl_2018/*.zip` | [MEDSL/2018-elections-official](https://github.com/MEDSL/2018-elections-official) | Precinct returns: `SENATE/`, `STATE/` |
| `raw/medsl_2022/*.zip` | [MEDSL/2022-elections-official](https://github.com/MEDSL/2022-elections-official) | Precinct returns, `individual_states/` |
| `raw/medsl_2024/2024-senate-county.csv` | [MEDSL/2024-elections-official](https://github.com/MEDSL/2024-elections-official) | County Senate returns |
| `raw/wikipedia/*.html` | Wikipedia race pages | Cached automatically by `core/wiki_county_patch.py` |
| `raw/cvap/county_cvap_*.csv` | [Census CVAP special tabulation](https://www.census.gov/programs-surveys/decennial-census/about/voting-rights/cvap.html), 5-year releases 2006-2010 ... 2020-2024 | County file extracted from each release zip |
| `raw/downballot/pres_by_cd_2026_lines.csv` | [The Downballot: presidential results by congressional district](https://www.the-downballot.com/p/the-downballots-calculations-of-presidential) (2026 lines, 2024 + unchanged-line 2020) | Google Sheet CSV export; cite as The Downballot |
| `raw/wikipedia/2026_*.html` | Wikipedia 2026 House/Senate/gubernatorial overview pages | Candidate + incumbent tables only; ratings tables ignored by design |
| `raw/votehub/polls_all.json` | [VoteHub open polling API](https://api.votehub.com/polls) | Race, generic-ballot, approval polls; refreshed with `build_polls.py --refresh` |
| `raw/wikipedia/2026_*election*.html` | Wikipedia 2026 race pages | Poll tables; refreshed with `scrape_wikipedia_polls.py --refresh` |
| `raw/fte/raw_polls.csv` | [FiveThirtyEight pollster-ratings raw polls](https://github.com/fivethirtyeight/data/tree/master/pollster-ratings) | 1998-2022 polls matched to results, with partisan flags. Raw polls only -- 538 grades are not used |
| `raw/fte/generic_ballot_polls_historical.csv`, `president_approval_polls*.csv`, `governor_polls_historical.csv` | 538 poll lists via Internet Archive snapshots (projects.fivethirtyeight.com/polls-page/data/) | Generic ballot 2018-2024; approval Trump I + Biden |
| `raw/downballot/1l7W130t_429358610.csv` | [The Downballot data hub](https://www.the-downballot.com/p/data): Daily Kos Elections 2008 presidential results for districts used in 2006-2010 | Google Sheet CSV export; backtest 2010 and House personal vote 2008-2010 |
| `raw/downballot/1zLNAuRq_0.csv` | Same hub: 2008, 2012 & 2016 presidential results for districts used in 2018 | Pennsylvania's 2018 court map in the 2018/2020 backtests |
| `raw/fec_results/federalelectionsYYYY.xls(x)` | [FEC Federal Elections results books](https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/) 2006-2022 | primary and general votes by candidate (core/primary_turnout.py) |
| `raw/fte/senate_polls_historical.csv`, `house_polls_historical.csv`, `senate_polls.csv`, `house_polls.csv` | 538 poll lists via Internet Archive snapshots (projects.fivethirtyeight.com/polls-page/data/, Nov 2024-Mar 2025) | full-season race polls 2018-2024 (core/poll_archive.py) |
| `raw/wikipedia_governors/`, `raw/wikipedia_2024/` | Wikipedia yearly governor summary pages; 2024 race pages | core/governor_results.py, core/polls_2024.py |
| `processed/ces_vote_mode.csv` | Cooperative Election Study Common Content 2008-2024 (Harvard Dataverse, CC0), yearly files | the few columns used (year, weight, voting method, party, House vote); the 2.1 GB yearly downloads were deleted after extraction (core/early_vote_history.py) |
| `raw/civicapi/` | [civicAPI](https://civicapi.org) early-vote API (free, attribution) | 2026 early and absentee ballots by state (core/early_vote.py) |
| `raw/spae/` | MIT Survey of the Performance of American Elections (Harvard Dataverse, CC0) | not used since the CES replaced it for the early-vote chart |
| `raw/downballot/specials_YYYY.csv`, `special_elections_index_1989.csv` | [The Downballot data hub](https://www.the-downballot.com/p/data) special-election sheets | 2017-2022, 2025-2026; index from 1989 |
| `raw/ddhq/generic-ballot.html` | [Decision Desk HQ public generic-ballot page](https://polls.decisiondeskhq.com/averages/generic-ballot/national/lv-rv-adults) | Primary generic-ballot source (VoteHub stopped adding national polls after June 2026) |
| `raw/app_approval/g_*.csv` | [American Presidency Project](https://www.presidency.ucsb.edu/statistics/data/presidential-job-approval) Gallup approval sheets | Truman-Biden |
| `raw/tilegrams/us-congressional-districts-2018.json` | [Pitch Interactive Tilegrams](https://github.com/PitchInteractiveInc/tilegrams) (ISC license) | Base layout for the House hex map (`core/build_hexmap.py`) |
| `raw/census/2024_Gaz_119CDs_national.txt` | [Census 2024 Gazetteer, 119th Congress districts](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html) | District center points for hex placement |
| `raw/county_pres/` | [tonmcg county results](https://github.com/tonmcg/US_County_Level_Election_Results_08-24) | Only used for county-name → FIPS lookup |

## Known data quirks (handled in `core/build_county_results.py`)

- Vote modes reported both split and as TOTAL → per candidate, take max(TOTAL, sum of modes).
- 2022 Louisiana "TOTAL" mode is election-day only → all modes summed.
- Pseudo-candidate rows (over/undervotes, "total votes cast", ballot counters) dropped.
- "COUNTY TOTAL" pseudo-precincts dropped where real precincts exist (Idaho 2022).
- Fusion voting (NY, CT): candidates credited with all ballot lines.
- Party labels rescued from `party_detailed` (ND "Democratic-NPL", WA "GOP").
- Alaska has no counties (reports by legislative district) — handled separately.
- Remaining validation gaps: small (2–3%) total-vote gaps in MA/ME/WY/NY from blanks and
  write-ins; Maine 2004 ~7% short (missing towns); two-party votes match exactly.

## Attribution

Race, approval, and generic-ballot poll data from VoteHub (https://votehub.com), licensed CC BY 4.0.
Generic-ballot polls from Decision Desk HQ. Presidential results by district from The Downballot.
