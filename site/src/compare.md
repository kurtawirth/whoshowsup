---
title: Compare the forecasters
---

```js
import {tokens, pct, pctPair, date, ratingPill, raceLink, RATINGS, favoriteText} from "./components/wsu.js";
const races = FileAttachment("data/races.json").json();
const outlets = FileAttachment("data/outlets.json").json();
const top = FileAttachment("data/topline.json").json();
```

```js
const t = (dark, tokens());
const byId = new Map(races.map((r) => [r.race_id, r]));
const SCORE = {"Safe D": 3, "Likely D": 2, "Lean D": 1, "Toss-up": 0, "Lean R": -1, "Likely R": -2, "Safe R": -3};
const names = outlets.outlets.map((o) => o.name);
// Consensus = the median of the outlets' ratings, on the Safe D (+3) ... Safe R (-3) scale.
function consensus(ratings) {
  const v = Object.values(ratings).map((x) => SCORE[x]).filter((x) => x != null).sort((a, b) => a - b);
  if (!v.length) return null;
  const m = v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2;
  return m;
}
const fromScore = (s) => RATINGS[3 - Math.round(s)];
const rows = Object.entries(outlets.races).map(([id, ratings]) => {
  const r = byId.get(id);
  if (!r) return null;
  const c = consensus(ratings);
  return {r, ratings, cons: c, gap: c == null ? 0 : SCORE[r.rating] - c};
}).filter(Boolean);
const competitive = (x) => x.r.rating !== "Safe D" && x.r.rating !== "Safe R" || Object.values(x.ratings).some((v) => v !== "Safe D" && v !== "Safe R");
```

<p class="kicker">Compare · Updated ${date(top.forecast_date)}</p>

# How our forecast compares with the major forecasters

<p class="dek">The raters and modelers below never feed into Who Shows Up; we build the forecast from polls, special elections and past results alone. Here is where we agree with them, where we don't, and how our method would have stacked up against them in past elections.</p>

```js
const disagree = rows.filter((x) => x.cons != null && Math.abs(x.gap) >= 1.5 && competitive(x))
  .sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap));
const moreD = disagree.filter((x) => x.gap > 0), moreR = disagree.filter((x) => x.gap < 0);
const officeWord = {SEN: "Senate", GOV: "Governor", HOUSE: "House"};
const item = (x) => html`<li>${raceLink(x.r, x.r.office === "HOUSE" ? `House: ${x.r.label}` : `${x.r.label} ${officeWord[x.r.office].toLowerCase()}`)}: we say <b>${x.r.rating}</b> (${favoriteText(x.r)}); the consensus is <b>${fromScore(x.cons)}</b>.</li>`;
display(html`<div class="grid-2">
  <div class="panel"><h3>Where we're more Democratic than the consensus</h3>${moreD.length ? html`<ul class="tight">${moreD.slice(0, 8).map(item)}</ul>` : html`<p class="caption">No big disagreements.</p>`}</div>
  <div class="panel"><h3>Where we're more Republican than the consensus</h3>${moreR.length ? html`<ul class="tight">${moreR.slice(0, 8).map(item)}</ul>` : html`<p class="caption">No big disagreements.</p>`}</div>
</div>`);
```

<p class="caption">"Consensus" is the middle rating across the outlets listed below. A disagreement is at least a step and a half apart on the Safe–Likely–Lean–Toss-up scale, in a race someone rates as competitive.</p>

## Senate

```js
function compareTable(office) {
  const list = rows.filter((x) => x.r.office === office && competitive(x))
    .sort((a, b) => Math.abs(a.r.p_dem - 0.5) - Math.abs(b.r.p_dem - 0.5));
  const cols = outlets.outlets.filter((o) => list.some((x) => x.ratings[o.name]));
  const cell = (v) => (v ? html`<span class="cmp-pill" style="background:${t[v]};color:${v.startsWith("Safe") || v.startsWith("Likely") ? "#fff" : "#111"}">${v.replace("Toss-up", "Toss-up")}</span>` : html`<span class="cmp-none">–</span>`);
  return html`<div class="table-wrap"><table class="wsu-table cmp-table">
    <thead><tr><th>Race</th><th class="us">Who Shows Up</th>${cols.map((o) => html`<th title="${o.name}${o.rated_on ? `, updated ${date(o.rated_on)}` : ""}">${o.short}${o.kind === "model" ? html`<sup>M</sup>` : ""}</th>`)}</tr></thead>
    <tbody>${list.map((x) => html`<tr>
      <td>${raceLink(x.r)}</td>
      <td class="us">${cell(x.r.rating)}<div class="cmp-p">${favoriteText(x.r)}</div></td>
      ${cols.map((o) => html`<td>${cell(x.ratings[o.name])}</td>`)}
    </tr>`)}</tbody></table></div>
    <p class="caption">${list.length} competitive races (any forecaster rates it below Safe), closest in our forecast first. <sup>M</sup> = statistical model; the rest are expert ratings.</p>`;
}
display(compareTable("SEN"));
```

## Governors

```js
display(compareTable("GOV"));
```

```js
const houseRows = rows.filter((x) => x.r.office === "HOUSE");
display(houseRows.length ? html`<h2>House</h2>${compareTable("HOUSE")}` : html``);
```

## Track record against the pros

```js
const track = outlets.track ?? [];
const pick = (asof, subset) => track.filter((d) => d.asof === asof && d.subset === subset).sort((a, b) => b.races - a.races);
const pctf = (v) => `${(v * 100).toFixed(1)}%`;
function trackTable(asof, subset) {
  const list = pick(asof, subset);
  if (!list.length) return html`<p class="caption">Comparison not yet available.</p>`;
  return html`<div class="table-wrap"><table class="wsu-table">
    <thead><tr><th>Compared with</th><th class="num">Races</th><th class="num">Years</th><th class="num">Winner called: us</th><th class="num">Winner called: them</th><th class="num">Toss-ups: us / them</th><th class="num">Brier: us / them</th></tr></thead>
    <tbody>${list.map((d) => html`<tr>
      <td><b>${d.outlet}</b></td><td class="num">${d.races}</td><td class="num">${String(d.years).replaceAll(",", ", ")}</td>
      <td class="num ${d.ours_called > d.theirs_called + 0.0005 ? "win" : ""}">${pctf(d.ours_called)}</td>
      <td class="num ${d.theirs_called > d.ours_called + 0.0005 ? "win" : ""}">${pctf(d.theirs_called)}</td>
      <td class="num">${d.ours_tossups} / ${d.theirs_tossups}</td>
      <td class="num">${d.ours_brier.toFixed(3)} / ${d.theirs_brier == null || Number.isNaN(d.theirs_brier) ? "–" : d.theirs_brier.toFixed(3)}</td>
    </tr>`)}</tbody></table></div>`;
}
display(html`<p>We reran our model on the 2018, 2020, 2022 and 2024 elections using only the information available at the time, and compared it race by race with each outlet's ratings from the same day. <b>Winner called</b> is the share of races where the favored side won; a Toss-up counts as half right, the same as a coin flip. The <b>Brier score</b> grades probabilities (lower is better) and applies only to forecasts that publish them.</p>`);
display(html`<h3>Competitive races, as of September 22</h3>${trackTable("sep22", "competitive")}`);
display(html`<h3>Competitive races, on the eve of the election</h3>${trackTable("eve", "competitive")}`);
display(html`<details><summary>All races, including safe seats</summary>
  <h3>As of September 22</h3>${trackTable("sep22", "all")}<h3>On the eve of the election</h3>${trackTable("eve", "all")}</details>`);
```

<p class="caption">Ratings as listed on Wikipedia's election pages on each date, where every outlet's column is dated and cited; FiveThirtyEight's probabilities come from its archived forecast data. Our past-year forecasts are a backtest: the same method run after the fact on what was knowable then, not forecasts we published at the time. Only races both sides rated are compared. Ratings shown for 2026 are each outlet's own; see their sites for details.</p>
