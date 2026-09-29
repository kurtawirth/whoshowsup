---
title: Early vote
---

```js
import {tokens, pct, date} from "./components/wsu.js";
const ev = FileAttachment("data/early_vote.json").json();
```

```js
const t = (dark, tokens());
const fmt = (n) => (n ?? 0).toLocaleString();
const states = [...ev.states].sort((a, b) => b.cast - a.cast);
const cast = d3.sum(states, (d) => d.cast);
const requested = d3.sum(states, (d) => d.requested);
const partyStates = states.filter((d) => d.dem != null);
```

<p class="kicker">Early vote · Updated ${date(ev.as_of)}</p>

# Who has voted so far

<p class="dek">Ballots cast before Election Day, in the ${states.length} states reporting them so far. This page shows who is turning out early; it is not an input to the forecast.</p>

```js
display(html`<div class="stat-row">
  <div class="s"><div class="k">Ballots cast so far</div><div class="v">${fmt(cast)}</div></div>
  <div class="s"><div class="k">Mail ballots requested</div><div class="v">${fmt(requested)}</div></div>
  <div class="s"><div class="k">States reporting</div><div class="v">${states.length}</div></div>
</div>`);
```

## Early voters lean Democratic

Early voters have leaned Democratic in every election since at least 2008. Among people who voted in person before Election Day, Democrats outnumbered Republicans by 8 to 19 points; among mail voters, by 1 to 13 points; Election Day voters split about evenly. Then 2020 blew the gap open. Voting by mail became a Democratic habit and Election Day turned Republican, and the split held in 2022.

So an early vote that looks very blue is normal and says little on its own. What matters is whether it is bluer or redder than usual, and the ballots cast on Election Day will pull the count back toward Republicans.

```js
const modes = ["Mail", "Early in person", "Election Day"];
const modeColor = {"Mail": t.ind, "Early in person": t.ink, "Election Day": t["ink-3"]};
const lean = (g) => (Math.abs(g) < 0.5 ? "even" : g > 0 ? `D+${Math.round(g)}` : `R+${Math.round(-g)}`);
const byMode = ev.by_mode.map((d) => ({...d, when: new Date(`${d.year}-11-06`)}));
display(resize((w) => Plot.plot({
  width: w, height: 300, marginLeft: 48, marginRight: w < 560 ? 12 : 110,
  x: {label: null, ticks: [...new Set(byMode.map((d) => d.when.getTime()))].map((v) => new Date(v)), tickFormat: "%Y"},
  y: {label: "Party lean of voters (D minus R, points)", grid: true, tickFormat: (v) => (v === 0 ? "Even" : v > 0 ? `D+${v}` : `R+${-v}`), domain: [-25, 30]},
  color: {domain: modes, range: modes.map((m) => modeColor[m]), legend: w < 560},
  style: {background: "transparent", color: t["ink-3"], fontSize: "12px"},
  marks: [
    Plot.ruleY([0], {stroke: t.axis}),
    Plot.line(byMode, {x: "when", y: "gap", stroke: "mode", strokeWidth: 2.5, strokeDasharray: (d) => (d.mode === "Election Day" ? "5,4" : null)}),
    Plot.dot(byMode, {x: "when", y: "gap", fill: "mode", r: 4, stroke: t.surface, strokeWidth: 2}),
    w < 560 ? null : Plot.text(byMode.filter((d) => d.year === d3.max(byMode, (e) => e.year)), {x: "when", y: "gap", text: "mode", fill: "mode", dx: 10, textAnchor: "start", fontWeight: 600}),
    Plot.tip(byMode, Plot.pointer({x: "when", y: "gap", title: (d) => `${d.year}, ${d.mode.toLowerCase()} voters\n${lean(d.gap)} by party\n${Math.round(100 * d.share_of_voters)}% of all voters`}))
  ]
})));
```

<p class="caption">How voters who cast their ballot each way identified themselves by party, with Democrats' share minus Republicans'. From MIT's Survey of the Performance of American Elections, about 10,000 voters per election (the 2018 and 2024 surveys aren't available to download). It measures party identification, not votes, but the pattern matches how the parties' voters have used each method.</p>

## Ballots cast over time

```js
const byDate = d3.rollups(ev.series, (v) => d3.sum(v, (d) => d.cast), (d) => d.date)
  .map(([date, cast]) => ({date: new Date(date), cast})).sort((a, b) => a.date - b.date);
display(resize((w) => Plot.plot({
  width: w, height: 240, marginLeft: 56,
  y: {label: "Ballots cast", grid: true, tickFormat: "~s"},
  x: {label: null, ticks: d3.utcWeek.every(1), tickFormat: "%b %-d"},
  style: {background: "transparent", color: t["ink-3"], fontSize: "12px"},
  marks: [
    Plot.areaY(byDate, {x: "date", y: "cast", fill: t["ink-3"], fillOpacity: 0.12}),
    Plot.line(byDate, {x: "date", y: "cast", stroke: t.ink, strokeWidth: 2}),
    Plot.tip(byDate, Plot.pointerX({x: "date", y: "cast", title: (d) => `${d3.utcFormat("%b %-d")(d.date)}\n${fmt(d.cast)} ballots cast`}))
  ]
})));
```

<p class="caption">Mail ballots returned plus in-person early votes, added up across the reporting states. States join the count as they begin reporting, so part of the rise is new states.</p>

## By state

```js
function partyBar(d) {
  if (d.dem == null) return html`<span class="muted">Not recorded</span>`;
  const n = d.dem + d.rep + d.other || 1;
  if (n < 500) return html`<span class="muted">Too few ballots yet</span>`;
  const seg = (v, c) => `<b style="width:${(100 * v) / n}%;background:${c}"></b>`;
  const el = html`<span class="ev-party" title="${pct(d.dem / n)} registered Democrats, ${pct(d.other / n)} other or none, ${pct(d.rep / n)} registered Republicans"></span>`;
  el.innerHTML = seg(d.dem, t["party-d"]) + seg(d.other, t.hair) + seg(d.rep, t["party-r"]);
  const lab = html`<span class="ev-party-lab"><span style="color:${t["party-d"]}">D ${pct(d.dem / n)}</span> · <span style="color:${t["party-r"]}">R ${pct(d.rep / n)}</span></span>`;
  return html`<span class="ev-party-cell">${el}${lab}</span>`;
}
display(html`<div class="table-wrap"><table class="wsu-table">
  <thead><tr><th>State</th><th class="num">Ballots cast</th><th class="num">Share of 2022 vote</th><th class="num">Mail ballots returned</th><th>Party registration of voters so far</th></tr></thead>
  <tbody>${states.map((d) => html`<tr>
    <td>${d.state_name}</td>
    <td class="num">${fmt(d.cast)}</td>
    <td class="num">${d.turnout22 ? pct(d.cast / d.turnout22) : "–"}</td>
    <td class="num">${d.requested ? `${fmt(d.returned)} of ${fmt(d.requested)}` : fmt(d.returned)}</td>
    <td>${partyBar(d)}</td>
  </tr>`)}</tbody>
</table></div>`);
```

<p class="caption">"Share of 2022 vote" compares ballots cast so far with each state's total vote for the U.S. House in 2022. Party registration is shown only where the state records it (${partyStates.length} of ${states.length} states) and at least 500 ballots are in, and it is not a vote: many registered Democrats and Republicans vote for the other party, and early voters differ from Election Day voters in ways that change from year to year, so an early lead in party registration does not mean a lead in votes. States count and report ballots differently, and some report only mail ballots.</p>

<p class="caption">Early-vote counts from <a href="https://civicapi.org">civicAPI</a>, compiled from state election offices. Updated every morning.</p>
