# Live odds on election night: how much to trust a race's own partial count

**Question.** On election night the results page turns each race's partial count into a live chance of winning
(`site/src/components/live.js`, `liveOdds` with `partial`). How much should a count that's 10%, 50% or 90% in
move those odds?

**Method** (`calibrate.py`). For the 214 Senate and governor races from 2018 to 2024 we have our model's
election-eve forecast from the leave-one-year-out backtest and the final county-by-county result. We replay each
race's count 30 times: counties report at their own pace (big ones slower), and each county's first-counted ballots
lean away from its final margin by a state-wide early-ballot skew plus its own, fading as it finishes. At 10%, 25%,
50%, 75% and 90% counted we run the page's live-odds math, with county benchmarks built from the previous
presidential result (never the race's own), and score its chance against who won (log loss), on the 53 races our
forecast had between 5% and 95% (the ones people watch).

The count's trust is a noise level, sg = a + b × (share not yet counted) points, on what the count says about the
race's own miss, plus a final leftover noise r. We searched a, b and r, for two versions: races with county results
(Senate, governor: the counted counties against their benchmarks) and races judged on the whole count alone (House).

**What's real and what's assumed.** Real: our forecasts, the final results, and where in each state the forecast
missed, which is what county benchmarks rely on. Assumed: the counting order and the size of the early-ballot skew,
which final results can't show. We ran skews of 3, 6 and 9 points and chose weights that hold up across all three.

**Result** (log loss on competitive races, averaged over the three skews; lower is better):

| | weights | average | worst skew |
|---|---|---|---|
| Forecast alone, ignoring the count | | 0.456 | 0.456 |
| County version, first guess | 1.5 + 6(1−f), r 0.5 | 0.258 | 0.309 |
| **County version, chosen** | **6 + 2(1−f), r 0.5** | **0.254** | **0.288** |
| Whole-count version, first guess | 2 + 10(1−f), r 0 | 0.378 | 0.380 |
| **Whole-count version, chosen** | **0.5 + 6(1−f), r 0.5** | **0.312** | **0.330** |

Using the count roughly halves the error against the morning forecast. The first guess for county races was close;
the whole-count version had been trusting the count too little.

**Calibration** (chosen weights, 6-point skew): when the favorite was given 50-60%, it won 55% (county version) and
58% (whole count); 60-70%: 64%; 70-80%: 72% (both slightly overconfident in this band); 80-90%: 84-88%; 90-95%:
93-96%; 95-99%: 97-99%. By share counted, the favorite's average chance and its win rate stay within about 2 points
of each other, except at 75% counted in the county version (said 94%, won 91%).

**Limits.** House districts have no county results, so the whole-count weights come from treating Senate and
governor counts as if only their totals were known. Real counting quirks (an overnight pause, a late batch of mail
ballots from one county) aren't in the replay. Governors and the shared national shift use the same machinery.
