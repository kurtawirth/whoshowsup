---
title: House forecast
---

```js
import {tokens, pct, margin, date, hexMap, ratingLegend, ratingPill, raceTable, raceLink, miniBar, favoriteText, withSearch, RATINGS, RACE_SORTS, shareBar, tippingTable, tpPct, powerText} from "./components/wsu.js";
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
const verb = q >= 0.95 ? "are strong favorites" : q >= 0.8 ? "are clear favorites" : q >= 0.6 ? "are favored" : "have a slight edge";
```

<p class="kicker">House of Representatives · Updated ${date(top.forecast_date)}</p>

# ${lead} ${verb} to win the House

<p class="dek">Democrats win a majority in ${pct(top.p_house_d)} of our simulations. The most likely outcome is about ${Math.round(top.house_median)} Democratic seats, with an 80% chance of landing between ${Math.round(top.house_p10)} and ${Math.round(top.house_p90)}. It takes 218 for a majority.${top.p_house_ind != null ? ` Independent Bill Hill wins Alaska's seat in ${pct(top.p_house_ind)} of simulations; he hasn't said which party he would side with, so those wins count for neither party.` : ""}</p>

```js
{
const side = (p) => (p >= 0.5 ? ["Democrats", p] : ["Republicans", 1 - p]);
const [hp, hv] = side(top.p_house_d);
display(shareBar({path: "/house", text: `The Who Shows Up 2026 House forecast: ${hp} win the House in ${pct(hv)} of our simulations, with about ${Math.round(top.house_median)} Democratic seats.`}));
}
```

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

## The tipping point

<p class="caption">In each of 20,000 simulations, we line up the districts the winning party took from its safest to its closest and find the one that gave it the 218th seat. A district's tipping-point chance is how often it was that seat; with 435 seats in play, no single district gets much of it. "Vote's sway" divides that chance by the votes we expect in the district, so a 10× district is one where a vote is ten times as likely to decide control as the average House vote.</p>

```js
{
  const live = house.filter((r) => r.tipping_point > 0);
  const ranked = [...live].sort((a, b) => b.tipping_point - a.tipping_point);
  const top10 = d3.sum(ranked.slice(0, 10), (r) => r.tipping_point);
  const sway = live.filter((r) => r.tipping_point >= 0.01).sort((a, b) => b.voter_power - a.voter_power)[0];
  const gap = top.house_tp_gap;
  display(html`<p>The majority line runs through districts like <strong>${raceLink(ranked[0])}</strong>, ${raceLink(ranked[1])} and ${raceLink(ranked[2])}, each the tipping point in about ${tpPct(ranked[2].tipping_point)} to ${tpPct(ranked[0].tipping_point)} of simulations; the ten likeliest together cover ${pct(top10)}. In the typical simulation the 218th seat runs about ${Math.abs(gap).toFixed(0)} points ${gap < 0 ? "more Republican" : "more Democratic"} than the national House vote, so a national ${margin(top.nat_median)} is closer to ${margin(top.nat_median + gap)} where the majority is decided. A vote counts most in ${raceLink(sway)}, where it is ${powerText(sway.voter_power)} the average House vote to decide control.</p>`);
  display(tippingTable(house, {pageSize: 15}));
}
```

## The most competitive districts

<p class="caption">Districts where each party wins in at least 10% of simulations, closest first.</p>

```js
const competitive = house.filter((r) => r.race_type !== "same_party" && r.p_dem > 0.1 && r.p_dem < 0.9)
  .sort((a, b) => Math.abs(a.p_dem - 0.5) - Math.abs(b.p_dem - 0.5));
const columns = [
  {key: "label", label: "District", sort: true, render: (r) => raceLink(r)},
  {key: "incumbent", label: "Incumbent", render: (r) => (r.inc_side ? `${r.incumbent} (${r.incumbent_party})` : "Open seat")},
  {key: "dem_candidate", label: "Democrat", render: (r) => r.dem_name ?? "–"},
  {key: "rep_candidate", label: "Republican", render: (r) => r.rep_name ?? "–"},
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
