---
title: House forecast
---

```js
import {tokens, pct, margin, date, hexMap, ratingLegend, ratingPill, raceTable, raceLink, miniBar, favoriteText, withSearch, RATINGS, RACE_SORTS} from "./components/wsu.js";
import {seatChart} from "./components/charts.js";
const top = FileAttachment("data/topline.json").json();
const seats = FileAttachment("data/seats.json").json();
const races = FileAttachment("data/races.json").json();
const layout = FileAttachment("data/hexmap.json").json();
```

```js
const t = (dark, tokens());
const house = races.filter((r) => r.office === "HOUSE");
const byRating = d3.rollup(house, (v) => v.length, (r) => r.rating);
const lead = top.p_house_d >= 0.5 ? "Democrats" : "Republicans";
const q = Math.max(top.p_house_d, 1 - top.p_house_d);
const verb = q >= 0.95 ? "are overwhelming favorites" : q >= 0.8 ? "are clear favorites" : q >= 0.6 ? "are favored" : "have a slight edge";
```

<p class="kicker">House of Representatives · Updated ${date(top.forecast_date)}</p>

# ${lead} ${verb} to win the House

<p class="dek">Democrats win a majority in ${pct(top.p_house_d)} of our simulations. The most likely outcome is about ${Math.round(top.house_median)} Democratic seats, with an 80% chance of landing between ${Math.round(top.house_p10)} and ${Math.round(top.house_p90)}. It takes 218 for a majority.</p>

```js
display(html`<div class="stat-row">${RATINGS.map((r) => html`<div class="s"><div class="k">${r}</div><div class="v">${byRating.get(r) ?? 0}</div></div>`)}</div>`);
```

## Every district

<p class="caption">One hexagon per district, grouped by state and placed near its real location. Color shows our forecast. Hover for details and click a district for its full forecast. On a phone, pinch or tap + to zoom in, then tap a district to preview it. Lines are the new 2026 maps, including mid-decade redistricting in ten states.</p>

```js
display(ratingLegend());
display(hexMap(races, layout, {width: Math.min(width, 1100)}));
```

## How many seats each party wins

```js
display(seatChart(seats.house, 218, {width, label: "House", total: 435, height: 250, pControl: top.p_house_d}));
```

## The most competitive districts

<p class="caption">Districts where each party wins in at least 10% of simulations, closest first.</p>

```js
const competitive = house.filter((r) => r.race_type !== "same_party" && r.p_dem > 0.1 && r.p_dem < 0.9)
  .sort((a, b) => Math.abs(a.p_dem - 0.5) - Math.abs(b.p_dem - 0.5));
const columns = [
  {key: "label", label: "District", sort: true, render: (r) => raceLink(r)},
  {key: "incumbent", label: "Incumbent", render: (r) => (r.inc_side ? `${r.incumbent} (${r.incumbent_party})` : "Open seat")},
  {key: "dem_candidate", label: "Democrat", render: (r) => String(r.dem_candidate ?? "–").split(";")[0]},
  {key: "rep_candidate", label: "Republican", render: (r) => String(r.rep_candidate ?? "–").split(";")[0]},
  {key: "pres24", label: "2024 pres.", num: true, sort: true, render: (r) => margin(r.pres24)},
  {key: "margin_median", label: "Forecast margin", num: true, sort: true, render: (r) => margin(r.margin_median)},
  {key: "p_dem", label: "Chance", num: true, sort: true, defaultDir: -1, render: (r) => favoriteText(r)},
  {key: "bar", label: "", render: (r) => miniBar(r.p_dem)}
];
display(raceTable(withSearch(competitive), columns, {search: false, pageSize: 40}));
```

## All 435 districts

```js
const states = [...new Set(house.map((r) => r.state_po))].sort();
display(raceTable(withSearch(house), [
  ...columns.slice(0, 7),
  {key: "rating", label: "Rating", sort: true, sortValue: (r) => RATINGS.indexOf(r.rating), render: (r) => ratingPill(r.rating)}
], {
  sorts: RACE_SORTS,
  filters: [
    {key: "state", label: "All states", options: states.map((s) => [s, s]), test: (r, v) => r.state_po === v},
    {key: "rating", label: "All ratings", options: RATINGS.map((r) => [r, r]), test: (r, v) => r.rating === v},
    {key: "lines", label: "Old and new lines", options: [["new", "Redrawn for 2026"], ["old", "Unchanged lines"]],
      test: (r, v) => (v === "new" ? r.lines_changed : !r.lines_changed)}
  ]
}));
```

<p class="caption">"2024 pres." is the 2024 presidential margin within the district's 2026 lines (The Downballot). Ratings are our own probability bands: Safe above 95%, Likely 80–95%, Lean 60–80%, Toss-up in between.</p>
