---
title: 2026 Midterm Forecast
---

```js
import {tokens, pct, margin, date, oddsPhrase, probBar, raceLink, favoriteText, miniBar, ratingPill, link} from "./components/wsu.js";
import {seatChart} from "./components/charts.js";
const top = FileAttachment("data/topline.json").json();
const seats = FileAttachment("data/seats.json").json();
const races = FileAttachment("data/races.json").json();
const history = FileAttachment("data/history.json").json();
const national = FileAttachment("data/national.json").json();
```

```js
// Headline sentence, written from the numbers so it updates itself every day.
function chamberState(p) {
  const q = Math.max(p, 1 - p);
  const lead = q < 0.55 ? null : p >= 0.5 ? "Democrats" : "Republicans";
  const verb = q >= 0.95 ? "are overwhelming favorites to win" : q >= 0.8 ? "are clear favorites to win"
    : q >= 0.65 ? "are favored to win" : "have a slight edge in";
  return {lead, verb};
}
function headlineFor(pH, pS) {
  const h = chamberState(pH), s = chamberState(pS);
  if (h.lead && h.lead === s.lead) return `${h.lead} ${h.verb} the House and ${s.verb} the Senate.`;
  const one = (x, name) => (x.lead ? `${x.lead} ${x.verb} the ${name}` : `The ${name} is a toss-up`);
  return `${one(h, "House")}. ${one(s, "Senate")}.`;
}
const headline = headlineFor(top.p_house_d, top.p_senate_d);
const daysLeft = Math.round((new Date(`${top.election_day}T12:00:00`) - new Date(`${top.forecast_date}T12:00:00`)) / 864e5);
```

<p class="kicker">2026 midterm forecast · Updated ${date(top.forecast_date)} · ${daysLeft} days to Election Day</p>

# ${headline}

<p class="dek">Who Shows Up forecasts every House, Senate and governor race by asking whose voters will actually turn out. It reads the electorate's enthusiasm from more than 100 special elections, blends it with polls and fundamentals, and simulates the election 20,000 times.</p>

```js
const t = (dark, tokens());
function heroCard(title, p, body, href) {
  const a = document.createElement("a");
  a.className = "hero-card";
  a.href = link(href);
  const lead = p >= 0.5 ? "Democrats" : "Republicans";
  a.innerHTML = `<div class="label"></div><div class="big"></div><div class="sub"></div>`;
  a.querySelector(".label").textContent = title;
  const big = a.querySelector(".big");
  big.textContent = pct(Math.max(p, 1 - p));
  big.style.color = p >= 0.5 ? t.dem : t.rep;
  a.querySelector(".sub").textContent = `chance ${lead} win control`;
  a.append(probBar(p));
  const extra = document.createElement("div");
  extra.className = "sub";
  extra.style.marginTop = "10px";
  extra.textContent = body;
  a.append(extra);
  return a;
}
const govs = races.filter((r) => r.office === "GOV");
display(html`<div class="hero-grid">
  ${heroCard("House", top.p_house_d, `Most likely: ${Math.round(top.house_median)} Democratic seats (80% range ${Math.round(top.house_p10)}–${Math.round(top.house_p90)}). 218 needed.`, "house")}
  ${heroCard("Senate", top.p_senate_d, `Most likely: ${Math.round(top.senate_median)} Democratic seats (80% range ${Math.round(top.senate_p10)}–${Math.round(top.senate_p90)}). Democrats need 51; the vice president breaks ties.`, "senate")}
  <a class="hero-card" href="${link("governors")}">
    <div class="label">Governors</div>
    <div class="big" style="color:${t.ink}">${Math.round(top.gov_median)}<span style="font-size:24px;color:${t["ink-3"]};font-weight:600;margin-left:8px">of 36</span></div>
    <div class="sub">governorships up this year that Democrats are most likely to win (80% range ${Math.round(top.gov_p10)}–${Math.round(top.gov_p90)})</div>
  </a>
</div>`);
```

## How many seats each party wins

<p class="caption">Each bar is how often a seat count came up across 20,000 simulated elections. Blue bars are outcomes where Democrats win control; red where Republicans do.</p>

```js
const houseDist = seats.house.filter((d) => d.p > 0.0004);
const senDist = seats.senate.filter((d) => d.p > 0.0004);
```

```js
const colW = width >= 800 ? (width - 32) / 2 : width;
display(html`<div class="grid-2">
  <div class="panel"><h3>House</h3>${seatChart(houseDist, 218, {width: colW, label: "House", total: 435})}</div>
  <div class="panel"><h3>Senate</h3>${seatChart(senDist, 51, {width: colW, label: "Senate", total: 100})}</div>
</div>`);
```

## The races most likely to decide the Senate

<p class="caption">Ranked by how much the chance of controlling the Senate changes with each race's winner, across all simulations.</p>

```js
const pivotal = races.filter((r) => r.office === "SEN" && r.control_leverage != null)
  .sort((a, b) => b.control_leverage - a.control_leverage).slice(0, 8);
display(html`<div class="table-wrap"><table class="wsu-table">
  <thead><tr><th>Race</th><th>Matchup</th><th class="num">Forecast</th><th class="hide-sm"></th><th class="num">Swing in control</th></tr></thead>
  <tbody>${pivotal.map((r) => html`<tr>
    <td>${raceLink(r)}</td>
    <td>${r.race_type === "independent" ? `${r.race_note} (I)` : r.dem_candidate} vs. ${String(r.rep_candidate).split(";")[0]}</td>
    <td class="num">${favoriteText(r)}</td>
    <td class="hide-sm">${miniBar(r.p_dem)}</td>
    <td class="num">${Math.round(r.control_leverage * 100)} pts</td>
  </tr>`)}</tbody></table></div>`);
```

## The national picture

```js
const env = national.env;
const reads = national.reads;
const readLabel = {fundamentals: "Fundamentals", generic: "Generic ballot", specials: "Special elections"};
display(html`<div class="stat-row">
  <div class="s"><div class="k">Expected House popular vote</div><div class="v">${margin(env.median)}</div></div>
  <div class="s"><div class="k">80% range</div><div class="v">${margin(env.p10)} to ${margin(env.p90)}</div></div>
  ${reads.map((r) => html`<div class="s"><div class="k">${readLabel[r.read]} · ${Math.round(r.weight * 100)}% weight</div><div class="v">${margin(r.dem_margin)}</div></div>`)}
</div>`);
```

```js
const strongest = [...reads].sort((a, b) => b.dem_margin - a.dem_margin)[0];
display(html`<p>Three independent readings of the national mood, each corrected for how it has missed before, are blended by how accurate they have historically been. ${strongest.read === "specials"
  ? "Special-election results, our main turnout signal, currently point to the most Democratic environment of the three."
  : `Right now the ${readLabel[strongest.read].toLowerCase()} reading is the most favorable to Democrats.`} <a href="./national">See the national picture →</a></p>`);
```

## How the forecast has moved

```js
const hist = history.map((d) => ({...d, date: new Date(`${d.forecast_date}T12:00:00`)}));
display(hist.length < 3
  ? html`<p class="caption">The forecast launched on ${date(history[0].forecast_date)}. This chart fills in as daily updates accumulate: ${history.map((d) => `${date(d.forecast_date)}: House ${pct(d.p_house_d)} D, Senate ${pct(d.p_senate_d)} D`).join(" · ")}.</p>`
  : ((w) => Plot.plot({
      width: w, height: 260, y: {domain: [0, 1], tickFormat: "%", label: "Chance Democrats win control", grid: true},
      x: {label: null},
      style: {background: "transparent", color: t["ink-3"], fontSize: "12px"},
      marks: [
        Plot.ruleY([0.5], {stroke: t.axis}),
        Plot.line(hist, {x: "date", y: "p_house_d", stroke: t.dem, strokeWidth: 2}),
        Plot.line(hist, {x: "date", y: "p_senate_d", stroke: t.ind, strokeWidth: 2}),
        Plot.text(hist.slice(-1), {x: "date", y: "p_house_d", text: () => "House", dx: 6, textAnchor: "start", fill: t["ink-2"]}),
        Plot.text(hist.slice(-1), {x: "date", y: "p_senate_d", text: () => "Senate", dx: 6, textAnchor: "start", fill: t["ink-2"]}),
        Plot.tip(hist, Plot.pointerX({x: "date", y: "p_house_d", title: (d) => `${date(d.forecast_date)}\nHouse: ${pct(d.p_house_d)} D\nSenate: ${pct(d.p_senate_d)} D`}))
      ]
    })));
```

## What makes this forecast different

- **Turnout first.** Special-election overperformance is one of the two biggest inputs to the national picture. Every simulation also randomizes how much of the national swing comes from turnout versus voters changing sides.
- **Independent.** No pundit ratings and no other forecasts go into the model. Prediction markets will appear alongside it for comparison, never inside it.
- **Tested, not assumed.** The full model was rerun on 2018, 2020, 2022 and 2024 as those years looked in late September. It called 96% of 1,691 races, and its 80% ranges held 84% of the time. Ideas that failed those tests were dropped.
- **Honest about polls.** September generic-ballot polls have overstated Democrats in 14 of the last 15 elections, campaign-sponsored polls lean toward their sponsor by about four points, and fresh polls count more than stale ones. The model corrects for all three using measured numbers.

<p><a href="./methodology">How the model works, and its track record →</a></p>
