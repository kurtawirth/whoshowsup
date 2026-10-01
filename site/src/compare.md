---
title: Compare the forecasters
---

```js
import {tokens, pct, pctPair, date, ratingPill, raceLink, RATINGS, favoriteText, sides} from "./components/wsu.js";
const races = FileAttachment("data/races.json").json();
const outlets = FileAttachment("data/outlets.json").json();
const top = FileAttachment("data/topline.json").json();
const markets = FileAttachment("data/markets.json").json();
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

<p class="dek">Where we agree with the major raters, modelers and prediction markets, and where we don't. None of them feed into Who Shows Up.</p>

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

## Prediction markets

```js
const mkRows = Object.entries(markets.races).filter(([id]) => byId.has(id))
  .map(([id, m]) => ({r: byId.get(id), m: m.p, gap: byId.get(id).p_dem - m.p}));
const ctl = (key) => markets.races[`control-${key}`]?.p;
// Neutral wording: always name whichever side is favored, with its own chance.
const lastName = (s) => String(s).trim().split(/\s+/).filter((w) => !/^(Jr\.?|Sr\.?|I{2,3})$/.test(w)).pop();
const favored = (r, p) => {
  const s = sides(r), dSide = p >= 0.5;
  return {name: lastName(dSide ? s.d : s.r), tag: dSide ? s.dTag : s.rTag, p: Math.max(p, 1 - p)};
};
const partyPick = (p) => ({name: p >= 0.5 ? "Democrats" : "Republicans", tag: p >= 0.5 ? "D" : "R", p: Math.max(p, 1 - p)});
const tagColor = (tag) => (tag === "D" ? t.dem : tag === "R" ? t.rep : t.ind);
const chip = (x) => html`<span class="mk-pick"><span class="party-chip ${x.tag.toLowerCase()}">${x.tag}</span> ${x.name} ${pct(x.p)}</span>`;
display(html`<p>Prediction markets let people bet on the outcome, and the prices turn into odds. Below are the prices on <a href="https://www.predictit.org">PredictIt</a>, a U.S. market for political bets, as of ${date(markets.asof)}, next to our forecast. Markets are shown for comparison only and never change our numbers.</p>`);
const ctlCard = (label, ours, theirs) => html`<div class="s"><div class="k">${label}</div>
  <div class="mk-ctl"><span class="mk-src">Us</span>${chip(partyPick(ours))}</div>
  <div class="mk-ctl"><span class="mk-src">PredictIt</span>${theirs == null ? "–" : chip(partyPick(theirs))}</div></div>`;
display(html`<div class="stat-row">
  ${ctlCard("Control of the House", top.p_house_d, ctl("house"))}
  ${ctlCard("Control of the Senate", top.p_senate_d, ctl("senate"))}
  <div class="s"><div class="k">Races with a market</div><div class="v">${mkRows.length}</div></div>
</div>`);
```

```js
const officeLabel = {SEN: "Senate", GOV: "Governor", HOUSE: "House"};
const raceName = (r) => (r.office === "HOUSE" ? `House: ${r.label}` : `${r.state_name} ${officeLabel[r.office]}${r.special ? " (special)" : ""}`);
const mkLabel = (x) => (x.r.office === "HOUSE" ? x.r.label : `${x.r.state_po} ${officeLabel[x.r.office].slice(0, 3)}${x.r.special ? " (sp.)" : ""}`);
const bigGaps = [...mkRows].sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap)).slice(0, 6);
// Both axes run from a sure Republican win to a sure win for the other side, with 50/50 in the middle.
const sideTick = (v) => (Math.abs(v - 0.5) < 1e-9 ? "50/50" : v < 0.5 ? `R ${Math.round((1 - v) * 100)}%` : `D ${Math.round(v * 100)}%`);
const ticks = [0, 0.25, 0.5, 0.75, 1];
display(resize((w) => Plot.plot({
  width: Math.min(w, 640), height: Math.min(w, 640) * 0.9, marginLeft: 56, marginBottom: 44, marginRight: 24,
  x: {label: "PredictIt →", domain: [0, 1], ticks, tickFormat: sideTick, grid: true},
  y: {label: "↑ Who Shows Up", domain: [0, 1], ticks, tickFormat: sideTick, grid: true},
  symbol: {domain: ["Senate", "Governor", "House"], range: ["circle", "square", "triangle"], legend: true},
  style: {background: "transparent", color: t["ink-3"], fontSize: "12px"},
  marks: [
    Plot.line([[0, 0], [1, 1]], {stroke: t.axis, strokeDasharray: "4,4"}),
    Plot.ruleX([0.5], {stroke: t.axis}), Plot.ruleY([0.5], {stroke: t.axis}),
    Plot.dot(mkRows, {x: "m", y: (d) => d.r.p_dem, symbol: (d) => officeLabel[d.r.office], r: 5,
      fill: (d) => tagColor(favored(d.r, d.r.p_dem).tag), fillOpacity: 0.75, stroke: t.surface, strokeWidth: 1.5}),
    Plot.text(bigGaps, {x: "m", y: (d) => d.r.p_dem, text: mkLabel, dy: -11, fill: t.ink, fontWeight: 600}),
    Plot.tip(mkRows, Plot.pointer({x: "m", y: (d) => d.r.p_dem, title: (d) => {
      const us = favored(d.r, d.r.p_dem), them = favored(d.r, d.m);
      return `${raceName(d.r)}\nUs: ${us.name} ${pct(us.p)}\nPredictIt: ${them.name} ${pct(them.p)}`;
    }}))
  ]
})));
```

<p class="caption">Each mark is a race with a PredictIt market, colored by the side our forecast favors. Both scales run from a sure Republican win (R 100%) through a coin flip (50/50) to a sure win for the other side (D 100%). On the dashed line, we and the market agree. Above it, our forecast leans further toward the Democratic side than the market does; below it, further toward the Republican side. In Nebraska's Senate race the other side is independent Dan Osborn.</p>

```js
const gapRows = mkRows.filter((x) => Math.abs(x.gap) >= 0.1).sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap));
const toward = (x) => { const s = sides(x.r); return x.gap > 0 ? lastName(s.d) : lastName(s.r); };
display(gapRows.length ? html`<div class="table-wrap"><table class="wsu-table">
  <thead><tr><th>Race</th><th>Our forecast</th><th>PredictIt</th><th>Difference</th></tr></thead>
  <tbody>${gapRows.map((x) => html`<tr>
    <td>${raceLink(x.r, raceName(x.r))}</td>
    <td>${chip(favored(x.r, x.r.p_dem))}</td>
    <td><a href="${markets.races[x.r.race_id].url}">${chip(favored(x.r, x.m))}</a></td>
    <td>${Math.round(Math.abs(x.gap) * 100)} points more toward ${toward(x)} in our forecast</td>
  </tr>`)}</tbody></table></div>` : html`<p class="caption">No race differs by 10 points or more.</p>`);
```

<p class="caption">Races where our forecast and the market differ by 10 points or more, naming the side each one favors. PredictIt's prices come from its free data feed, credited to PredictIt, and are converted to chances: each price is the midpoint between the best offers to buy and sell, rescaled so a race's prices add up to 100% (PredictIt's fees push them a little over). Markets with too few trades to set a clear price are left out, which is why only some House races appear. PredictIt limits how much each trader can bet, so its prices can differ from larger markets. We don't use Kalshi or Polymarket because their terms don't allow their prices to be republished or collected automatically.</p>

## Backtest: how our method would have done against the pros

```js
const track = outlets.track ?? [];
const MAIN = ["Cook Political Report", "Sabato's Crystal Ball", "Inside Elections", "FiveThirtyEight (model)", "Politico",
              "RealClearPolitics", "Fox News", "DDHQ", "The Economist"];
const pick = (asof, subset) => track.filter((d) => d.asof === asof && d.subset === subset && MAIN.includes(d.outlet))
  .sort((a, b) => MAIN.indexOf(a.outlet) - MAIN.indexOf(b.outlet));
const p1 = (v) => (v == null || Number.isNaN(v) ? "–" : `${(v * 100).toFixed(0)}%`);
// One comparison cell: our backtest's number above the outlet's live number, each labeled; the better one is marked
const vs = (a, b, them, better = "high") => {
  const aw = better === "high" ? a > b + 0.004 : a < b - 0.0004, bw = better === "high" ? b > a + 0.004 : b < a - 0.0004;
  const f = better === "high" ? p1 : (v) => (v == null || Number.isNaN(v) ? "–" : v.toFixed(3));
  const line = (who, v, w) => html`<div class="pair ${w ? "win" : ""}"><span class="who">${who}</span><span class="val">${f(v)}</span>${w ? html`<span class="mark" title="Better">✓</span>` : ""}</div>`;
  return html`<div class="pairs">${line("Ours", a, aw)}${line(them, b, bw)}</div>`;
};
const shortName = (o) => ({"Cook Political Report": "Cook", "Sabato's Crystal Ball": "Sabato", "Inside Elections": "Inside", "FiveThirtyEight (model)": "538", "RealClearPolitics": "RCP", "The Economist": "Economist"}[o] ?? o);
function trackTable(asof, subset) {
  const list = pick(asof, subset);
  if (!list.length) return html`<p class="caption">Comparison not yet available.</p>`;
  return html`<div class="table-wrap"><table class="wsu-table track-table">
    <thead><tr><th>Outlet<br><small>their calls, made live</small></th><th class="num">Races</th><th class="num">Winner called<br><small>Toss-up = half</small></th>
      <th class="num">When both picked a side</th><th class="num">Direct disagreements<br><small>our method right</small></th>
      <th class="num">Their Toss-ups<br><small>our method's pick right</small></th><th class="num">Brier<br><small>lower is better</small></th></tr></thead>
    <tbody>${list.map((d) => html`<tr>
      <td><b>${d.outlet.replace(" (model)", "")}</b><div class="cmp-p">${String(d.years).replaceAll(",", ", ")}</div></td>
      <td class="num">${d.races}</td>
      <td class="num">${vs(d.ours_called, d.theirs_called, shortName(d.outlet))}</td>
      <td class="num">${vs(d.ours_right_both, d.theirs_right_both, shortName(d.outlet))}<div class="cmp-p">${d.both_picked} races</div></td>
      <td class="num">${d.ours_won_disagreements} of ${d.disagreed}</td>
      <td class="num">${d.their_tossups_we_picked ? html`${p1(d.ours_right_on_their_tossups)}<div class="cmp-p">${d.their_tossups_we_picked} races</div>` : "–"}</td>
      <td class="num">${d.theirs_brier == null || Number.isNaN(d.theirs_brier) ? html`<span class="cmp-p">ratings only</span>` : vs(d.ours_brier, d.theirs_brier, shortName(d.outlet), "low")}</td>
    </tr>`)}</tbody></table></div>`;
}
const find = (outlet) => track.find((d) => d.asof === "sep22" && d.subset === "competitive" && d.outlet === outlet);
const cook = find("Cook Political Report"), fte = find("FiveThirtyEight (model)"), sab = find("Sabato's Crystal Ball");
display(html`<div class="callout warn"><b>Read this as a backtest, not a track record.</b>
  Who Shows Up didn't exist in 2018 to 2024. We built the method in 2026 and re-ran it on those years using only what was known at the time, while the outlets below made their calls live, under real deadlines and without knowing how things turned out. Each piece of our model was fit without the year being tested, but we chose the method knowing which ideas had worked, which tends to make a backtest look better than live forecasting does. We don't yet know how well these results will hold up in real time; 2026 is the first real test.</div>`);
if (cook && fte) display(html`<div class="callout"><b>The short version.</b>
  In the backtest's competitive races as of September 22, our method would have called the winner in ${p1(cook.ours_called)} of the races Cook rated, versus ${p1(cook.theirs_called)} for Cook's actual calls.
  But most of that edge comes from <i>willingness to pick</i>: Cook left ${cook.their_tossups_we_picked} of those races as Toss-ups, and our method picked a side in them and was right ${p1(cook.ours_right_on_their_tossups)} of the time.
  When both picked a winner, the top raters were about as accurate as our method or a bit more so (Cook ${p1(cook.theirs_right_both)} vs. our ${p1(cook.ours_right_both)}${sab ? `; Sabato ${p1(sab.theirs_right_both)} vs. ${p1(sab.ours_right_both)}` : ""}).
  Against FiveThirtyEight's model, the one other forecast with public probabilities for these years, our method essentially tied (Brier ${fte.ours_brier.toFixed(3)} vs. ${fte.theirs_brier.toFixed(3)}).</div>`);
display(html`<p>How to read the tables: we reran our model on the 2018, 2020, 2022 and 2024 elections using only what was known at the time, and compared it race by race with each outlet's ratings from the same day. In each cell, <b>Ours</b> is our backtest and the outlet's own number is below it; a check mark marks the better one. <b>Winner called</b> is the share of races where the favored side won, with a Toss-up counting as half right (a coin flip gets half). Because Toss-ups only earn half credit, we also show accuracy <b>when both sides picked a winner</b>, and how often our pick was right in races the outlet left as a Toss-up. The <b>Brier score</b> grades probabilities and applies only to forecasts that publish them.</p>`);
display(html`<h3>Competitive races, as of September 22</h3>${trackTable("sep22", "competitive")}`);
display(html`<h3>Competitive races, on the eve of the election</h3>${trackTable("eve", "competitive")}`);
display(html`<details><summary>All races, including safe seats</summary>
  <h3>As of September 22</h3>${trackTable("sep22", "all")}<h3>On the eve of the election</h3>${trackTable("eve", "all")}</details>`);
```

<p class="caption">Our past-year runs read their race polls from FiveThirtyEight's complete poll lists, using only polls finished by each date. "Competitive" means at least one side rated the race below Safe. Past ratings are as listed on Wikipedia's election pages on each date, where every outlet's column is dated and cited; FiveThirtyEight's probabilities come from its archived forecast data. Only races both sides rated are compared.</p>
