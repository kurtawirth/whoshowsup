---
title: How the forecast works
---

```js
import {tokens, pct, margin, date} from "./components/wsu.js";
const top = FileAttachment("data/topline.json").json();
const track = FileAttachment("data/track_record.json").json();
```

```js
const t = (dark, tokens());
const style = {background: "transparent", color: t["ink-3"], fontSize: "12px"};
```

<p class="kicker">Methodology</p>

# How Who Shows Up works, and how well it would have done

<p class="dek">The short version: estimate the national mood, carry it down to every race, update each race with its polls, and simulate the whole election 20,000 times with errors that move together, the way real polling misses do. Every step was tested against elections the model had not seen.</p>

## 1. The national mood

The model first estimates the national House popular vote from three independent readings, each corrected for how it has historically missed and weighted by how accurate it has been:

- **Special elections.** Our main turnout signal. In low-turnout specials, the party whose voters are more motivated beats the district's usual lean. We add the cycle's average overperformance to the last presidential margin. Historically this overstates Democrats by about three points, so the model subtracts that.
- **The generic ballot.** Polls of which party voters want in Congress, read in two-party terms (undecided voters don't vote). In late September these polls have overstated Democrats in 14 of the last 15 elections, by 3.4 points on average, and the model corrects for it.
- **Fundamentals.** The president's approval rating and the midterm penalty, fit on every election since 1978.

Each reading is a small Bayesian model: it learns from history not just a best estimate of its bias but a range of plausible values, so its uncertainty flows into the forecast.

## 2. From the nation to each race

A district's starting point is its 2024 presidential result under the new 2026 lines. The national shift is applied two ways, and each simulation blends them:

- **Turnout-shaped:** each party's vote in the district rises or falls in proportion to its vote nationally, the way an enthusiasm gap works.
- **Persuasion-shaped:** every district's margin moves by the same amount, the way voters changing sides works.

Across eight past elections, the turnout-shaped version explained about 65% of the pattern on average, but it swung from 0% to 100% depending on the year. So each simulation draws its own mix, and our uncertainty about what kind of year 2026 will be flows into the odds.

Then come adjustments measured from past races:

- **Personal vote:** incumbents keep part of how far they outran or trailed expectations last time: about half for House members, 43% for senators, 63% for governors. A House member's first re-election gets about 3.6 points more. That is why Vermont's Phil Scott, a Republican, is favored in a very Democratic state, and why a Republican who trailed Trump in their own district in 2024 is more exposed than one who ran ahead of him. Where we can't find the incumbent's last race (for example, they ran unopposed), they get the average House incumbency edge of about 2.3 points.
- **Candidate experience:** each nominee is coded from their record (senator or governor; U.S. representative, statewide office or mayor; state legislator or local office; none). We coded every nominee back to 2018 and tested what the gap is worth. In governors' races it matters when the race is close, up to about eight points. In House and Senate races it added nothing once the district's lean, the national mood, incumbency and campaign money were known: experienced challengers tend to run in the years and places that already favor them, and they raise the money to show for it.
- **Campaign money:** each side's money as of its latest report to the Federal Election Commission: cash in the bank plus everything spent this year. It counts only in close races, where a big fundraising edge is worth up to about five points in the House and more in the Senate (where polls usually outweigh it). In safe seats it counts for nothing, because incumbents there pile up money regardless. Adding it improved our backtest's accuracy, most of all in Senate races. Governors' races are not in FEC data.
- **Candidate ideology (House):** how far each nominee sits from the middle of their own party, measured from who donates to them (Adam Bonica's DIME scores, which run through 2024, so first-time candidates have none and count as typical for their party). In a close House race, the nominee further out from the center pays for it: a typical gap is worth about a point. It made no reliable difference in Senate races.
- **A close-seat effect:** in all four test elections, Democrats ran about one and a half points ahead of expectations in competitive House districts, even after accounting for money, so the model expects that.

## 3. Polls

Polls are collected every morning from three sources (VoteHub, Wikipedia and Decision Desk HQ), and a poll listed in more than one counts once. When a pollster releases several versions of the same poll, such as likely voters and registered voters, only one counts, preferring likely voters. Each race's polls are averaged in two-party terms. A poll's weight halves every 14 days (the best-performing half-life when we tested 3 to 60 days on past elections). Larger samples and likely-voter polls count a little more. Polls sponsored by a campaign or party are corrected for their measured lean toward the sponsor, about three to five points, and count half as much.

How much a race's polls move it away from its fundamentals depends on how accurate poll averages have historically been at this point in the race. That depends on how many polls there are, and it improves as Election Day nears. A Senate race with 40 polls leans mostly on them. A House district with none runs on fundamentals alone.

## 4. Simulation

Each of the 20,000 simulated elections draws a national environment, a turnout/persuasion mix, a shared error for each state (a polling miss in Wisconsin hits every Wisconsin race), a shared error for each region, and each race's own error. That correlation is why the seat ranges are realistic rather than falsely narrow.

## What the model does not use

No pundit ratings (Cook, Sabato, Inside Elections), no other forecasters' models, and no prediction markets. Markets will be shown alongside the forecast for comparison, never as an input.

## Track record

We rebuilt 2018, 2020, 2022 and 2024 exactly as they looked on September 22 of each year, using only what was known then, and ran the same model. Each year's national estimate was fit without that year, and the close-seat effect was estimated only from the other three years.

```js
const scores = Object.fromEntries((track.backtest_scores ?? []).map((d) => [d.set, d]));
const all = scores["all"];
display(html`<div class="stat-row">
  <div class="s"><div class="k">Races tested</div><div class="v">${all.races.toLocaleString()}</div></div>
  <div class="s"><div class="k">Winners called correctly</div><div class="v">${(all.correct_calls * 100).toFixed(1)}%</div></div>
  <div class="s"><div class="k">Results inside the 80% range</div><div class="v">${(all.inside_80 * 100).toFixed(0)}%</div></div>
  <div class="s"><div class="k">Brier score (lower is better)</div><div class="v">${all.brier.toFixed(3)}</div></div>
  <div class="s"><div class="k">Using 2024 lean alone</div><div class="v">${all.brier_lean_only.toFixed(3)}</div></div>
</div>`);
```

### When we said X%, did it happen X% of the time?

```js
const cal = (track.backtest_calibration ?? []).map((d) => ({...d}));
display(Plot.plot({
  width: Math.min(width, 620), height: Math.min(width, 620) * 0.8, marginLeft: 48, marginBottom: 44,
  r: {range: [4, 16]},
  x: {domain: [0, 1], tickFormat: "%", label: "Forecast chance of a Democratic win", labelAnchor: "center", labelOffset: 36},
  y: {domain: [0, 1], tickFormat: "%", label: "Share Democrats actually won", grid: true},
  style,
  marks: [
    Plot.line([[0, 0], [1, 1]], {stroke: t.axis}),
    Plot.text([[0.83, 0.93]], {text: () => "Perfectly calibrated", rotate: -38, fill: t["ink-3"], fontSize: 11}),
    Plot.dot(cal, {x: "predicted", y: "actual", r: "races", fill: t.dem, fillOpacity: 0.85, stroke: t.surface, strokeWidth: 2}),
    Plot.tip(cal, Plot.pointer({x: "predicted", y: "actual", title: (d) => `${d.races} races forecast at ${pct(d.predicted)} on average\nDemocrats won ${pct(d.actual)}`}))
  ]
}));
```

<p class="caption">Each circle groups races by their forecast probability; its size reflects how many races are in the group. Points on the diagonal mean the probabilities meant what they said.</p>

### Chamber totals: forecast versus result

```js
const ch = (track.backtest_chambers ?? []).filter((d) => d.races > 0);
const officeName = {HOUSE: "House", SEN: "Senate races", GOV: "Governor races"};
const key = (d) => `${d.year} ${officeName[d.office]}`;
// House totals (~200) and statewide totals (~15) sit on different scales: two panels, not one axis.
const chamberPlot = (rows, w, label) => {
  const lo = Math.min(...rows.map((d) => Math.min(d.p10, d.actual_D))), hi = Math.max(...rows.map((d) => Math.max(d.p90, d.actual_D)));
  const pad = Math.max(2, (hi - lo) * 0.08);
  return Plot.plot({
  width: w, height: 34 * rows.length + 56, marginLeft: 130, marginRight: 20, marginBottom: 44,
  x: {label, grid: true, domain: [lo - pad, hi + pad], labelAnchor: "center", labelOffset: 36},
  y: {domain: rows.map(key), label: null},
  style,
  marks: [
    Plot.ruleY(rows, {x1: "p10", x2: "p90", y: key, stroke: t.dem, strokeWidth: 8, strokeOpacity: 0.3, strokeLinecap: "round"}),
    Plot.tickX(rows, {x: "pred_median_D", y: key, stroke: t.dem, strokeWidth: 2}),
    Plot.dot(rows, {x: "actual_D", y: key, r: 5, fill: t.ink, stroke: t.surface, strokeWidth: 2}),
    Plot.tip(rows, Plot.pointerY({x: "actual_D", y: key, title: (d) => `${key(d)}
Forecast: ${d.pred_median_D} (80% range ${d.p10}–${d.p90})
Actual: ${d.actual_D}`}))
  ]
  });
};
const half = width >= 800 ? (width - 32) / 2 : width;
display(html`<div class="grid-2">
  <div class="panel"><h3>House</h3>${chamberPlot(ch.filter((d) => d.office === "HOUSE"), half, "Democratic seats among districts modeled")}</div>
  <div class="panel"><h3>Senate and governor races</h3>${chamberPlot(ch.filter((d) => d.office !== "HOUSE"), half, "Democratic wins among races up")}</div>
</div>`);
```

<p class="caption">Shaded bars: the 80% range forecast on September 22. Tick: the forecast median. Dot: what happened. All 12 results landed inside the range. (Some districts are left out in redistricting years; the House rows count only the districts modeled.)</p>

### The national environment, 1996–2024

```js
const nb = (track.national_env_backtest ?? []);
display(Plot.plot({
  width, height: 300, marginLeft: 44,
  x: {type: "band", label: null},
  y: {label: "House popular vote margin", grid: true, tickFormat: (d) => (d === 0 ? "Even" : margin(d).replace(".0", ""))},
  style,
  marks: [
    Plot.ruleY([0], {stroke: t.axis}),
    Plot.ruleX(nb, {x: "year", y1: "p10", y2: "p90", stroke: t.dem, strokeWidth: 10, strokeOpacity: 0.28}),
    Plot.dot(nb, {x: "year", y: "predicted", r: 3, fill: t.dem}),
    Plot.dot(nb, {x: "year", y: "actual", r: 5, fill: t.ink, stroke: t.surface, strokeWidth: 2}),
    Plot.tip(nb, Plot.pointerX({x: "year", y: "actual", title: (d) => `${d.year}\nForecast ${margin(d.predicted)} (80%: ${margin(d.p10)} to ${margin(d.p90)})\nActual ${margin(d.actual)}`}))
  ]
}));
```

<p class="caption">Each year predicted without that year in the training data, as of September 22. Shaded: 80% range. Small dot: forecast. Large dot: result.</p>

## Ideas we tested and dropped

Good models are defined as much by what they leave out. We built a county-level measure of how strongly each place's turnout amplifies national waves, a natural fit for a turnout-first model. On 2018 and 2022 results it did not predict how statewide swings distributed across counties any better than simpler methods, so it is not in the model. The broader turnout idea, shifting each party's vote in proportion rather than moving every margin equally, did pass, and it is.

## Sources

Polls from VoteHub (CC BY 4.0), Decision Desk HQ and Wikipedia. Election results from the MIT Election Data + Science Lab. District-level presidential results and special elections from The Downballot. Historical polls from FiveThirtyEight's public archive. Presidential approval history from the American Presidency Project. Eligible-voter counts from the Census Bureau. The code is public on [GitHub](https://github.com/kurtawirth/whoshowsup).
