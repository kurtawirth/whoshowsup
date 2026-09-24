---
title: Governor forecasts
---

```js
import {tokens, pct, margin, date, stateMap, ratingLegend, ratingPill, raceTable, raceLink, miniBar, favoriteText, withSearch, RATINGS, RACE_SORTS} from "./components/wsu.js";
import {seatChart} from "./components/charts.js";
const top = FileAttachment("data/topline.json").json();
const seats = FileAttachment("data/seats.json").json();
const races = FileAttachment("data/races.json").json();
const topo = FileAttachment("data/states-albers-10m.json").json();
const states = FileAttachment("data/states.json").json();
```

```js
const t = (dark, tokens());
const gov = races.filter((r) => r.office === "GOV");
const flipsD = gov.filter((r) => r.incumbent_party === "R" && r.p_dem > 0.5);
const flipsR = gov.filter((r) => r.incumbent_party === "D" && r.p_dem < 0.5);
```

<p class="kicker">Governors · Updated ${date(top.forecast_date)}</p>

# Democrats are on track to win about ${Math.round(top.gov_median)} of 36 governorships

<p class="dek">Thirty-six states elect a governor this year; each party currently holds 18 of those seats. Democrats win between ${Math.round(top.gov_p10)} and ${Math.round(top.gov_p90)} of them in 80% of our simulations. Governors' races are less partisan than federal ones, so popular incumbents like Vermont's Phil Scott can win in states that lean hard the other way.</p>

## The map

```js
display(ratingLegend({noRace: "No governor's race in 2026"}));
display(stateMap(races, topo, states, {office: "GOV", width: Math.min(width, 1000)}));
```

```js
const list = (rs) => rs.sort((a, b) => Math.abs(b.p_dem - 0.5) - Math.abs(a.p_dem - 0.5)).map((r) => `${r.label} (${favoriteText(r)})`).join(", ");
display(html`<p><strong>Seats favored to change parties.</strong> ${flipsD.length ? `Toward Democrats: ${list(flipsD)}.` : "No Republican-held seats currently lean Democratic."} ${flipsR.length ? `Toward Republicans: ${list(flipsR)}.` : "No Democratic-held seats currently lean Republican."}</p>`);
```

## How the 36 races could split

```js
display(seatChart(seats.governor, 19, {width, label: "Governorships", total: 36, height: 230,
  sides: ["Republicans win most races", "Democrats win most races"], tieNeutral: true}));
```

<p class="caption">Every possible outcome across 20,000 simulations; taller bars are more likely. The line marks a majority of this year's 36 races; the gray bar is an 18–18 tie.</p>

## Every governor's race

```js
display(raceTable(withSearch(gov), [
  {key: "label", label: "State", sort: true, render: (r) => raceLink(r)},
  {key: "dem_candidate", label: "Democrat", render: (r) => String(r.dem_candidate ?? "–")},
  {key: "rep_candidate", label: "Republican", render: (r) => String(r.rep_candidate ?? "–").split(";")[0]},
  {key: "incumbent", label: "Current governor", render: (r) => `${r.incumbent} (${r.incumbent_party})${r.inc_side ? "" : ", not running"}`},
  {key: "poll_count", label: "Polls", num: true, sort: true, defaultDir: -1, render: (r) => r.poll_count ?? 0},
  {key: "margin_median", label: "Forecast margin", num: true, sort: true, render: (r) => margin(r.margin_median)},
  {key: "p_dem", label: "Chance", num: true, sort: true, defaultDir: -1, render: (r) => favoriteText(r)},
  {key: "bar", label: "", render: (r) => miniBar(r.p_dem)},
  {key: "rating", label: "Rating", sort: true, sortValue: (r) => RATINGS.indexOf(r.rating), render: (r) => ratingPill(r.rating)}
], {sorts: RACE_SORTS, pageSize: 40}));
```
