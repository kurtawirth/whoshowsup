---
title: Election night
---

```js
import {tokens, pct, date, sides, raceLink, raceHref, raceTable, withSearch, hexMap, stateMap, shareRow} from "./components/wsu.js";
import {liveStream, liveOdds, raceMath, countiesOf, fetchRace, nightRead} from "./components/live.js";
import {racePanel, finish, sideText, lastName, k} from "./components/night.js";
const liveModel = FileAttachment("data/live_model.json").json();
const races = FileAttachment("data/races.json").json();
const top = FileAttachment("data/topline.json").json();
const liveFile = FileAttachment("data/live.json");
const bench = FileAttachment("data/benchmarks.json").json();
const layout = FileAttachment("data/hexmap.json").json();
const topo = FileAttachment("data/states-albers-10m.json").json();
const statesMeta = FileAttachment("data/states.json").json();
```

```js
// Open at the top. The races draw only after the data loads, so for a moment the page is just its header and
// footer; a browser that restores or nudges the scroll position then can pin the view to the footer and leave the
// reader at the bottom once everything appears. So: no scroll restoring here, and back to the top after the first
// full draw unless the reader has already scrolled, or the address names a race (#senate-tx), which opens on it.
const opening = {done: false, touched: false, race: /^#(senate|house|governor)-/.test(location.hash)};
if (!opening.race) { history.scrollRestoration = "manual"; scrollTo(0, 0); }
for (const ev of ["wheel", "touchstart", "keydown", "mousedown"]) addEventListener(ev, () => (opening.touched = true), {once: true, passive: true});
```

<style>#observablehq-footer { overflow-anchor: none; } #observablehq-main { min-height: 100vh; }</style>

```js
// Results: civicAPI directly during the night (every reader shares its cached answer), with the copy our poller
// publishes every few minutes as the fallback (components/live.js). ?direct in the address turns the direct feed on early, for testing.
const live = liveStream(liveFile, races, liveModel.civic, {Generators, force: new URLSearchParams(location.search).has("direct")});
```

```js
// What the reader has open (tab, map view, expanded races): kept here, outside the cells that redraw with every
// update, so a new count doesn't close what someone is reading.
const TABS = [["overview", "Overview"], ["senate", "Senate"], ["house", "House"], ["governors", "Governors"]];
// The address can name a tab (#house) or a race (#senate-tx), which opens on its chamber's tab, already expanded.
const hash = location.hash.slice(1);
const hashTab = TABS.some(([k]) => k === hash) ? hash : /^senate-/.test(hash) ? "senate" : /^house-/.test(hash) ? "house" : /^governor-/.test(hash) ? "governors" : null;
const ui = {tab: hashTab ?? "overview", mapMode: {overview: "lead", senate: "lead", house: "lead", governors: "lead"}, mapOffice: {overview: "SEN"},
  open: hashTab && hashTab !== hash ? {[hashTab]: new Set([hash])} : {}};
const openSet = (k) => (ui.open[k] ??= new Set());
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
// one row per race: our forecast, the latest count, and what's left (components/live.js raceMath)
const base = withSearch(contested).map((r) => {
  const s = sides(r), x = L[r.race_id] ?? {};
  const counted = (x.d ?? 0) + (x.r ?? 0) > 0;
  const lead = counted ? (x.margin >= 0 ? "D" : "R") : null;
  const tagOf = (side) => (side === "D" ? s.dTag : s.rTag);
  const nameOf = (side) => (side === "D" ? s.d : s.r);
  const b = r.office !== "HOUSE" ? bench[r.race_id] ?? null : null;
  const m = raceMath(r, x, b, countiesOf(x));
  return {...r, s, x, m, b, counted, lead, called: x.called ?? null, tagOf, nameOf,
    fav: r.p_dem >= 0.5 ? "D" : "R", closes: (CLOSE[r.state_po] ?? [21, 21])[1],
    flipped: Boolean(x.called && r.incumbent_party && tagOf(x.called) !== r.incumbent_party)};
});
// Live odds (components/live.js): the races that have finished counting move every race still out, and each
// race's own partial count moves its own odds; mFinal is where we now expect each margin to finish
const odds = started ? liveOdds(races, liveModel, live.races, {partial: Object.fromEntries(base.map((d) => [d.race_id, d.m]))}) : null;
const rows = base.map((d) => ({...d, pNow: odds?.p?.[d.race_id] ?? null, mNow: odds?.mFinal?.[d.race_id] ?? null}));
const rowOf = new Map(rows.map((d) => [d.race_id, d]));
const calledRows = rows.filter((d) => d.called);
const right = calledRows.filter((d) => d.called === d.fav);
const settled = rows.filter((d) => d.counted && (d.x.pct ?? 0) >= 95);
const inRange = settled.filter((d) => d.x.margin >= d.margin_p10 && d.x.margin <= d.margin_p90);
const read = started ? nightRead(rows.filter((d) => d.office !== "HOUSE").map((d) => ({r: d, m: d.m}))) : null;
// how much a race matters for control: its tipping-point chance (Senate, House); governors: how close we had it
const importance = (d) => (d.office === "GOV" ? 0.5 - Math.abs(d.p_dem - 0.5) : d.tipping_point ?? 0);
```

${live.mode === "simulation" ? html`<div class="sim-banner"><b>Rehearsal.</b> These are made-up results for testing the page, not real votes.</div>` : live.mode === "practice" ? html`<div class="sim-banner"><b>Practice run.</b> Real counts from civicAPI, fetched to test the page; not published.</div>` : ""}

<p class="kicker">Election night · November 3, 2026${asof && started ? ` · Updated ${etTime(asof)}${live.source === "direct" ? " · live from civicAPI" : ""}` : ""}</p>

# ${started ? `${live.called} of ${live.total} races called` : "Results will appear here on election night"}

<p class="dek">${started
  ? html`Vote counts from <a href="https://civicapi.org">civicAPI</a>, refreshed every few minutes, next to what our forecast expected. Click any race for its full count: the votes left, what each side needs of them, and turnout against what we expected. This page updates on its own. Calls are civicAPI's, not ours.`
  : html`From the first poll closings at 6 p.m. Eastern on November 3, the count for every House, Senate and governor race will appear here every few minutes, next to what our forecast expected, with a running tally of the House and Senate. ${(() => { const days = Math.ceil((new Date("2026-11-03T23:00:00Z") - new Date()) / 864e5); return days > 0 ? `That's ${days} day${days === 1 ? "" : "s"} away.` : ""; })()}`}</p>

${shareRow("https://whoshowsup.net/results", started ? "Live 2026 election results and odds, race by race, from Who Shows Up" : "2026 election night results, race by race, from Who Shows Up")}

```js
// ---------- pieces every tab uses ----------
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
const TALLY = {
  SEN: () => tallyBar("Senate", tally("SEN", {D: 34, R: 31}), 51, 100, "51 seats for control (50 plus the vice president for Republicans); includes the 65 seats not up this year"),
  HOUSE: () => tallyBar("House", tally("HOUSE"), 218, 435, "218 seats for control; includes seats where only one party is on the ballot"),
  GOV: () => tallyBar("Governors", tally("GOV"), null, 36, "36 races")
};
const party = (p) => (p >= 0.5 ? `D ${pct(p)}` : `R ${pct(1 - p)}`);
const oddsStat = (label, now, morning) => html`<div class="s"><div class="k">${label}</div><div class="v">${party(now)}</div><div class="muted">this morning: ${party(morning)}</div></div>`;

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
// "Talarico running 1.2 points ahead of our forecast", from the counted counties where we have them
function gapText(d) {
  const g = d.m.gap;
  if (g == null) return "";
  if (Math.abs(g) < 0.5) return "Right on our forecast";
  return `${lastName(d.nameOf(g > 0 ? "D" : "R"))} running ${Math.abs(g).toFixed(1)} ahead of forecast`;
}
const status = (d) => (d.called ? html`<span class="res-called">${chip(d.tagOf(d.called))} ${lastName(d.nameOf(d.called))} wins</span>`
  : d.counted ? html`<span>${sideText(d, d.x.margin)}${leftText(d)}</span>` : html`<span class="muted">No votes yet (polls close ${clock((CLOSE[d.state_po] ?? [21])[0])})</span>`);
// "272,000 of ~4.7 million votes counted": the count against the turnout we expect
function leftText(d) {
  const f = finish(d, d.m);
  if (!f || !d.counted) return "";
  return html`<div class="adj">${k(d.m.counted)} of ~${k(f.total)} votes counted</div>`;
}
// the number people come for: our chance now, big; this morning's, small
const oddsCell = (d) => {
  const morning = `${lastName(d.nameOf(d.fav))} ${pct(Math.max(d.p_dem, 1 - d.p_dem))}`;
  if (d.called) return html`<span><span class="odds-now">${chip(d.tagOf(d.called))} ${lastName(d.nameOf(d.called))} won</span><div class="adj">this morning: ${morning}</div></span>`;
  const p = d.pNow ?? d.p_dem, side = p >= 0.5 ? "D" : "R";
  return html`<span><span class="odds-now">${chip(d.tagOf(side))} ${lastName(d.nameOf(side))} ${pct(Math.max(p, 1 - p))}</span>${d.pNow != null ? html`<div class="adj">this morning: ${morning}</div>` : ""}</span>`;
};
const COLUMNS = [
  {key: "label", label: "Race", sort: true, sortValue: (d) => `${d.state_name} ${String(d.district ?? 0).padStart(2, "0")}`, render: (d) => html`<span class="rd-name">${raceName(d)}</span>`},
  {key: "status", label: "Result so far", render: status},
  {key: "pct", label: "Counted", num: true, sort: true, defaultDir: -1, sortValue: (d) => d.x.pct ?? -1, render: (d) => (d.counted ? `${d.x.pct ?? 0}%` : "")},
  {key: "range", label: "vs. our forecast", render: (d) => html`<span>${rangeBar(d)}${gapText(d) ? html`<div class="adj">${gapText(d)}</div>` : ""}</span>`},
  {key: "p_dem", label: "Chance to win", sort: true, sortValue: (d) => { const p = d.pNow ?? d.p_dem; return Math.max(p, 1 - p); }, render: oddsCell}
];
const STATUS_FILTER = {key: "status", label: "Every race", options: [["open", "Not called yet"], ["called", "Called"], ["flip", "Seats that flipped"], ["against", "Leader isn't our favorite"]],
  test: (d, v) => (v === "open" ? !d.called : v === "called" ? Boolean(d.called) : v === "flip" ? d.flipped
    : (d.called ?? d.lead) && (d.called ?? d.lead) !== d.fav)};
const stateFilter = (list) => ({key: "st", label: "All states", options: [...new Set(list.map((d) => d.state_po))].sort().map((s) => [s, list.find((d) => d.state_po === s).state_name]),
  test: (d, v) => d.state_po === v});
const topRaces = (office, n) => rows.filter((d) => d.office === office).sort((a, b) => importance(b) - importance(a)).slice(0, n);
const SORTS = [
  {label: "Most important for control", value: (d) => importance(d), dir: -1},
  {label: "Closest count", value: (d) => (d.called ? 900 : d.counted ? Math.abs(d.x.margin) : 999), dir: 1},
  {label: "Least counted", value: (d) => (d.called ? 999 : d.x.pct ?? -1), dir: 1},
  {label: "State A–Z", value: (d) => `${d.state_name} ${String(d.district ?? 0).padStart(2, "0")}`, dir: 1}
];
```

```js
// Before the night: the races to watch, most important first, with when their polls close
const closeText = (st) => { const [a, b] = CLOSE[st] ?? [21, 21]; return b > a ? `${clock(a)} (rest ${clock(b)})` : clock(a); };
function watchTable() {
  const watch = [...topRaces("SEN", 7), ...topRaces("HOUSE", 5), ...topRaces("GOV", 3)];
  return html`<div class="res-cards"><h2>Races to watch</h2><p class="caption">The Senate and House races likeliest to decide control in our forecast, and the closest governor's races, with when each state's polls close.</p>
  <div class="table-wrap"><table class="wsu-table">
    <thead><tr><th>Race</th><th>Polls close (ET)</th><th>Our forecast</th></tr></thead>
    <tbody>${watch.map((d) => html`<tr><td class="c-label">${raceLink(d, raceName(d))}</td><td class="c-close nowrap">${closeText(d.state_po)}</td>
      <td class="c-p_dem">${chip(d.tagOf(d.fav))} ${lastName(d.nameOf(d.fav))} ${pct(Math.max(d.p_dem, 1 - d.p_dem))}</td></tr>`)}</tbody>
  </table></div></div>`;
}
function schedule() {
  const waves = d3.groups(contested, (r) => (CLOSE[r.state_po] ?? [21, 21])[0]).sort((a, b) => a[0] - b[0]);
  return html`<div class="table-wrap"><table class="wsu-table waves">
    <thead><tr><th>Eastern Time</th><th>States</th><th>Senate and governor races</th><th class="num">House races</th></tr></thead>
    <tbody>${waves.map(([h, list]) => {
      const states = [...new Set(list.map((r) => r.state_po))].sort();
      const big = list.filter((r) => r.office !== "HOUSE").sort((a, b) => a.state_po.localeCompare(b.state_po));
      return html`<tr><td class="nowrap"><b>${clock(h)}</b></td>
        <td>${states.map((s, i) => html`${i ? ", " : ""}${s}${CLOSE[s][1] > CLOSE[s][0] ? html`<sup title="last polls close at ${clock(CLOSE[s][1])}">*</sup>` : ""}`)}</td>
        <td>${big.length ? big.map((r, i) => html`${i ? ", " : ""}${raceLink(r, `${r.state_po} ${officeLabel[r.office].slice(0, 3)}${r.special ? " (sp.)" : ""}`)}`) : html`<span class="muted">–</span>`}</td>
        <td class="num">${list.filter((r) => r.office === "HOUSE").length}</td></tr>`;
    })}</tbody></table></div>
    <p class="caption">When each state's first polls close. <sup>*</sup>States that span two time zones, where the rest close an hour later (hover for the time); results often wait until all of a state's polls have closed. Alaska's and Hawaii's polls close at midnight Eastern, and the far western Aleutian Islands at 1 a.m. Poll-closing times from <a href="https://www.thegreenpapers.com/G26/closing.phtml?format=gc">The Green Papers</a>.</p>`;
}
```

```js
// ---------- the drill-in: one race's full count (components/night.js, the same panel as the race pages) ----------
function detail(d) {
  const el = html`<div class="race-detail"></div>`;
  const draw = (counties) => el.replaceChildren(...racePanel(d, counties));
  const cs = countiesOf(d.x);
  draw(cs);
  // without counties in our published copy, ask civicAPI for this one race while it's open
  const cid = liveModel.civic?.[d.race_id];
  if (!cs && d.b && cid && d.counted && live.mode !== "simulation") {
    fetchRace(d, cid).then(({counties}) => { if (counties.size) draw(counties); }).catch(() => {});
  }
  return el;
}
```

```js
// ---------- maps ----------
function fillLead(r) {
  const d = rowOf.get(r.race_id);
  if (!d) return r.race_type === "same_party" ? (r.race_note === "D" ? t["Safe D"] : t["Safe R"]) : t.hair;  // decided before the night
  const tag = d.called ? d.tagOf(d.called) : d.lead ? d.tagOf(d.lead) : null;
  if (!tag) return t.hair;
  if (tag === "I") return t.ind;
  return d.called ? (tag === "D" ? t["Safe D"] : t["Safe R"]) : (tag === "D" ? t["Lean D"] : t["Lean R"]);
}
const GAP_STEPS = [[6, "Safe D"], [3, "Likely D"], [1, "Lean D"], [-1, "Toss-up"], [-3, "Lean R"], [-6, "Likely R"], [-Infinity, "Safe R"]];
function fillGap(r) {
  const d = rowOf.get(r.race_id);
  if (!d || !d.counted || (d.x.pct ?? 0) < 10) return t.surface;
  const g = d.m.gap ?? d.x.margin - d.margin_median;
  return t[GAP_STEPS.find(([lo]) => g >= lo)[1]];
}
function tipRows(r) {
  const d = rowOf.get(r.race_id);
  if (!d) return [["t-title", raceName(r)], ["t-sub", r.race_type === "same_party" ? `Only ${r.race_note === "D" ? "Democrats" : "Republicans"} on the ballot` : "No race"]];
  const rows_ = [["t-title", raceName(d)]];
  const p = d.pNow ?? d.p_dem;
  rows_.push(["t-val", d.called ? `${lastName(d.nameOf(d.called))} won` : `${lastName(d.nameOf(p >= 0.5 ? "D" : "R"))} ${pct(Math.max(p, 1 - p))} to win${d.pNow != null ? " now" : ""}`]);
  rows_.push(["t-sub", d.counted ? `Count: ${sideText(d, d.x.margin)}` : "No votes yet"]);
  if (d.counted) rows_.push(["t-sub", `${d.x.pct ?? 0}% counted`]);
  if (gapText(d)) rows_.push(["t-sub", gapText(d)]);
  rows_.push(["t-sub", "Click for the full count"]);
  return rows_;
}
// our chance to win (live, or this morning's), in the forecast pages' rating colors
const CHANCE_STEPS = [[0.95, "Safe"], [0.75, "Likely"], [0.6, "Lean"], [0.5, "Toss-up"]];
function chanceFill(d, p) {
  const side = p >= 0.5 ? "D" : "R", q = Math.max(p, 1 - p);
  if (d.tagOf(side) === "I") return t.ind;
  const step = CHANCE_STEPS.find(([lo]) => q >= lo)[1];
  return t[step === "Toss-up" ? "Toss-up" : `${step} ${side}`];
}
function fillChance(r) {
  const d = rowOf.get(r.race_id);
  if (!d) return r.race_type === "same_party" ? (r.race_note === "D" ? t["Safe D"] : t["Safe R"]) : t.hair;
  return chanceFill(d, d.called ? (d.called === "D" ? 1 : 0) : d.pNow ?? d.p_dem);
}
function fillMorning(r) {
  const d = rowOf.get(r.race_id);
  if (!d) return r.race_type === "same_party" ? (r.race_note === "D" ? t["Safe D"] : t["Safe R"]) : t.hair;
  return chanceFill(d, d.p_dem);
}
const MAP_MODES = [["lead", "Who's ahead", fillLead], ["chance", "Chance to win now", fillChance], ["gap", "Against our forecast", fillGap], ["morning", "This morning's forecast", fillMorning]];
function legend(mode, office) {
  const sw = (c, label) => html`<span><i style="background:${c}"></i>${label}</span>`;
  const called = mode === "morning" ? "" : office === "HOUSE" ? html`<span><b class="call-dot"></b>called</span>` : html`<span><b class="call-check">✓</b>called</span>`;
  if (mode === "lead") return html`<div class="map-legend">${sw(t["Safe D"], "Democrat won")}${sw(t["Lean D"], "Democrat leading")}${sw(t.hair, "No votes yet")}${sw(t["Lean R"], "Republican leading")}${sw(t["Safe R"], "Republican won")}${called}</div>`;
  if (mode === "gap") return html`<div class="map-legend">${sw(t["Safe D"], "6+ pts bluer")}${sw(t["Lean D"], "1–3 bluer")}${sw(t["Toss-up"], "within 1")}${sw(t["Lean R"], "1–3 redder")}${sw(t["Safe R"], "6+ pts redder")}${sw(t.surface, "under 10% counted")}${called}</div>`;
  return html`<div class="map-legend">${sw(t["Safe D"], "D 95%+")}${sw(t["Likely D"], "D 75–95%")}${sw(t["Lean D"], "D 60–75%")}${sw(t["Toss-up"], "under 60% either way")}${sw(t["Lean R"], "R 60–75%")}${sw(t["Likely R"], "R 75–95%")}${sw(t["Safe R"], "R 95%+")}${mode === "chance" ? sw(t.ind, "independent favored") : ""}${called}</div>`;
}
const MAP_NOTES = {
  lead: "Solid colors (and check marks) are races civicAPI has called; lighter ones, who leads the count so far.",
  chance: "Our live chance to win: this morning's forecast, moved by each race's own count and by the races that have finished counting. Called races count for their winners.",
  gap: "Each race's count against what our forecast expected",
  morning: "Our forecast as of this morning, before any votes were counted."
};
// a map with its four views; clicking a state or district opens that race in `table`. With offices, the map
// also switches between the Senate, the House and governors (the Overview tab).
function mapPanel(key, office, table, {offices = null} = {}) {
  const box = html`<div class="map-panel"></div>`;
  const officeSeg = offices ? html`<div class="seg" role="group" aria-label="Office"></div>` : null;
  const toggle = html`<div class="seg" role="group" aria-label="Map view"></div>`;
  const body = html`<div></div>`, note = html`<p class="caption"></p>`;
  const draw = () => {
    const mode = ui.mapMode[key] ?? "lead", off = offices ? ui.mapOffice[key] ?? office : office;
    if (offices) officeSeg.replaceChildren(...offices.map(([v, label]) => {
      const b = html`<button type="button" aria-pressed=${String(off === v)}>${label}</button>`;
      b.onclick = () => { ui.mapOffice[key] = v; draw(); };
      return b;
    }));
    toggle.replaceChildren(...MAP_MODES.map(([v, label]) => {
      const b = html`<button type="button" aria-pressed=${String(mode === v)}>${label}</button>`;
      b.onclick = () => { ui.mapMode[key] = v; draw(); };
      return b;
    }));
    // sized so the buttons, the map and its key fit on one screen
    const fitH = Math.max(340, (typeof innerHeight === "number" ? innerHeight : 900) - 220);
    const w = Math.min(width, off === "HOUSE" ? 1150 : 1050, off === "HOUSE" ? fitH / 0.66 : (fitH * 975) / 610);
    const opts = {width: w, fillRace: MAP_MODES.find(([v]) => v === mode)[2], tipRows, onPick: (r) => rowOf.has(r.race_id) && table.reveal(r.race_id),
      mark: mode === "morning" ? null : (r) => Boolean(rowOf.get(r.race_id)?.called)};
    body.replaceChildren(off === "HOUSE" ? hexMap(races, layout, opts) : stateMap(races, topo, statesMeta, {office: off, ...opts}), legend(mode, off));
    note.textContent = `${MAP_NOTES[mode]}${mode === "gap" ? (off === "HOUSE" ? ": for House districts, our most likely margin for the whole district, so early counts can mislead." : ", in the counties counted so far.") : ""} Click a ${off === "HOUSE" ? "district" : "state"} for its full count.`;
  };
  draw();
  box.append(...(offices ? [html`<div class="seg-row">${officeSeg}${toggle}</div>`] : [toggle]), body, note);
  return box;
}
function chamberTable(key, list, {pageSize = 25} = {}) {
  return raceTable(list, COLUMNS, {filters: [STATUS_FILTER, stateFilter(list)], sorts: SORTS, pageSize, detail, openSet: openSet(key),
    placeholder: "Search candidates, states, districts"});
}
```

```js
// ---------- tabs ----------
function tabBar() {
  const bar = html`<div class="tabs" role="tablist" aria-label="Results by office"></div>`;
  for (const [key, label] of TABS) {
    const b = html`<button type="button" role="tab" id="tab-${key}" aria-selected=${String(ui.tab === key)}>${label}</button>`;
    b.onclick = () => {
      ui.tab = key;
      history.replaceState(history.state, "", `#${key}`);
      for (const x of bar.children) x.setAttribute("aria-selected", String(x === b));
      for (const [k_] of TABS) document.getElementById(`panel-${k_}`)?.toggleAttribute("hidden", k_ !== key);
      document.getElementById(`panel-${key}`)?.dispatchEvent(new Event("show"));
    };
    bar.append(b);
  }
  return bar;
}
function panel(key, build) {
  const el = html`<section class="tab-panel" id="panel-${key}" role="tabpanel" aria-labelledby="tab-${key}"></section>`;
  let built = false;
  const show = () => { if (!built) { built = true; el.append(...build()); } };
  el.addEventListener("show", show);
  if (ui.tab === key) show(); else el.hidden = true;
  return el;
}
```

```js
// ---------- the Overview tab ----------
function overview() {
  const parts = [];
  if (odds) parts.push(html`<div class="stat-row">
    ${oddsStat("Senate control", odds.pSen, top.p_senate_d)}
    ${oddsStat("House control", odds.pHouse, top.p_house_d)}
    ${read ? html`<div class="s"><div class="k">Counted counties vs. our forecast</div><div class="v">${Math.abs(read.gap) < 0.25 ? "Even" : `${read.gap > 0 ? "D" : "R"} +${Math.abs(read.gap).toFixed(1)}`}</div><div class="muted">${Math.abs(read.gap) < 0.25 ? "right on our forecast" : `points ${read.gap > 0 ? "more Democratic" : "more Republican"} than we expected`}</div></div>` : ""}
    ${read?.turnout != null ? html`<div class="s"><div class="k">Turnout vs. our expectation</div><div class="v">${read.turnout >= 0 ? "+" : "−"}${Math.round(Math.abs(read.turnout) * 100)}%</div><div class="muted">${read.turnoutD != null && read.turnoutR != null ? `D-leaning counties ${read.turnoutD >= 0 ? "+" : "−"}${Math.round(Math.abs(read.turnoutD) * 100)}%, R-leaning ${read.turnoutR >= 0 ? "+" : "−"}${Math.round(Math.abs(read.turnoutR) * 100)}%` : "in counted counties"}</div></div>` : ""}
  </div>`);
  if (started) parts.push(leftToCount());
  if (odds) parts.push(html`<p class="caption">${odds.used
    ? `Live odds: based on the ${odds.used} race${odds.used === 1 ? "" : "s"} at least 95% counted, results are running about ${Math.abs(odds.shift).toFixed(1)} points more ${odds.shift >= 0 ? "Democratic" : "Republican"} than our forecast nationally (more or less in some regions and states). We move every race still out by that much, count called races for their winners, and play out the rest of the night thousands of times.`
    : "Live odds: until races finish counting, the night's overall shift comes from our forecast."} Each race's own count also moves its odds, more as more of it comes in: where we have county results, we compare the counted counties with our forecast and fill in the counties still out from their benchmarks.${read ? ` The counted-counties and turnout figures compare every county that has reported in the ${read.states} states with Senate or governor races counting against our county benchmarks; they move earlier than the live odds, and can mislead early, when one kind of ballot dominates the count.` : ""} Not a call: estimates that will swing as results come in.</p>`);
  parts.push(html`<div class="tallies">${TALLY.SEN()}${TALLY.HOUSE()}${TALLY.GOV()}</div>`);
  // the map, all three offices; clicking a race opens it in "Find any race" below
  const all = raceTable(rows, COLUMNS, {filters: [{key: "office", label: "All offices", options: [["SEN", "Senate"], ["GOV", "Governor"], ["HOUSE", "House"]], test: (d, v) => d.office === v}, STATUS_FILTER],
    sorts: [SORTS[1], ...SORTS.filter((x, i) => i !== 1)], pageSize: 10, detail, openSet: openSet("all"), placeholder: "Search candidates, states, districts"});
  all.classList.add("res-cards");
  parts.push(mapPanel("overview", "SEN", all, {offices: [["SEN", "Senate"], ["HOUSE", "House"], ["GOV", "Governors"]]}));
  // the races that matter most for control, then any race at all
  const keyRaces = [...topRaces("SEN", 7), ...topRaces("HOUSE", 5), ...topRaces("GOV", 3)];
  parts.push(html`<h2>Key races</h2><p class="caption">The Senate and House races likeliest to decide control in our forecast, and the closest governor's races. Click a race for its full count.</p>`);
  const kt = raceTable(keyRaces, COLUMNS, {search: false, pageSize: 20, detail, openSet: openSet("key"), noun: "race"});
  kt.classList.add("res-cards");
  parts.push(kt);
  if (calledRows.length) parts.push(...scorecard());
  parts.push(html`<h2>Find any race</h2>`);
  parts.push(all);
  parts.push(caption());
  parts.push(html`<details class="schedule"><summary>When polls close</summary>${schedule()}</details>`);
  return parts;
}
// ---------- what's left to count, in plain words ----------
// Votes: every contested House district (together they cover nearly the whole country's vote), each counted up
// to where its own count says it will end, or to our expected turnout before it has much in.
function leftToCount() {
  const house = rows.filter((d) => d.office === "HOUSE");
  const done = (d) => (d.x.pct ?? 0) >= 100;
  const total = (d) => (done(d) ? d.m.counted : Math.max(d.m.projected ?? d.expected_votes ?? 0, d.m.counted));
  const left = (d) => total(d) - d.m.counted;
  const all = d3.sum(house, total), out = d3.sum(house, left), got = all - out;
  const piles = d3.rollups(house, (v) => d3.sum(v, left), (d) => d.state_name).filter(([, n]) => n >= 50000).sort((a, b) => b[1] - a[1]).slice(0, 4);
  const open = (o) => rows.filter((d) => d.office === o && !d.called).length;
  const [s, h, g] = [open("SEN"), open("HOUSE"), open("GOV")];
  const uncalled = [s && `${s} Senate`, h && `${h} House`, g && `${g} governor's`].filter(Boolean);
  // states whose last polls haven't closed yet, by the clock of the latest update (hours after midnight ET, Nov. 3)
  const hr = asof ? (asof - Date.UTC(2026, 10, 3, 5)) / 36e5 : null;
  const stillOpen = hr == null ? [] : Object.entries(CLOSE).filter(([, [, last]]) => last > hr).sort((a, b) => a[1][1] - b[1][1]);
  const list = (xs) => (xs.length < 3 ? xs.join(" and ") : `${xs.slice(0, -1).join(", ")} and ${xs.at(-1)}`);
  const share = all ? got / all : 0;
  return html`<div class="left-box"><h3>What's left to count</h3>
    <div class="left-bar" role="img" aria-label="${Math.round(share * 100)}% of the expected vote counted"><b style="flex:${share}"></b><i></i></div>
    <ul>
      <li><b>Votes:</b> ${out > 0 ? html`about <b>${k(out)}</b> still to count, roughly ${Math.round((100 * out) / all)}% of the ${k(all)} we expect in all.` : "all in, or close to it."}</li>
      <li><b>Races:</b> ${uncalled.length ? html`${list(uncalled)} race${s + h + g === 1 ? "" : "s"} not called yet.` : "every race has been called."}</li>
      ${piles.length ? html`<li><b>Most of the uncounted vote:</b> ${list(piles.map(([st, n]) => `${st} (${k(n)})`))}.</li>` : ""}
      ${stillOpen.length ? html`<li><b>Polls still open</b> in ${stillOpen.length} state${stillOpen.length === 1 ? "" : "s"}: ${list(stillOpen.map(([po]) => statesMeta.names?.[po] ?? po))}. The last close at ${clock(d3.max(stillOpen, ([, [, last]]) => last))} ET.</li>` : ""}
    </ul></div>`;
}
// ---------- called races against our forecast ----------
function scorecard() {
  const wonP = (d) => (d.called === "D" ? d.p_dem : 1 - d.p_dem);  // the chance we gave the winner this morning
  const upsets = calledRows.filter((d) => d.called !== d.fav);
  const outside = settled.filter((d) => !(d.x.margin >= d.margin_p10 && d.x.margin <= d.margin_p90));
  const list = calledRows.map((d) => ({...d, wonP: wonP(d), surprise: d.called !== d.fav,
    inside: (d.x.pct ?? 0) >= 95 ? d.x.margin >= d.margin_p10 && d.x.margin <= d.margin_p90 : null}));
  const cols = [
    {key: "label", label: "Race", sort: true, sortValue: (d) => `${d.state_name} ${String(d.district ?? 0).padStart(2, "0")}`, render: (d) => html`<span class="rd-name">${raceName(d)}</span>`},
    {key: "winner", label: "Winner", render: (d) => html`<span class="odds-now">${chip(d.tagOf(d.called))} ${lastName(d.nameOf(d.called))}</span>${d.surprise ? html` <span class="pill-upset">Upset</span>` : ""}`},
    {key: "wonP", label: "We gave them", num: true, sort: true, render: (d) => pct(d.wonP)},
    {key: "result", label: "Result", num: true, sort: true, sortValue: (d) => Math.abs(d.x.margin), render: (d) => html`<span>by ${Math.abs(d.x.margin) < 0.05 ? "under 0.1" : Math.abs(d.x.margin).toFixed(1)}${(d.x.pct ?? 0) < 95 ? html`<div class="adj">${d.x.pct ?? 0}% counted</div>` : ""}</span>`},
    {key: "expected", label: "We expected", num: true, render: (d) => sideText(d, d.margin_median)},
    {key: "inside", label: "Inside our 80% range", render: (d) => (d.inside == null ? html`<span class="muted">still counting</span>` : d.inside ? "Yes" : html`<b>No</b>`)}
  ];
  const tbl = raceTable(list, cols, {
    filters: [{key: "office", label: "All offices", options: [["SEN", "Senate"], ["GOV", "Governor"], ["HOUSE", "House"]], test: (d, v) => d.office === v},
      {key: "which", label: "Every called race", options: [["upset", "Upsets: our underdog won"], ["outside", "Outside our 80% range"]], test: (d, v) => (v === "upset" ? d.surprise : d.inside === false)}],
    sorts: [{label: "Biggest surprises first", value: (d) => d.wonP, dir: 1}, {label: "Closest results", value: (d) => Math.abs(d.x.margin), dir: 1}, {label: "State A–Z", value: (d) => `${d.state_name} ${String(d.district ?? 0).padStart(2, "0")}`, dir: 1}],
    pageSize: 10, detail, openSet: openSet("called"), noun: "called race", placeholder: "Search called races"});
  tbl.classList.add("score-table");
  const share = settled.length ? inRange.length / settled.length : null;
  return [html`<h2>Called races: how our forecast did</h2>`,
    html`<div class="stat-row">
      <div class="s"><div class="k">Our favorite won</div><div class="v">${right.length} of ${calledRows.length}</div><div class="muted">${pct(right.length / calledRows.length)} of called races${upsets.length ? `; ${upsets.length} upset${upsets.length === 1 ? "" : "s"}` : ""}</div></div>
      <div class="s"><div class="k">Inside our 80% range</div><div class="v">${settled.length ? `${inRange.length} of ${settled.length}` : "–"}</div><div class="muted">${share != null ? `${pct(share)} of races 95%+ counted; a well-calibrated forecast lands about 80%` : "races 95%+ counted"}</div></div>
    </div>`,
    html`<p class="caption">Every race civicAPI has called, next to what we said this morning. "We gave them" is the chance our forecast gave the winner before any votes were counted; an upset is a race our underdog won. Results are as counted so far, and margins are between the two main sides. ${outside.length ? `${outside.length} race${outside.length === 1 ? "" : "s"} finished outside our 80% range so far.` : ""}</p>`,
    tbl];
}
const caption = () => html`<p class="caption">"vs. our forecast": the bar is the range our forecast gave an 80% chance, the tick our most likely result, and the dot the count so far (early counts can swing a lot as different kinds of ballots come in). Margins are between the two main sides only.</p>`;

// ---------- a chamber's tab ----------
function chamber(key, office) {
  const list = rows.filter((d) => d.office === office);
  const parts = [];
  if (odds && office !== "GOV") parts.push(html`<div class="stat-row">${office === "SEN" ? oddsStat("Senate control", odds.pSen, top.p_senate_d) : oddsStat("House control", odds.pHouse, top.p_house_d)}</div>`);
  parts.push(html`<div class="tallies">${TALLY[office]()}</div>`);
  const table = chamberTable(key, list, {pageSize: office === "HOUSE" ? 25 : 40});
  table.classList.add("res-cards");
  parts.push(mapPanel(key, office, table));
  parts.push(html`<h2>Every ${office === "GOV" ? "governor's race" : office === "SEN" ? "Senate race" : "House race"}</h2>`);
  parts.push(table, caption());
  return parts;
}
```

```js
// ---------- the page ----------
if (started) {
  display(tabBar());
  display(panel("overview", overview));
  display(panel("senate", () => chamber("senate", "SEN")));
  display(panel("house", () => chamber("house", "HOUSE")));
  display(panel("governors", () => chamber("governors", "GOV")));
} else {
  display(watchTable());
  display(html`<h2>When polls close</h2>`);
  display(schedule());
}
// the first full draw: back to the top (see `opening` above); later updates leave the reader where they are
if (!opening.done) {
  opening.done = true;
  requestAnimationFrame(() => {
    if (opening.touched) return;
    if (opening.race) document.querySelector(`tr[data-id="${CSS.escape(location.hash.slice(1))}"]`)?.scrollIntoView({block: "start"});
    else scrollTo(0, 0);
  });
}
```



<p class="caption">Election-night results from <a href="https://civicapi.org">civicAPI</a>, which compiles them from state and local election offices. They are shown for comparison only and are not official; official results come from each state after its canvass. Louisiana's six House races put every candidate on the November 3 ballot; where no one wins a majority, the top two meet in a December 12 runoff, so some may stay uncalled until then.</p>
