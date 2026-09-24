---
title: The national picture
---

```js
import {tokens, pct, margin, date, shortDate, tip} from "./components/wsu.js";
const top = FileAttachment("data/topline.json").json();
const national = FileAttachment("data/national.json").json();
```

```js
const t = (dark, tokens());
const env = national.env;
const reads = national.reads;
const readInfo = {
  fundamentals: ["Fundamentals", "The president's approval rating and the midterm penalty the president's party almost always pays."],
  generic: ["Generic ballot", "Polls asking which party voters want in Congress, corrected for their long history of overstating Democrats in September."],
  specials: ["Special elections", "How much Democrats have beaten the usual partisan lean in 100+ special elections this cycle: our main turnout signal."]
};
const style = {background: "transparent", color: t["ink-3"], fontSize: "12px"};
```

<p class="kicker">The national environment · Updated ${date(top.forecast_date)}</p>

# ${env.median >= 0.5 ? `Expect Democrats to win the House popular vote by about ${Math.round(env.median)} points` : env.median <= -0.5 ? `Expect Republicans to win the House popular vote by about ${Math.round(-env.median)} points` : "The national House vote looks roughly even"}

<p class="dek">Before forecasting any single race, the model estimates the national mood: how the House popular vote will split nationwide. Our estimate is ${margin(env.median)}, with an 80% chance of falling between ${margin(env.p10)} and ${margin(env.p90)}. For comparison, Democrats won it by 8.7 points in the 2018 wave and lost it by 2.5 in 2024.</p>

## Three readings, one estimate

<p class="caption">Each reading is corrected for how it has missed in past elections, then weighted by how accurate it has been. The bars show each reading's typical historical miss.</p>

```js
const readRows = reads.map((r) => ({...r, name: readInfo[r.read][0], lo: r.dem_margin - 1.28 * r.noise_sd, hi: r.dem_margin + 1.28 * r.noise_sd}));
readRows.push({name: "Combined estimate", dem_margin: env.median, lo: env.p10, hi: env.p90, weight: 1, combined: true});
display(Plot.plot({
  width, height: 60 * readRows.length + 50, marginLeft: 150, marginRight: 30,
  x: {label: "House popular vote margin", grid: true, tickFormat: (d) => (d === 0 ? "Even" : margin(d).replace(".0", ""))},
  y: {domain: readRows.map((d) => d.name), label: null},
  style,
  marks: [
    Plot.ruleX([0], {stroke: t.axis}),
    Plot.ruleY(readRows, {x1: "lo", x2: "hi", y: "name", stroke: (d) => (d.combined ? t.ink : t["ink-3"]), strokeWidth: (d) => (d.combined ? 4 : 2), strokeLinecap: "round"}),
    Plot.dot(readRows.filter((d) => !d.combined), {x: "dem_margin", y: "name", r: 6, fill: t.dem, stroke: t.surface, strokeWidth: 2}),
    Plot.dot(readRows.filter((d) => d.combined), {x: "dem_margin", y: "name", r: 8, fill: t.ink, stroke: t.surface, strokeWidth: 2}),
    Plot.text(readRows, {x: "dem_margin", y: "name", dy: -16, text: (d) => `${margin(d.dem_margin)}${d.combined ? "" : ` · ${Math.round(d.weight * 100)}% weight`}`, fill: t.ink, fontWeight: 600}),
    Plot.tip(readRows, Plot.pointerY({x: "dem_margin", y: "name", title: (d) => `${d.name}\n${margin(d.dem_margin)}\n80% range: ${margin(d.lo)} to ${margin(d.hi)}`}))
  ]
}));
display(html`<div class="grid-2" style="margin-top:8px">${reads.map((r) => html`<div class="panel"><h3>${readInfo[r.read][0]}</h3><p style="font-size:16px">${readInfo[r.read][1]}</p></div>`)}</div>`);
```

## The generic ballot

<p class="caption">Each dot is a poll, shown as the two-party margin (undecided voters set aside). The line is the average the model uses, with each poll's weight halving every two weeks. The model then subtracts about three points, the amount September generic-ballot polls have overstated Democrats in 14 of the last 15 elections.</p>

```js
const gen = national.generic.map((d) => ({...d, date: new Date(`${d.end_date}T12:00:00`)})).filter((d) => d.margin != null);
const days = d3.utcDays(d3.min(gen, (d) => d.date), d3.max(gen, (d) => d.date), 3);
const trend = days.map((day) => {
  let w = 0, s = 0;
  for (const p of gen) { const age = (day - p.date) / 864e5; if (age < 0 || age > 90) continue; const wi = Math.pow(0.5, age / 14); w += wi; s += wi * p.margin; }
  return {date: day, margin: s / w};
});
display(Plot.plot({
  width, height: 320, marginLeft: 44,
  x: {label: null, type: "utc"},
  y: {label: "Democratic lead (two-party)", grid: true, tickFormat: (d) => (d === 0 ? "Even" : margin(d).replace(".0", ""))},
  style,
  marks: [
    Plot.ruleY([0], {stroke: t.axis}),
    Plot.dot(gen, {x: "date", y: "margin", r: 3, fill: t.dem, fillOpacity: 0.28}),
    Plot.line(trend, {x: "date", y: "margin", stroke: t.dem, strokeWidth: 2.5, curve: "monotone-x"}),
    Plot.text(trend.slice(-1), {x: "date", y: "margin", text: (d) => margin(d.margin), dx: 8, textAnchor: "start", fill: t.ink, fontWeight: 700}),
    Plot.tip(gen, Plot.pointer({x: "date", y: "margin", title: (d) => `${d.pollster}\n${date(d.end_date)} · ${String(d.population ?? "").toUpperCase()}\nD ${d.dem_pct} – R ${d.rep_pct} (${margin(d.margin)} two-party)`}))
  ]
}));
```

## Special elections: the turnout signal

<p class="caption">Every special election contested by both parties since 2017. Each dot shows how much better (up) or worse (down) the Democrat did than the district's last presidential result. These low-turnout races reveal which party's voters are more motivated.</p>

```js
const spec = national.specials.map((d) => ({...d, dt: new Date(`${d.date}T12:00:00`)}));
const cycles = [["2017–18", 2017, 2018], ["2019–20", 2019, 2020], ["2021–22", 2021, 2022], ["2025–26", 2025, 2026]];
const cycleMeans = cycles.map(([label, a, b]) => {
  const xs = spec.filter((d) => d.year >= a && d.year <= b);
  return {label, mean: d3.mean(xs, (d) => d.overperformance), n: xs.length, x1: new Date(`${a}-01-01`), x2: d3.max(xs, (d) => d.dt)};
});
display(Plot.plot({
  width, height: 340, marginLeft: 44,
  x: {label: null, type: "utc"},
  y: {label: "Democratic overperformance (points)", grid: true, tickFormat: (d) => (d > 0 ? `+${d}` : d)},
  style,
  marks: [
    Plot.ruleY([0], {stroke: t.axis}),
    Plot.dot(spec, {x: "dt", y: "overperformance", r: 3.5, fill: (d) => (d.overperformance >= 0 ? t.dem : t.rep), fillOpacity: 0.45}),
    Plot.ruleY(cycleMeans, {x1: "x1", x2: "x2", y: "mean", stroke: t.ink, strokeWidth: 2.5}),
    Plot.text(cycleMeans, {x: "x2", y: "mean", text: (d) => `${d.label}: ${d.mean > 0 ? "+" : ""}${d.mean.toFixed(1)}`, dx: 6, dy: -10, textAnchor: "end", fill: t.ink, fontWeight: 700}),
    Plot.tip(spec, Plot.pointer({x: "dt", y: "overperformance", title: (d) => `${d.state_po} ${d.district} (${d.chamber})\n${date(d.date)}\nResult ${margin(d.special_margin)} vs. president ${margin(d.pres_margin)}\nOverperformance ${d.overperformance > 0 ? "+" : ""}${d.overperformance}`}))
  ]
}));
```

```js
const cur = cycleMeans.at(-1), maxPrev = d3.max(cycleMeans.slice(0, -1), (d) => d.mean);
display(html`<p>Democrats ran about 10 points ahead of the presidential baseline in 2017–18, the cycle before their 2018 wave, and about 4 points behind it in 2021–22, before a Republican-leaning midterm. This cycle they are running ${cur.mean > 0 ? `${cur.mean.toFixed(0)} points ahead` : `${(-cur.mean).toFixed(0)} points behind`} across ${cur.n} races${cur.mean > maxPrev ? ", the strongest showing in the record" : ""}. History shows these races overstate the eventual House margin by about three points, and the model corrects for that.</p>`);
```

## Presidential approval

```js
const app = national.approval.map((d) => ({...d, date: new Date(`${d.end_date}T12:00:00`), net: d.approve - d.disapprove}));
const appDays = d3.utcDays(d3.min(app, (d) => d.date), d3.max(app, (d) => d.date), 4);
const appTrend = appDays.map((day) => {
  const xs = app.filter((d) => (day - d.date) / 864e5 >= 0 && (day - d.date) / 864e5 < 30);
  return {date: day, approve: d3.mean(xs, (d) => d.approve), disapprove: d3.mean(xs, (d) => d.disapprove)};
}).filter((d) => d.approve);
display(Plot.plot({
  width, height: 280, marginLeft: 40,
  x: {label: null, type: "utc"}, y: {label: "Share of adults (%)", grid: true, domain: [25, 65]},
  style,
  marks: [
    Plot.line(appTrend, {x: "date", y: "approve", stroke: t.ink, strokeWidth: 2}),
    Plot.line(appTrend, {x: "date", y: "disapprove", stroke: t["ink-3"], strokeWidth: 2}),
    Plot.text(appTrend.slice(-1), {x: "date", y: "approve", text: (d) => `Approve ${d.approve.toFixed(0)}%`, dx: -4, dy: 14, textAnchor: "end", fill: t.ink, fontWeight: 700}),
    Plot.text(appTrend.slice(-1), {x: "date", y: "disapprove", text: (d) => `Disapprove ${d.disapprove.toFixed(0)}%`, dx: -4, dy: -12, textAnchor: "end", fill: t["ink-2"], fontWeight: 700}),
    Plot.tip(appTrend, Plot.pointerX({x: "date", y: "approve", title: (d) => `${date(d.date.toISOString().slice(0, 10))}\nApprove ${d.approve.toFixed(1)}%\nDisapprove ${d.disapprove.toFixed(1)}%`}))
  ]
}));
```

<p class="caption">President Trump's job approval, 30-day average of polls from VoteHub. Approval feeds the fundamentals reading, which gets the least weight because it has been the least accurate predictor on its own.</p>

## Every election since 1978

```js
const hist = national.history.filter((d) => d.house_margin != null && d.year >= 1978);
display(Plot.plot({
  width, height: 300, marginLeft: 44,
  y: {label: "House popular vote margin", grid: true, tickFormat: (d) => (d === 0 ? "Even" : margin(d).replace(".0", ""))},
  style,
  marks: [
    Plot.ruleY([0], {stroke: t.axis}),
    Plot.barY(hist, {x: "year", y: "house_margin", fill: (d) => (d.house_margin >= 0 ? t.dem : t.rep), rx: 2, insetLeft: 0.5, insetRight: 0.5}),
    Plot.dot(hist.filter((d) => d.generic_margin != null), {x: "year", y: "generic_margin", r: 4, fill: t.surface, stroke: t.ink, strokeWidth: 2}),
    Plot.tip(hist, Plot.pointerX({x: "year", y: "house_margin", title: (d) => `${d.year}${d.midterm ? " (midterm)" : ""}\nHouse vote: ${margin(d.house_margin)}${d.generic_margin != null ? `\nLate-Sept. generic ballot: ${margin(d.generic_margin)}` : ""}${d.net_approval != null ? `\nPresident's net approval: ${d.net_approval > 0 ? "+" : ""}${d.net_approval.toFixed(0)}` : ""}`}))
  ],
  x: {type: "band", label: null, tickFormat: (d) => (d % 4 === 2 ? `'${String(d).slice(2)}` : "")}
}));
```

<p class="caption">Bars: the actual House popular vote. Circles: the generic ballot in late September of that year (since 1996). In nearly every year the circle sits to the Democratic side of the bar.</p>
