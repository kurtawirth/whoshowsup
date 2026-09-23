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
