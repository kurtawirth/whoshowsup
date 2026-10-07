---
title: Election night
---

```js
import {tokens, pct, date, sides, raceLink, raceTable, withSearch} from "./components/wsu.js";
import {liveStream, liveOdds, votesLeft} from "./components/live.js";
const liveModel = FileAttachment("data/live_model.json").json();
const races = FileAttachment("data/races.json").json();
const top = FileAttachment("data/topline.json").json();
const liveFile = FileAttachment("data/live.json");
```

```js
// Results: civicAPI directly during the night (every reader shares its cached answer), with the copy our poller
// publishes every few minutes as the fallback (components/live.js). ?direct in the address turns the direct feed on early, for testing.
const live = liveStream(liveFile, races, liveModel.civic, {Generators, force: new URLSearchParams(location.search).has("direct")});
```

```js
const t = (dark, tokens());
// When each state's polls close, in Eastern Time (first polls, last polls), from The Green Papers.
// 24 = midnight, 25 = 1 a.m. on Nov. 4.
const CLOSE = {AL: [20, 20], AK: [24, 25], AZ: [21, 21], AR: [20.5, 20.5], CA: [23, 23], CO: [21, 21], CT: [20, 20], DE: [20, 20],
  FL: [19, 20], GA: [19, 19], HI: [24, 24], ID: [22, 23], IL: [20, 20], IN: [18, 19], IA: [21, 21], KS: [20, 21], KY: [18, 19],
  LA: [21, 21], ME: [20, 20], MD: [20, 20], MA: [20, 20], MI: [20, 21], MN: [21, 21], MS: [20, 20], MO: [20, 20], MT: [22, 22],
  NE: [21, 21], NV: [22, 22], NH: [20, 20], NJ: [20, 20], NM: [21, 21], NY: [21, 21], NC: [19.5, 19.5], ND: [21, 22], OH: [19.5, 19.5],
  OK: [20, 20], OR: [22, 23], PA: [20, 20], RI: [20, 20], SC: [19, 19], SD: [20, 21], TN: [20, 20], TX: [20, 21], UT: [22, 22],
  VT: [19, 19], VA: [19, 19], WA: [23, 23], WV: [19.5, 19.5], WI: [21, 21], WY: [21, 21]};
const clock = (h) => { const hh = Math.floor(h) % 24, mm = Math.round((h % 1) * 60); return `${hh % 12 || 12}${mm ? `:${String(mm).padStart(2, "0")}` : ""} ${hh >= 12 ? "p.m." : "a.m."}`; };
const lastName = (s) => String(s).trim().split(/\s+/).filter((w) => !/^(Jr\.?|Sr\.?|I{2,3})$/.test(w)).pop();
const officeLabel = {SEN: "Senate", GOV: "Governor", HOUSE: "House"};
const raceName = (r) => (r.office === "HOUSE" ? `House: ${r.label}` : `${r.state_name} ${officeLabel[r.office]}${r.special ? " (special)" : ""}`);
const contested = races.filter((r) => r.race_type !== "same_party");
const tagColor = (tag) => (tag === "D" ? t.dem : tag === "R" ? t.rep : t.ind);
const chip = (tag) => html`<span class="party-chip ${tag.toLowerCase()}">${tag}</span>`;
```

```js
const L = live.races ?? {};
const started = live.mode !== "waiting" && Object.keys(L).length > 0;
const asof = live.asof ? new Date(live.asof) : null;
const etTime = (d) => d.toLocaleTimeString("en-US", {timeZone: "America/New_York", hour: "numeric", minute: "2-digit"}) + " ET";
// one row per race: our forecast and the latest count
const rows = contested.map((r) => {
  const s = sides(r), x = L[r.race_id] ?? {};
  const counted = (x.d ?? 0) + (x.r ?? 0) > 0;
  const lead = counted ? (x.margin >= 0 ? "D" : "R") : null;
  const tagOf = (side) => (side === "D" ? s.dTag : s.rTag);
  const nameOf = (side) => (side === "D" ? s.d : s.r);
  return {...r, s, x, counted, lead, called: x.called ?? null, tagOf, nameOf,
    fav: r.p_dem >= 0.5 ? "D" : "R", closes: (CLOSE[r.state_po] ?? [21, 21])[1]};
});
const calledRows = rows.filter((d) => d.called);
const right = calledRows.filter((d) => d.called === d.fav);
const settled = rows.filter((d) => d.counted && (d.x.pct ?? 0) >= 95);
const inRange = settled.filter((d) => d.x.margin >= d.margin_p10 && d.x.margin <= d.margin_p90);
```

${live.mode === "simulation" ? html`<div class="sim-banner"><b>Rehearsal.</b> These are made-up results for testing the page, not real votes.</div>` : live.mode === "practice" ? html`<div class="sim-banner"><b>Practice run.</b> Real counts from civicAPI, fetched to test the page; not published.</div>` : ""}

<p class="kicker">Election night · November 3, 2026${asof && started ? ` · Updated ${etTime(asof)}${live.source === "direct" ? " · live from civicAPI" : ""}` : ""}</p>

# ${started ? `${live.called} of ${live.total} races called` : "Results will appear here on election night"}

<p class="dek">${started
  ? html`Vote counts from <a href="https://civicapi.org">civicAPI</a>, refreshed every few minutes, next to what our forecast expected. This page updates on its own; there's no need to reload. Calls are civicAPI's, not ours.`
  : html`From the first poll closings at 6 p.m. Eastern on November 3, the count for every House, Senate and governor race will appear here every few minutes, next to what our forecast expected, with a running tally of the House and Senate. ${(() => { const days = Math.ceil((new Date("2026-11-03T23:00:00Z") - new Date()) / 864e5); return days > 0 ? `That's ${days} day${days === 1 ? "" : "s"} away.` : ""; })()}`}</p>

```js
// Chamber tallies: called seats, then seats where someone leads, then seats not yet counted.
function tally(office, base = {D: 0, R: 0}) {
  const list = rows.filter((d) => d.office === office);
  // seats where only one party is on the ballot (California's top-two, unopposed) are already decided
  const fixed = races.filter((r) => r.office === office && r.race_type === "same_party");
  const c = {Dc: base.D + fixed.filter((r) => r.race_note === "D").length, Dl: 0, Ic: 0, Il: 0, Rl: 0,
    Rc: base.R + fixed.filter((r) => r.race_note === "R").length, open: 0};
  for (const d of list) {
    const tag = d.called ? d.tagOf(d.called) : d.lead ? d.tagOf(d.lead) : null;
    if (!tag) c.open++;
    else if (d.called) c[tag + "c"]++;
    else c[tag + "l"]++;
  }
  return c;
}
function tallyBar(label, c, need, total, note) {
  const seg = (n, color, opacity = 1) => (n ? `<b style="flex:${n};background:${color};opacity:${opacity}"></b>` : "");
  const bar = html`<div class="tally-bar"></div>`;
  bar.innerHTML = seg(c.Dc, t.dem) + seg(c.Dl, t.dem, 0.4) + seg(c.Ic + c.Il, t.ind, c.Ic ? 1 : 0.4) + seg(c.open, t.hair) + seg(c.Rl, t.rep, 0.4) + seg(c.Rc, t.rep)
    + (need ? `<i style="left:${(100 * need) / total}%"></i>` : "");
  return html`<div class="tally">
    <div class="tally-head"><b>${label}</b><span class="muted">${note}</span></div>
    ${bar}
    <div class="tally-nums"><span>${chip("D")} ${c.Dc} won${c.Dl ? `, ${c.Dl} leading` : ""}</span>${c.Ic + c.Il ? html`<span>${chip("I")} ${c.Ic} won${c.Il ? `, ${c.Il} leading` : ""}</span>` : ""}<span class="muted">${c.open} not yet counted</span><span>${chip("R")} ${c.Rc} won${c.Rl ? `, ${c.Rl} leading` : ""}</span></div>
  </div>`;
}
// Live odds: what the races that have finished counting say about the ones still out (components/live.js)
const odds = started ? liveOdds(races, liveModel, live.races) : null;
if (odds) {
  const party = (p) => (p >= 0.5 ? `D ${pct(p)}` : `R ${pct(1 - p)}`);
  const shift = odds.shift, dir = shift >= 0 ? "Democratic" : "Republican";
  display(html`<h2>Live odds</h2>
  <div class="stat-row">
    <div class="s"><div class="k">Senate control</div><div class="v">${party(odds.pSen)}</div><div class="muted">this morning: ${party(top.p_senate_d)}</div></div>
    <div class="s"><div class="k">House control</div><div class="v">${party(odds.pHouse)}</div><div class="muted">this morning: ${party(top.p_house_d)}</div></div>
  </div>
  <p class="caption">${odds.used
    ? `Based on the ${odds.used} race${odds.used === 1 ? "" : "s"} at least 95% counted, results so far are running about ${Math.abs(shift).toFixed(1)} points more ${dir} than our forecast nationally (more or less in some regions and states). We move every race still out by that much, count called races for their winners, and play out the rest of the night thousands of times.`
    : "Until races finish counting, these are our forecast's odds with called races counted for their winners. Partial counts don't move them: early votes lean toward whichever party's voters cast that kind of ballot."} Not a call: an estimate that will swing as results come in.</p>`);
}
if (started) display(html`<div class="tallies">
  ${tallyBar("Senate", tally("SEN", {D: 34, R: 31}), 51, 100, "51 seats for control (50 plus the vice president for Republicans); includes the 65 seats not up this year")}
  ${tallyBar("House", tally("HOUSE"), 218, 435, "218 seats for control; includes seats where only one party is on the ballot")}
  ${tallyBar("Governors", tally("GOV"), null, 36, "36 races")}
</div>`);
```

```js
if (started && calledRows.length) display(html`<div class="stat-row">
  <div class="s"><div class="k">Our favorite won</div><div class="v">${right.length} of ${calledRows.length} called races</div></div>
  <div class="s"><div class="k">Inside our 80% range</div><div class="v">${settled.length ? `${inRange.length} of ${settled.length}` : "–"}</div><div class="muted">races with 95%+ counted</div></div>
</div>`);
const upsets = calledRows.filter((d) => d.called !== d.fav).sort((a, b) => Math.abs(b.p_dem - 0.5) - Math.abs(a.p_dem - 0.5));
const upsetItem = (d) => html`<li>${raceLink(d, raceName(d))}: ${lastName(d.nameOf(d.called))} wins, whom we gave ${pct(d.called === "D" ? d.p_dem : 1 - d.p_dem)}</li>`;
if (upsets.length) display(html`<div class="upsets"><p><b>Called against our forecast</b>${upsets.length > 5 ? ", biggest surprises first" : ""}:</p>
  <ul class="tight">${upsets.slice(0, 5).map(upsetItem)}</ul>
  ${upsets.length > 5 ? html`<details><summary>Show all ${upsets.length}</summary><ul class="tight">${upsets.slice(5).map(upsetItem)}</ul></details>` : ""}</div>`);
```

```js
if (started) display(watchTable());
```

```js
// A race's count against our forecast: the 80% range (bar), our most likely result (tick) and the count so far (dot).
const SPAN = 20;  // the bar runs from R+20 to D+20; margins beyond sit at the ends
function rangeBar(d) {
  const X = (m) => 50 + (50 * Math.max(-SPAN, Math.min(SPAN, m))) / SPAN;
  const el = html`<span class="rng" title="Our 80% range, ${sideText(d, d.margin_p10)} to ${sideText(d, d.margin_p90)}"></span>`;
  el.innerHTML = `<i class="mid"></i><b style="left:${X(d.margin_p10)}%;width:${X(d.margin_p90) - X(d.margin_p10)}%"></b>`
    + `<i class="med" style="left:${X(d.margin_median)}%"></i>`
    + (d.counted ? `<em style="left:${X(d.x.margin)}%;background:${tagColor(d.tagOf(d.lead))}"></em>` : "");
  return el;
}
function sideText(d, m) { const side = m >= 0 ? "D" : "R"; return `${lastName(d.nameOf(side))} +${Math.abs(m).toFixed(1)}`; }
const status = (d) => (d.called ? html`<span class="res-called">${chip(d.tagOf(d.called))} ${lastName(d.nameOf(d.called))} wins</span>`
  : d.counted ? html`<span>${sideText(d, d.x.margin)}${leftText(d)}</span>` : html`<span class="muted">No votes yet (polls close ${clock((CLOSE[d.state_po] ?? [21])[0])})</span>`);
// "about 150,000 votes left; Turek needs 54% of them" / "lead bigger than the votes left"
function leftText(d) {
  const v = votesLeft(d.x);
  if (!v) return "";
  const k = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)} million` : n >= 1e4 ? `${Math.round(n / 1000).toLocaleString()},000` : (Math.round(n / 100) * 100 || n).toLocaleString());
  const trail = v.leader === "D" ? "R" : "D";
  return html`<div class="adj">${v.locked ? `Lead of ${k(v.lead)} is bigger than the ~${k(v.left)} votes left` : `~${k(v.left)} votes left; ${lastName(d.nameOf(trail))} needs ${Math.round(v.need * 100)}% of them`}</div>`;
}
if (started) {
  const order = (d) => (d.called ? 2 : d.counted ? 0 : 1) * 10 + Math.abs(d.p_dem - 0.5);
  display(html`<h2>Every race</h2>`);
  const tbl = raceTable(withSearch([...rows].sort((a, b) => order(a) - order(b))), [
    {key: "label", label: "Race", sort: true, render: (d) => raceLink(d, raceName(d))},
    {key: "status", label: "Result so far", render: status},
    {key: "pct", label: "Counted", num: true, sort: true, sortValue: (d) => d.x.pct ?? -1, render: (d) => (d.counted ? `${d.x.pct ?? 0}%` : "")},
    {key: "range", label: "vs. our forecast", render: rangeBar},
    {key: "p_dem", label: "Our odds", sort: true, sortValue: (d) => Math.max(d.p_dem, 1 - d.p_dem), render: (d) => `${lastName(d.nameOf(d.fav))} ${pct(Math.max(d.p_dem, 1 - d.p_dem))}`}
  ], {filters: [
    {key: "office", label: "All offices", options: [["SEN", "Senate"], ["GOV", "Governor"], ["HOUSE", "House"]], test: (d, v) => d.office === v},
    {key: "state", label: "All races", options: [["called", "Called"], ["open", "Not called"], ["upset", "Called against our forecast"]],
      test: (d, v) => (v === "called" ? Boolean(d.called) : v === "open" ? !d.called : d.called && d.called !== d.fav)}
  ], pageSize: 40, placeholder: "Search races, candidates, states"});
  tbl.classList.add("res-cards");
  display(tbl);
  display(html`<p class="caption">"vs. our forecast": the bar is the range our forecast gave an 80% chance, the tick our most likely result, and the dot the count so far (early counts can swing a lot as different kinds of ballots come in). Margins are between the two main sides only.</p>`);
}
```

## When polls close

```js
const waves = d3.groups(contested, (r) => (CLOSE[r.state_po] ?? [21, 21])[0]).sort((a, b) => a[0] - b[0]);
display(html`<div class="table-wrap"><table class="wsu-table waves">
  <thead><tr><th>Eastern Time</th><th>States</th><th>Senate and governor races</th><th class="num">House races</th></tr></thead>
  <tbody>${waves.map(([h, list]) => {
    const states = [...new Set(list.map((r) => r.state_po))].sort();
    const big = list.filter((r) => r.office !== "HOUSE").sort((a, b) => a.state_po.localeCompare(b.state_po));
    return html`<tr><td class="nowrap"><b>${clock(h)}</b></td>
      <td>${states.map((s, i) => html`${i ? ", " : ""}${s}${CLOSE[s][1] > CLOSE[s][0] ? html`<sup title="last polls close at ${clock(CLOSE[s][1])}">*</sup>` : ""}`)}</td>
      <td>${big.length ? big.map((r, i) => html`${i ? ", " : ""}${raceLink(r, `${r.state_po} ${officeLabel[r.office].slice(0, 3)}${r.special ? " (sp.)" : ""}`)}`) : html`<span class="muted">–</span>`}</td>
      <td class="num">${list.filter((r) => r.office === "HOUSE").length}</td></tr>`;
  })}</tbody></table></div>`);
```

<p class="caption">When each state's first polls close. <sup>*</sup>States that span two time zones, where the rest close an hour later (hover for the time); results often wait until all of a state's polls have closed. Alaska's and Hawaii's polls close at midnight Eastern, and the far western Aleutian Islands at 1 a.m. Poll-closing times from <a href="https://www.thegreenpapers.com/G26/closing.phtml?format=gc">The Green Papers</a>.</p>

```js
const watch = [...contested].filter((r) => r.office !== "HOUSE" || Math.abs(r.p_dem - 0.5) < 0.2)
  .sort((a, b) => (b.control_leverage ?? 0) - (a.control_leverage ?? 0) || Math.abs(a.p_dem - 0.5) - Math.abs(b.p_dem - 0.5))
  .filter((r) => Math.abs(r.p_dem - 0.5) < 0.35).slice(0, 12)
  // in the order results start coming in: first poll closing, then last, then importance (kept from above)
  .map((r, i) => ({r, i, when: CLOSE[r.state_po] ?? [21, 21]}))
  .sort((a, b) => a.when[0] - b.when[0] || a.when[1] - b.when[1] || a.i - b.i)
  .map((x) => x.r);
const closeText = (st) => { const [a, b] = CLOSE[st] ?? [21, 21]; return b > a ? `${clock(a)} (rest ${clock(b)})` : clock(a); };
const rowOf = new Map(rows.map((d) => [d.race_id, d]));
function watchTable() {
  return html`<div class="res-cards"><h2>Races to watch</h2><p class="caption">The races most likely to decide control of the House or Senate in our forecast, in the order their polls close${started ? ", with the count as it comes in" : ", so the first results come first"}.</p>
  <div class="table-wrap"><table class="wsu-table">
    <thead>${started
      ? html`<tr><th>Polls close (ET)</th><th>Race</th><th>Result so far</th><th class="num">Counted</th><th>vs. our forecast</th><th>Our forecast</th></tr>`
      : html`<tr><th>Polls close (ET)</th><th>Race</th><th>Our forecast</th></tr>`}</thead>
    <tbody>${watch.map((r) => {
      // whole rows only: table cells built on their own are dropped by the browser's HTML parser
      const d = rowOf.get(r.race_id);
      const odds = html`${chip(d.tagOf(d.fav))} ${lastName(d.nameOf(d.fav))} ${pct(Math.max(r.p_dem, 1 - r.p_dem))}`;
      return started
        ? html`<tr><td class="c-close nowrap">${closeText(r.state_po)}</td><td class="c-label">${raceLink(r, raceName(r))}</td>
            <td class="c-status">${status(d)}</td><td class="c-pct num">${d.counted ? `${d.x.pct ?? 0}%` : ""}</td>
            <td class="c-range">${rangeBar(d)}</td><td class="c-p_dem">${odds}</td></tr>`
        : html`<tr><td class="c-close nowrap">${closeText(r.state_po)}</td><td class="c-label">${raceLink(r, raceName(r))}</td>
            <td class="c-p_dem">${odds}</td></tr>`;
    })}</tbody>
  </table></div></div>`;
}
if (!started) display(watchTable());
```

<p class="caption">Election-night results from <a href="https://civicapi.org">civicAPI</a>, which compiles them from state and local election offices. They are shown for comparison only and are not official; official results come from each state after its canvass. Louisiana's six House races put every candidate on the November 3 ballot; where no one wins a majority, the top two meet in a December 12 runoff, so some may stay uncalled until then.</p>
