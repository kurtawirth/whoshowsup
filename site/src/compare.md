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
function compareTable(office, limit = Infinity) {
  const list = rows.filter((x) => x.r.office === office && competitive(x))
    .sort((a, b) => Math.abs(a.r.p_dem - 0.5) - Math.abs(b.r.p_dem - 0.5));
  const cols = outlets.outlets.filter((o) => list.some((x) => x.ratings[o.name]));
  const cell = (v) => (v ? html`<span class="cmp-pill" style="background:${t[v]};color:${v.startsWith("Safe") || v.startsWith("Likely") ? "#fff" : "#111"}">${v.replace("Toss-up", "Toss-up")}</span>` : html`<span class="cmp-none">–</span>`);
  return html`<div class="cmp-block"><div class="table-wrap"><table class="wsu-table cmp-table">
    <thead><tr><th>Race</th><th class="us">Who Shows Up</th>${cols.map((o) => html`<th title="${o.name}${o.rated_on ? `, updated ${date(o.rated_on)}` : ""}">${o.short}${o.kind === "model" ? html`<sup>M</sup>` : ""}</th>`)}</tr></thead>
    <tbody>${list.map((x, i) => html`<tr class="${i >= limit ? "extra" : ""}">
      <td>${raceLink(x.r)}</td>
      <td class="us">${cell(x.r.rating)}<div class="cmp-p">${favoriteText(x.r)}</div></td>
      ${cols.map((o) => html`<td>${cell(x.ratings[o.name])}</td>`)}
    </tr>`)}</tbody></table></div>
    ${list.length > limit ? html`<button class="show-all" onclick=${(e) => { e.target.closest("div.cmp-block").classList.add("all"); e.target.remove(); }}>Show all ${list.length} races</button>` : ""}
    <p class="caption">${list.length} competitive races (any forecaster rates it below Safe), closest in our forecast first. <sup>M</sup> = statistical model; the rest are expert ratings.</p></div>`;
}
display(compareTable("SEN"));
```

## Governors

```js
display(compareTable("GOV"));
```

```js
const houseRows = rows.filter((x) => x.r.office === "HOUSE");
display(houseRows.length ? html`<h2>House</h2>${compareTable("HOUSE", 25)}` : html``);
```

## Track record against the pros

```js
const track = outlets.track ?? [];
const MAIN = ["Cook Political Report", "Sabato's Crystal Ball", "Inside Elections", "FiveThirtyEight (model)", "Politico",
              "RealClearPolitics", "Fox News", "DDHQ", "The Economist"];
const pick = (asof, subset) => track.filter((d) => d.asof === asof && d.subset === subset && MAIN.includes(d.outlet))
  .sort((a, b) => MAIN.indexOf(a.outlet) - MAIN.indexOf(b.outlet));
const p1 = (v) => (v == null || Number.isNaN(v) ? "–" : `${(v * 100).toFixed(0)}%`);
const vs = (a, b, better = "high") => {
  const aw = better === "high" ? a > b + 0.004 : a < b - 0.0004, bw = better === "high" ? b > a + 0.004 : b < a - 0.0004;
  const f = better === "high" ? p1 : (v) => (v == null || Number.isNaN(v) ? "–" : v.toFixed(3));
  return html`<span class="${aw ? "win" : ""}">${f(a)}</span> <span class="vs">vs</span> <span class="${bw ? "win" : ""}">${f(b)}</span>`;
};
function trackTable(asof, subset) {
  const list = pick(asof, subset);
  if (!list.length) return html`<p class="caption">Comparison not yet available.</p>`;
  return html`<div class="table-wrap"><table class="wsu-table track-table">
    <thead><tr><th>Us vs.</th><th class="num">Races</th><th class="num">Winner called<br><small>Toss-up = half</small></th>
      <th class="num">When both picked a side</th><th class="num">Direct disagreements<br><small>we were right</small></th>
      <th class="num">Their Toss-ups we picked<br><small>we were right</small></th><th class="num">Brier<br><small>lower is better</small></th></tr></thead>
    <tbody>${list.map((d) => html`<tr>
      <td><b>${d.outlet.replace(" (model)", "")}</b><div class="cmp-p">${String(d.years).replaceAll(",", ", ")}</div></td>
      <td class="num">${d.races}</td>
      <td class="num">${vs(d.ours_called, d.theirs_called)}</td>
      <td class="num">${vs(d.ours_right_both, d.theirs_right_both)}<div class="cmp-p">${d.both_picked} races</div></td>
      <td class="num">${d.ours_won_disagreements} of ${d.disagreed}</td>
      <td class="num">${d.their_tossups_we_picked ? html`${p1(d.ours_right_on_their_tossups)}<div class="cmp-p">${d.their_tossups_we_picked} races</div>` : "–"}</td>
      <td class="num">${d.theirs_brier == null || Number.isNaN(d.theirs_brier) ? html`<span class="cmp-p">ratings only</span>` : vs(d.ours_brier, d.theirs_brier, "low")}</td>
    </tr>`)}</tbody></table></div>`;
}
const find = (outlet) => track.find((d) => d.asof === "sep22" && d.subset === "competitive" && d.outlet === outlet);
const cook = find("Cook Political Report"), fte = find("FiveThirtyEight (model)"), sab = find("Sabato's Crystal Ball");
if (cook && fte) display(html`<div class="callout"><b>The short version.</b>
  In competitive races as of September 22, we called the winner in ${p1(cook.ours_called)} of the races Cook rated, versus ${p1(cook.theirs_called)} for Cook.
  But most of that edge comes from <i>willingness to pick</i>: Cook left ${cook.their_tossups_we_picked} of those races as Toss-ups, and we picked a side in them and were right ${p1(cook.ours_right_on_their_tossups)} of the time.
  When both of us picked a winner, the top raters were about as accurate as us or a bit more so (Cook ${p1(cook.theirs_right_both)} vs. our ${p1(cook.ours_right_both)}${sab ? `; Sabato ${p1(sab.theirs_right_both)} vs. ${p1(sab.ours_right_both)}` : ""}).
  Against FiveThirtyEight's model, the one other forecast with public probabilities for these years, we were essentially tied (Brier ${fte.ours_brier.toFixed(3)} vs. ${fte.theirs_brier.toFixed(3)}).</div>`);
display(html`<p>We reran our model on the 2018, 2020, 2022 and 2024 elections using only what was known at the time, and compared it race by race with each outlet's ratings from the same day. <b>Winner called</b> is the share of races where the favored side won, with a Toss-up counting as half right (a coin flip gets half). Because Toss-ups only earn half credit, we also show accuracy <b>when both sides picked a winner</b>, and how often our pick was right in races the outlet left as a Toss-up. The <b>Brier score</b> grades probabilities and applies only to forecasts that publish them.</p>`);
display(html`<h3>Competitive races, as of September 22</h3>${trackTable("sep22", "competitive")}`);
display(html`<h3>Competitive races, on the eve of the election</h3>${trackTable("eve", "competitive")}`);
display(html`<details><summary>All races, including safe seats</summary>
  <h3>As of September 22</h3>${trackTable("sep22", "all")}<h3>On the eve of the election</h3>${trackTable("eve", "all")}</details>`);
```

<p class="caption"><b>Read these with a grain of salt in our favor.</b> Our past-year numbers come from a backtest: the same method run after the fact on what was knowable then. Each piece was fit without the year being tested, but we designed the method in 2026 knowing how these elections turned out, while the outlets made their calls live. Our 2024 run also had no race polls (no public archive), which works against us. "Competitive" means at least one side rated the race below Safe. Past ratings are as listed on Wikipedia's election pages on each date, where every outlet's column is dated and cited; FiveThirtyEight's probabilities come from its archived forecast data. Only races both sides rated are compared.</p>
