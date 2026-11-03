---
title: Election night
---

```js
import {tokens, pct, margin, date, sides, raceLink, raceHref, raceTable, withSearch, hexMap, stateMap, shareRow, tip} from "./components/wsu.js";
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
  open: hashTab && hashTab !== hash ? {[hashTab]: new Set([hash])} : {},
  mem: {},          // each table's search, filters, sort and "Show more", kept across updates
  prev: {}, changedAt: {},  // each race's last count, and when it last changed (its row flashes)
  tables: {}};      // the tables now on the page, so the maps and "Find a race" can open a race in them
const openSet = (k) => (ui.open[k] ??= new Set());
const memOf = (k) => (ui.mem[k] ??= {});
```

```js
// "4 min ago" beside the update time, kept current between updates
const agoText = (t) => { const m = Math.floor((Date.now() - t) / 60000); return m < 0 || m > 360 ? "" : m < 1 ? " (just now)" : ` (${m} min ago)`; };
{
  const tick = setInterval(() => { for (const el of document.querySelectorAll(".ago")) el.textContent = agoText(+el.dataset.t); }, 20000);
  invalidation.then(() => clearInterval(tick));
}
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
const smooth = () => (matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");
```

```js
// Which ballots each state counts first, and which way its count has tended to move as the rest come in
// (mechanics, not a prediction), for the states with the closest Senate and governor races.
// From AP's 2026 "what to expect" notes, Votebeat, and state and local reporting (checked Nov. 2, 2026).
const COUNT_ORDER = {
  AK: "Election-night results include early in-person and Election Day votes; most mail ballots are counted over the following days and can arrive up to 10 days late. Any ranked-choice tally comes Nov. 18. Late ballots have moved results before, but not consistently toward either party.",
  AZ: "Early ballots received before Election Day are reported about an hour after polls close, then Election Day votes. Mail ballots dropped off on Election Day take days to count; they leaned Republican in 2020 and 2022 and Democratic in 2024.",
  FL: "Mail and early in-person votes post soon after polls close, then Election Day precincts; most of the vote is in by late evening. Mail has leaned Democratic and early in-person voting Republican, so first results are mixed, with no consistent late shift.",
  GA: "Early in-person and mail votes come shortly after 7 p.m., then Election Day votes; provisional and military ballots take days. Early returns have leaned Democratic and then moved toward Republicans: in 2024's presidential race, an early 11-point Democratic lead became a 2-point Republican win.",
  IA: "Most counties release absentee and early votes first, often with some Election Day votes, and counting usually finishes within hours. Early returns have tended to lean Democratic, so the count can move toward Republicans.",
  KS: "Nearly every county posts early and mail votes first, with Election Day votes added later in the night. Under a court order, mail postmarked by Election Day still counts if it arrives within three days.",
  ME: "Towns report all kinds of ballots together, slowly; many count by hand, and in 2024 about 90% was in by the next afternoon. The Senate race and the 2nd District may need a ranked-choice tally, which has usually come the following week.",
  MI: "First updates mix mail, early and Election Day votes; big counties such as Wayne, Oakland and Macomb report later, and Detroit can run into the next morning. In 2024's presidential race the Democrat led early, the Republican pulled ahead, and that lead then narrowed.",
  MN: "Absentee ballots are processed ahead of time but released with precinct results after 8 p.m. Hennepin County reports nearly everything at once; Ramsey and Dakota are slower. Counting usually finishes overnight.",
  NC: "Mail ballots post first after polls close at 7:30 p.m., then early in-person votes, then Election Day precincts until about 1 a.m.; nearly all of the vote is counted on election night.",
  NE: "Most counties release early and absentee votes first; about half, including Douglas and Lancaster, report few Election Day votes at first. In 2024, 90% was in by about 2 a.m. Central.",
  NH: "Absentee and in-person ballots are counted together, town by town, and many small towns count by hand; in 2024, 90% was in by about 1:45 a.m. Early swings reflect which towns report first, not the kind of ballot.",
  NV: "Early in-person votes and mail received before Election Day come first, a few hours after polls close. Mail postmarked by Election Day counts if it arrives by Nov. 7, so counting runs for days; in 2022, late Clark County mail moved the Senate race toward the Democrat.",
  OH: "Early and absentee votes come first, then Election Day votes; in 2024, 90% was in by about 11 p.m. Under a 2025 law, most mail ballots must now arrive by the time polls close.",
  PA: "Mail ballots can't be opened before 7 a.m. on Election Day, so counties count them overnight alongside Election Day votes. Mail has leaned Democratic: in 2024 the Republican Senate winner's lead shrank as later ballots came in.",
  SC: "Most counties post early in-person and many mail results first, some with Election Day votes; in 2024, half the vote was in by about 9 p.m. and 90% by about 11 p.m.",
  TX: "Early in-person and mail votes come first, shortly after polls close, then Election Day votes; large counties are slower.",
  WI: "Absentee ballots can't be processed before Election Day, and Milwaukee and other cities that count them centrally report late, often after midnight. Those late batches have leaned Democratic, so the count can move toward Democrats late in the night."
};
function countOrderList() {
  const list = Object.entries(COUNT_ORDER).sort((a, b) => (statesMeta.names?.[a[0]] ?? a[0]).localeCompare(statesMeta.names?.[b[0]] ?? b[0]));
  return html`<details class="schedule"><summary>How each state counts</summary>
    <p class="caption">Which ballots each state usually reports first, and which way its count has tended to move as the rest come in, for the states with the closest Senate and governor races. An early lead can mean little until the late ballots are in.</p>
    <dl class="count-list">${list.map(([po, text]) => html`<dt>${statesMeta.names?.[po] ?? po}</dt><dd>${text}</dd>`)}</dl>
    <p class="caption">From the Associated Press's 2026 notes on what to expect in each state, <a href="https://www.votebeat.org">Votebeat</a>, and state and local reporting.</p></details>`;
}
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
// which races just got new votes: their rows flash once
for (const d of base) {
  const was = ui.prev[d.race_id];
  if (was != null && was !== d.m.counted) ui.changedAt[d.race_id] = Date.now();
  ui.prev[d.race_id] = d.m.counted;
}
const justChanged = (d) => Date.now() - (ui.changedAt[d.race_id] ?? 0) < 8000;
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

${html`<p class="kicker">Election night · November 3, 2026${started ? ` · ${live.called} of ${live.total} races called` : ""}${asof && started ? html` · Updated ${etTime(asof)}<span class="ago" data-t=${+asof}>${agoText(+asof)}</span>${live.source === "direct" ? " · live from civicAPI" : ""}` : ""}</p>`}

# ${started && headline ? headline : started ? `${live.called} of ${live.total} races called` : "Results will appear here on election night"}

<p class="dek">${started
  ? html`Live results and odds, updated every few minutes. The odds are our estimates from the counts so far, not calls, and will swing as votes come in.`
  : html`From the first poll closings at 6 p.m. Eastern on November 3, the count for every House, Senate and governor race will appear here every few minutes, next to what our forecast expected, with a running tally of the House and Senate. ${(() => { const today = new Date().toLocaleDateString("en-CA", {timeZone: "America/New_York"}), days = Math.round((Date.parse("2026-11-03") - Date.parse(today)) / 864e5); return days > 1 ? `That's ${days} days away.` : days === 1 ? "That's tomorrow." : days === 0 ? "That's tonight." : ""; })()}`}</p>

```js
// how the page works, folded away until asked for
if (started) display(html`<details class="how-works"><summary>How this page works</summary>
  <p>Vote counts come from <a href="https://civicapi.org">civicAPI</a>, refreshed every few minutes, next to what our forecast expected this morning. Calls are civicAPI's, not ours. Click any race for its full count: the votes left, what each side needs of them, where the uncounted vote leans, and turnout against what we expected. The page updates on its own.</p>
  ${odds ? html`<p>${odds.used
    ? `Live odds: in the ${odds.used} race${odds.used === 1 ? "" : "s"} at least 95% counted, results are running about ${Math.abs(odds.shift).toFixed(1)} points more ${odds.shift >= 0 ? "Democratic" : "Republican"} than our forecast nationally (more or less in some regions and states). We move every race still out by that much, count called races for their winners, and play out the rest of the night thousands of times.`
    : "Live odds: until races finish counting, the night's overall shift comes from our forecast."} Each race's own count also moves its odds, more as more of it comes in: where we have county results, we compare the counted counties with our forecast and fill in the counties still out from their benchmarks. The same results always give the same odds.</p>` : ""}
  ${read ? html`<p>The turnout and counted-counties figures compare every county that has reported in the ${read.states} states with Senate or governor races counting against our county benchmarks. They move earlier than the live odds, and can mislead early, when one kind of ballot dominates the count.</p>` : ""}
</details>`);
```

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
  c.flips = d3.rollups(list.filter((d) => d.flipped), (v) => v.length, (d) => d.tagOf(d.called)).sort((a, b) => b[1] - a[1]);
  return c;
}
const PARTY = {D: "Democrats", R: "Republicans", I: "independents"};
// under each bar, in words: where the seats stand if every lead holds, what each side still needs, and flips
function tallyLines(office, c, need) {
  const lines = [];
  const lead = {D: c.Dc + c.Dl, R: c.Rc + c.Rl, I: c.Ic + c.Il};
  if (c.Dl + c.Rl + c.Il + c.open > 0) lines.push(html`<div>If current leads hold: ${chip("D")} ${lead.D}${lead.I ? html` · ${chip("I")} ${lead.I}` : ""} · ${chip("R")} ${lead.R}${c.open ? ` (${c.open} with no votes yet)` : ""}</div>`);
  if (need) {
    const left = c.Dl + c.Rl + c.Il + c.open;  // seats not yet called
    const needOf = {D: need - c.Dc, R: (office === "SEN" ? need - 1 : need) - c.Rc};  // Republicans hold the Senate at 50, with the vice president
    const won = needOf.D <= 0 ? "D" : needOf.R <= 0 ? "R" : null;
    const say = (p) => (needOf[p] > left ? `${PARTY[p]} can no longer get there` : `${PARTY[p]} need ${needOf[p]} of the ${left} seats not yet called`);
    lines.push(html`<div>${won ? html`<b>${PARTY[won]} have won control.</b>` : `To win control: ${say("D")}; ${say("R")}.`}</div>`);
    // the count's leads and our odds can point different ways early in the night: say why
    const p = office === "SEN" ? odds?.pSen : odds?.pHouse;
    if (!won && p != null && lead.D !== lead.R) {
      const leader = lead.D > lead.R ? "D" : "R", fav = p >= 0.5 ? "D" : "R";
      if (leader !== fav && Math.max(p, 1 - p) >= 0.6) lines.push(html`<div class="muted">${PARTY[leader]} lead in more seats right now, but our live odds favor ${PARTY[fav]}: many of those leads are early counts that our odds expect to shift as the rest of the vote comes in.</div>`);
    }
  }
  lines.push(html`<div class="muted">${c.flips.length ? `Changed parties so far: ${c.flips.map(([p, n]) => `${n} seat${n === 1 ? "" : "s"} to ${PARTY[p]}`).join(", ")}.` : "No seat has changed parties yet."}</div>`);
  return lines;
}
function tallyBar(office, label, c, need, total, note) {
  // the same shades as the map: solid for called, lighter for leading
  const seg = (n, color) => (n ? `<b style="flex:${n};background:${color}"></b>` : "");
  const bar = html`<div class="tally-bar"></div>`;
  bar.innerHTML = seg(c.Dc, t["Safe D"]) + seg(c.Dl, t["Lean D"]) + seg(c.Ic, t.ind) + seg(c.Il, `color-mix(in srgb, ${t.ind} 45%, ${t.surface})`) + seg(c.open, t.hair) + seg(c.Rl, t["Lean R"]) + seg(c.Rc, t["Safe R"])
    + (need ? `<i style="left:${(100 * need) / total}%"></i>` : "");
  return html`<div class="tally">
    <div class="tally-head"><b>${label}</b><span class="muted">${note}</span></div>
    ${need ? html`<div class="tally-scale"><span style="left:${(100 * need) / total}%">${need} for control</span></div>` : ""}
    ${bar}
    <div class="tally-nums"><span>${chip("D")} ${c.Dc} won${c.Dl ? `, ${c.Dl} leading` : ""}</span>${c.Ic + c.Il ? html`<span>${chip("I")} ${c.Ic} won${c.Il ? `, ${c.Il} leading` : ""}</span>` : ""}<span class="muted">${c.open} not yet counted</span><span>${chip("R")} ${c.Rc} won${c.Rl ? `, ${c.Rl} leading` : ""}</span></div>
    <div class="tally-lines">${tallyLines(office, c, need)}</div>
  </div>`;
}
const SEATS = {SEN: () => tally("SEN", {D: 34, R: 31}), HOUSE: () => tally("HOUSE"), GOV: () => tally("GOV")};
const TALLY = {
  SEN: () => tallyBar("SEN", "Senate", SEATS.SEN(), 51, 100, "Includes the 65 seats not up this year; Republicans need only 50, with the vice president's tiebreak"),
  HOUSE: () => tallyBar("HOUSE", "House", SEATS.HOUSE(), 218, 435, "Includes seats where only one party is on the ballot"),
  GOV: () => tallyBar("GOV", "Governors", SEATS.GOV(), null, 36, "36 races")
};
// "Republicans' chance of Senate control: 72% (this morning: 21%)", for whichever side is favored now
function controlCard(chamber, p, morning) {
  const side = p >= 0.5 ? "D" : "R";
  const now = side === "D" ? p : 1 - p, then = side === "D" ? morning : 1 - morning;
  return html`<div class="ctl"><div class="k">${PARTY[side]}' chance of ${chamber} control</div><div class="v">${chip(side)} ${pct(now)}</div><div class="muted">this morning: ${pct(then)}</div></div>`;
}
// the headline, in words: "Republicans are favored to win the Senate; Democrats are all but certain to win the House"
function controlLine(chamber, p, c, need) {
  if (c.Dc >= need) return `Democrats have won the ${chamber}`;
  if (c.Rc >= (chamber === "Senate" ? need - 1 : need)) return `Republicans have won the ${chamber}`;
  const q = Math.max(p, 1 - p), who = PARTY[p >= 0.5 ? "D" : "R"];
  if (q < 0.55) return `the ${chamber} is a toss-up`;
  return `${who} are ${q >= 0.99 ? "all but certain" : q >= 0.9 ? "very likely" : q >= 0.7 ? "favored" : "slightly favored"} to win the ${chamber}`;
}
const headline = odds ? (([s]) => s[0].toUpperCase() + s.slice(1))([`${controlLine("Senate", odds.pSen, SEATS.SEN(), 51)}; ${controlLine("House", odds.pHouse, SEATS.HOUSE(), 218)}`]) : null;
// the top of the page, above the tabs: control odds, then the seat tallies
function topBlock() {
  return html`<div class="top-block">
    ${odds ? html`<div class="ctl-row">${controlCard("Senate", odds.pSen, top.p_senate_d)}${controlCard("House", odds.pHouse, top.p_house_d)}</div>` : ""}
    <div class="tallies">${TALLY.SEN()}${TALLY.HOUSE()}${TALLY.GOV()}</div>
  </div>`;
}

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
// "Talarico running 1.2 points ahead of our forecast", from the counted counties where we have them (map hover cards)
function gapText(d) {
  const g = d.m.gap;
  if (g == null) return "";
  if (Math.abs(g) < 0.5) return "Right on our forecast";
  return `${lastName(d.nameOf(g > 0 ? "D" : "R"))} running ${Math.abs(g).toFixed(1)} ahead of forecast`;
}
// the same in the tables, by party, so each row names its people only once
function gapCell(d) {
  const g = d.m.gap;
  if (g == null) return "";
  if (Math.abs(g) < 0.5) return html`<div class="adj">Right on our forecast</div>`;
  return html`<div class="adj">${chip(d.tagOf(g > 0 ? "D" : "R"))} ${Math.abs(g).toFixed(1)} pts ahead of our forecast</div>`;
}
const status = (d) => (d.called
  ? html`<span><span class="res-called">${chip(d.tagOf(d.called))} Won by ${Math.abs(d.x.margin ?? 0) < 0.05 ? "under 0.1" : Math.abs(d.x.margin).toFixed(1)}</span>${(d.x.pct ?? 0) < 100 ? html`<div class="adj">${d.x.pct ?? 0}% counted</div>` : ""}</span>`
  : d.counted ? html`<span><span class="res-lead">${chip(d.tagOf(d.lead))} ${sideText(d, d.x.margin)}</span>${leftText(d)}${leanText(d)}${favNote(d)}</span>`
  : html`<span class="muted">No votes yet (polls close ${clock((CLOSE[d.state_po] ?? [21])[0])})</span>`);
// "272,000 of ~4.7 million votes counted": the count against the turnout we expect
function leftText(d) {
  const f = finish(d, d.m);
  if (!f || !d.counted) return "";
  return html`<div class="adj">${k(d.m.counted)} of ~${k(f.total)} votes counted</div>`;
}
// where the votes still out lean, from our county benchmarks for the places still counting (Senate and governors)
function leanText(d) {
  if (d.m.benchRem == null || !(d.m.uncounted > 0) || (d.x.pct ?? 0) >= 100) return "";
  return html`<div class="adj">Votes left lean ${sideText(d, d.m.benchRem)}</div>`;
}
// the leader isn't who our live odds favor: say so, so the row doesn't read as a contradiction
function favNote(d) {
  if (d.pNow == null || !d.lead) return "";
  const fav = d.pNow >= 0.5 ? "D" : "R";
  return fav === d.lead ? "" : html`<div class="adj fav-note">Our odds favor ${lastName(d.nameOf(fav))}, who trails for now</div>`;
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
  {key: "range", label: "vs. our forecast", render: (d) => html`<span>${rangeBar(d)}${gapCell(d)}</span>`},
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
        <td>${states.map((s, i) => html`${i ? ", " : ""}${s}${CLOSE[s][1] > CLOSE[s][0] ? html`<sup>*</sup>` : ""}`)}</td>
        <td>${big.length ? big.map((r, i) => html`${i ? ", " : ""}${raceLink(r, `${r.state_po} ${officeLabel[r.office].slice(0, 3)}${r.special ? " (sp.)" : ""}`)}`) : html`<span class="muted">–</span>`}</td>
        <td class="num">${list.filter((r) => r.office === "HOUSE").length}</td></tr>`;
    })}</tbody></table></div>
    <p class="caption">When each state's first polls close. <sup>*</sup>States that span two time zones, where polls in the rest of the state close an hour later; results often wait until all of a state's polls have closed. Alaska's and Hawaii's polls close at midnight Eastern, and the far western Aleutian Islands at 1 a.m. Poll-closing times from <a href="https://www.thegreenpapers.com/G26/closing.phtml?format=gc">The Green Papers</a>.</p>`;
}
```

```js
// ---------- the drill-in: one race's full count (components/night.js, the same panel as the race pages) ----------
function detail(d) {
  const el = html`<div class="race-detail"></div>`;
  // back up to the map this race was opened from (or the one above it)
  const back = html`<button type="button" class="back-map">↑ Back to the map</button>`;
  back.onclick = (e) => { e.stopPropagation(); document.querySelector(`#panel-${ui.tab} .map-panel`)?.scrollIntoView({block: "start", behavior: smooth()}); };
  const order = d.office !== "HOUSE" ? COUNT_ORDER[d.state_po] : null;
  const draw = (counties) => el.replaceChildren(back, ...racePanel(d, counties),
    ...(order ? [html`<p class="count-order"><b>How ${d.state_name} counts:</b> ${order}</p>`] : []));
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
  lead: (off) => `Solid colors with a ${off === "HOUSE" ? "dot" : "check mark"} are races civicAPI has called; lighter ones, who leads the count so far; solid with no mark, seats where only one party is on the ballot.`,
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
    const opts = {width: w, fillRace: MAP_MODES.find(([v]) => v === mode)[2], tipRows, onPick: (r) => rowOf.has(r.race_id) && openRace(table, r.race_id),
      mark: mode === "morning" ? null : (r) => Boolean(rowOf.get(r.race_id)?.called)};
    body.replaceChildren(off === "HOUSE" ? hexMap(races, layout, opts) : stateMap(races, topo, statesMeta, {office: off, ...opts}), legend(mode, off));
    const n = MAP_NOTES[mode];
    note.textContent = `${typeof n === "function" ? n(off) : n}${mode === "gap" ? (off === "HOUSE" ? ": for House districts, our most likely margin for the whole district, so early counts can mislead." : ", in the counties counted so far.") : ""} Click a ${off === "HOUSE" ? "district" : "state"} for its full count.`;
  };
  draw();
  // keyboard readers can step past the map's hundreds of districts
  const skip = html`<button type="button" class="skip-map">Skip the map</button>`;
  skip.onclick = () => { const next = box.nextElementSibling; if (next) { next.tabIndex = -1; next.focus(); } };
  box.append(skip, ...(offices ? [html`<div class="seg-row">${officeSeg}${toggle}</div>`] : [toggle]), body, note);
  return box;
}
function chamberTable(key, list, {pageSize = 25} = {}) {
  return raceTable(list, COLUMNS, {filters: [STATUS_FILTER, stateFilter(list)], sorts: SORTS, pageSize, detail, openSet: openSet(key),
    memory: memOf(key), changed: justChanged, placeholder: "Search candidates, states, districts"});
}
// Open a race in a table and take the reader to it, as a step in the browser's history: Back returns to where they
// were (the map, usually), and the address names the race, so it can be shared.
function openRace(table, rid) {
  history.replaceState({...(history.state ?? {}), wsuY: window.scrollY, wsuTab: ui.tab}, "");
  history.pushState({wsuRace: rid, wsuTab: ui.tab}, "", `#${rid}`);
  table.reveal(rid);
}
```

```js
// ---------- tabs ----------
function selectTab(key, {address = true} = {}) {
  ui.tab = key;
  if (address) history.replaceState(history.state, "", `#${key}`);
  for (const [k_] of TABS) {
    document.getElementById(`tab-${k_}`)?.setAttribute("aria-selected", String(k_ === key));
    document.getElementById(`panel-${k_}`)?.toggleAttribute("hidden", k_ !== key);
  }
  document.getElementById(`panel-${key}`)?.dispatchEvent(new Event("show"));
}
function tabBar() {
  const bar = html`<div class="tabs" role="tablist" aria-label="Results by office"></div>`;
  for (const [key, label] of TABS) {
    const b = html`<button type="button" role="tab" id="tab-${key}" aria-selected=${String(ui.tab === key)}>${label}</button>`;
    b.onclick = () => selectTab(key);
    bar.append(b);
  }
  return bar;
}
// "Find a race", right under the tabs: suggestions as you type; picking one opens it in the table on this tab (or
// on its own office's tab)
const OFFICE_TAB = {SEN: "senate", HOUSE: "house", GOV: "governors"};
const OFFICE_ORDER = {SEN: 0, GOV: 1, HOUSE: 2};
function quickFind() {
  const box = html`<div class="quick-find"><input type="search" placeholder="Find a race: state, district or candidate" aria-label="Find a race" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="qf-list"><ul id="qf-list" class="qf-list" role="listbox" hidden></ul></div>`;
  const input = box.querySelector("input"), list = box.querySelector("ul");
  let hits = [], at = -1;
  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); };
  const pick = (d) => {
    input.value = ""; close(); input.blur();
    const key = ui.tab === "overview" ? "all" : ui.tab === OFFICE_TAB[d.office] ? ui.tab : (selectTab(OFFICE_TAB[d.office]), OFFICE_TAB[d.office]);
    if (ui.tables[key]) openRace(ui.tables[key], d.race_id);
  };
  const mark = () => [...list.children].forEach((li, i) => li.setAttribute("aria-selected", String(i === at)));
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    // matches at the start of a word first ("kansas" is Kansas before Arkansas)
    const word = new RegExp(`(^|[^a-z])${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`);
    const score = (d) => (d.state_name.toLowerCase().startsWith(q) ? 0 : word.test(d._search) ? 1 : 2);
    hits = q.length < 2 ? [] : rows.filter((d) => d._search.includes(q))
      .sort((a, b) => score(a) - score(b) || OFFICE_ORDER[a.office] - OFFICE_ORDER[b.office] || d3.ascending(a.state_name, b.state_name) || d3.ascending(a.district, b.district)).slice(0, 8);
    at = -1;
    list.replaceChildren(...hits.map((d) => {
      const li = html`<li role="option"><span>${raceName(d)}</span><span class="muted">${d.called ? `${lastName(d.nameOf(d.called))} won` : d.counted ? sideText(d, d.x.margin) : "No votes yet"}</span></li>`;
      li.addEventListener("mousedown", (e) => { e.preventDefault(); pick(d); });
      return li;
    }));
    list.hidden = !hits.length;
    input.setAttribute("aria-expanded", String(Boolean(hits.length)));
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); if (hits.length) { at = (at + (e.key === "ArrowDown" ? 1 : hits.length - 1)) % hits.length; mark(); } }
    else if (e.key === "Enter" && hits.length) { e.preventDefault(); pick(hits[Math.max(at, 0)]); }
    else if (e.key === "Escape") close();
  });
  input.addEventListener("blur", () => setTimeout(close, 150));
  return box;
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
// Back and Forward between the map and the races opened from it
{
  const onPop = (e) => {
    const s = e.state ?? {};
    if (s.wsuTab && s.wsuTab !== ui.tab) selectTab(s.wsuTab, {address: false});
    if (s.wsuY != null) scrollTo({top: s.wsuY});
    else if (s.wsuRace) document.querySelector(`#panel-${ui.tab} tr[data-id="${CSS.escape(s.wsuRace)}"]`)?.scrollIntoView({block: "start"});
  };
  addEventListener("popstate", onPop);
  invalidation.then(() => removeEventListener("popstate", onPop));
}
```

```js
// ---------- the Overview tab ----------
function overview() {
  const parts = [];
  // the night against our forecast: three measures, each labeled for what it compares
  const signed = (x) => `${x >= 0 ? "+" : "−"}${Math.round(Math.abs(x) * 100)}%`;
  const lean = (g) => (Math.abs(g) < 0.25 ? "Even" : `${g > 0 ? "D" : "R"} +${Math.abs(g).toFixed(1)}`);
  if (odds && (read || odds.used)) {
    parts.push(html`<h2 class="night-h">The night against our forecast</h2><div class="stat-row night-row">
      ${read?.turnout != null ? html`<div class="s"><div class="k">Turnout vs. what we expected</div><div class="v">${signed(read.turnout)}</div><div class="muted">${read.turnoutD != null && read.turnoutR != null ? `Democratic-leaning counties ${signed(read.turnoutD)}, Republican-leaning ${signed(read.turnoutR)}` : "in the counties counted so far"}</div></div>` : ""}
      ${read ? html`<div class="s"><div class="k">Counted counties vs. our benchmarks</div><div class="v">${lean(read.gap)}</div><div class="muted">${Math.abs(read.gap) < 0.25 ? "right on our forecast" : `points ${read.gap > 0 ? "more Democratic" : "more Republican"} than we expected there`}</div></div>` : ""}
      <div class="s"><div class="k">Finished races vs. our forecast</div><div class="v">${odds.used ? lean(odds.shift) : "–"}</div><div class="muted">${odds.used ? `in the ${odds.used} race${odds.used === 1 ? "" : "s"} at least 95% counted` : "no race has finished counting yet"}</div></div>
    </div>
    <p class="caption">The first two use every county reported so far in states with Senate or governor races, so they move early and can mislead when one kind of ballot dominates the count. The third uses only races nearly done counting; it's the one our live odds lean on.</p>`);
  }
  if (started) parts.push(leftToCount());
  const calls = latestCalls();
  if (calls) parts.push(calls);
  // the map, all three offices; clicking a race opens it in "Find any race" below
  const all = raceTable(rows, COLUMNS, {filters: [{key: "office", label: "All offices", options: [["SEN", "Senate"], ["GOV", "Governor"], ["HOUSE", "House"]], test: (d, v) => d.office === v}, STATUS_FILTER],
    sorts: [SORTS[1], ...SORTS.filter((x, i) => i !== 1)], pageSize: 10, detail, openSet: openSet("all"), memory: memOf("all"), changed: justChanged, placeholder: "Search candidates, states, districts"});
  all.classList.add("res-cards");
  ui.tables.all = all;
  parts.push(mapPanel("overview", "SEN", all, {offices: [["SEN", "Senate"], ["HOUSE", "House"], ["GOV", "Governors"]]}));
  // the races that matter most for control, then any race at all, then how our forecast has done
  const keyRaces = [...topRaces("SEN", 7), ...topRaces("HOUSE", 5), ...topRaces("GOV", 3)];
  parts.push(html`<h2>Key races</h2><p class="caption">The Senate and House races likeliest to decide control in our forecast, and the closest governor's races. Click a race for its full count.</p>`);
  const kt = raceTable(keyRaces, COLUMNS, {search: false, pageSize: 20, detail, openSet: openSet("key"), memory: memOf("key"), changed: justChanged, noun: "race"});
  kt.classList.add("res-cards", "key-cards");
  parts.push(kt);
  parts.push(html`<h2>Find any race</h2>`);
  parts.push(all);
  parts.push(caption());
  if (calledRows.length) parts.push(...scorecard());
  parts.push(html`<details class="schedule"><summary>When polls close</summary>${schedule()}</details>`);
  if (Object.keys(COUNT_ORDER).length) parts.push(countOrderList());
  return parts;
}
// ---------- the latest calls, newest first (when each call first showed up in our poller's copy) ----------
function latestCalls() {
  const list = rows.filter((d) => d.called && d.x.called_at).sort((a, b) => d3.descending(a.x.called_at, b.x.called_at)).slice(0, 8);
  if (!list.length) return null;
  return html`<div class="calls"><h3>Latest calls</h3><ul>${list.map((d) => {
    const go = html`<button type="button" class="call-race">${raceName(d)}</button>`;
    go.onclick = () => openRace(ui.tables.all, d.race_id);
    const gave = d.called === "D" ? d.p_dem : 1 - d.p_dem;
    return html`<li><span class="when">${etTime(new Date(d.x.called_at)).replace(" ET", "")}</span><span>${chip(d.tagOf(d.called))} <b>${lastName(d.nameOf(d.called))}</b> wins ${go}${d.flipped ? html` <span class="pill-flip">Flip</span>` : ""}<span class="muted"> · we gave ${pct(gave)} this morning</span></span></li>`;
  })}</ul></div>`;
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
  // the House vote counted so far, nationally, against our forecast of the national House vote
  const vD = d3.sum(house, (d) => d.x.d ?? 0), vR = d3.sum(house, (d) => d.x.r ?? 0);
  const houseLine = vD + vR > 0 ? html`<li><b>House vote counted so far:</b> ${margin((100 * (vD - vR)) / (vD + vR))}, from ${k(vD + vR)} votes for the two parties; our forecast for the national House vote was ${margin(top.nat_median)}. Contested seats only; early counts lean toward whichever ballots states count first, and the West counts last.</li>` : "";
  // hovering the bar (or tapping it, or tabbing to it) shows the votes counted so far
  const sharePct = share > 0 && share < 0.01 ? "Less than 1%" : `About ${Math.round(share * 100)}%`;
  const tipLines = [["t-title", "Votes counted so far"], ["t-val", got.toLocaleString()],
    ["t-sub", `${sharePct} of the ${k(all)} we expect. Votes for the two parties in contested House races.`]];
  const bar = html`<div class="left-bar" role="img" tabindex="0" aria-label="${got.toLocaleString()} votes counted so far, ${Math.round(share * 100)}% of the expected vote"><b style="flex:${share}"></b><i></i></div>`;
  const tt = tip();
  tt.hide();  // the page redraws with each update; don't leave a popup stranded from the old bar
  bar.addEventListener("pointerenter", (e) => { if (e.pointerType === "mouse") tt.show(e, tipLines); });
  bar.addEventListener("pointermove", (e) => { if (e.pointerType === "mouse") tt.move(e); });
  bar.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") tt.hide(); });
  bar.addEventListener("click", (e) => {
    if (e.pointerType === "mouse") return;
    tt.show(e, tipLines);
    window.addEventListener("pointerdown", () => tt.hide(), {once: true, capture: true});
  });
  bar.addEventListener("focus", () => {
    if (!bar.matches(":focus-visible")) return;
    const r = bar.getBoundingClientRect();
    tt.show({clientX: r.left + r.width / 2, clientY: r.bottom}, tipLines);
  });
  bar.addEventListener("blur", () => tt.hide());
  return html`<div class="left-box"><h3>What's left to count</h3>
    ${bar}
    <ul>
      <li><b>Votes:</b> ${out > 0 ? html`about <b>${k(out)}</b> still to count, roughly ${Math.round((100 * out) / all)}% of the ${k(all)} we expect in all.` : "all in, or close to it."}</li>
      <li><b>Races:</b> ${uncalled.length ? html`${list(uncalled)} race${s + h + g === 1 ? "" : "s"} not called yet.` : "every race has been called."}</li>
      ${piles.length ? html`<li><b>Most of the uncounted vote:</b> ${list(piles.map(([st, n]) => `${st} (${k(n)})`))}.</li>` : ""}
      ${houseLine}
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
    pageSize: 10, detail, openSet: openSet("called"), memory: memOf("called"), noun: "called race", placeholder: "Search called races"});
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
  const parts = [];  // the control odds and seat tallies sit above the tabs
  const table = chamberTable(key, list, {pageSize: office === "HOUSE" ? 25 : 40});
  table.classList.add("res-cards");
  ui.tables[key] = table;
  parts.push(mapPanel(key, office, table));
  parts.push(html`<h2>Every ${office === "GOV" ? "governor's race" : office === "SEN" ? "Senate race" : "House race"}</h2>`);
  parts.push(table, caption());
  return parts;
}
```

```js
// ---------- the page ----------
if (started) {
  ui.tables = {};
  display(topBlock());
  display(shareRow("https://whoshowsup.net/results", "Live 2026 election results and odds, race by race, from Who Shows Up"));
  display(tabBar());
  display(quickFind());
  display(panel("overview", overview));
  display(panel("senate", () => chamber("senate", "SEN")));
  display(panel("house", () => chamber("house", "HOUSE")));
  display(panel("governors", () => chamber("governors", "GOV")));
} else {
  display(shareRow("https://whoshowsup.net/results", "2026 election night results, race by race, from Who Shows Up"));
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
