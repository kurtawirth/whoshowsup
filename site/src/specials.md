---
title: Special elections
---

```js
import {tokens, pct, margin, marginShort, date, raceTable} from "./components/wsu.js";
const national = FileAttachment("data/national.json").json();
const states = FileAttachment("data/states.json").json();
```

```js
const t = (dark, tokens());
const style = {background: "transparent", color: t["ink-3"], fontSize: "12px"};
const shift = (v) => (Math.abs(v) < 0.5 ? "no shift" : v > 0 ? `D+${Math.round(v)}` : `R+${Math.round(-v)}`);
const cycleOf = (y) => (y % 2 ? y : y - 1);
const cycleLabel = (c) => `${c}–${String(c + 1).slice(2)}`;
const CUR = d3.max(national.specials, (d) => cycleOf(d.year));
const officeName = (d) => {
  if (d.chamber === "US House") return `${d.district} · U.S. House`;
  if (d.chamber === "US Senate") return "U.S. Senate";
  const kind = d.district.slice(0, 2), seat = d.district.slice(3).replace(/-/g, " ").replace(/\b0+(\d)/g, "$1");
  return `${{HD: "State House", SD: "State Senate", AD: "State Assembly"}[kind] ?? kind} ${seat}`;
};
// Each race, lined up by where it fell in its own two-year cycle (drawn on the current cycle's calendar).
const spec = national.specials
  .map((d) => {
    const dt = new Date(`${d.date}T12:00:00`), cycle = cycleOf(d.year);
    const aligned = new Date(dt); aligned.setFullYear(dt.getFullYear() + CUR - cycle);
    return {...d, dt, cycle, aligned, state_name: states.names[d.state_po] ?? d.state_po, office: officeName(d)};
  })
  .filter((d) => d.dt < new Date(d.cycle + 1, 10, 1))  // through October of the election year
  .sort((a, b) => a.dt - b.dt);
// Running (cycle-to-date) average; the model starts using it once 10 races are in.
const running = d3.groups(spec, (d) => d.cycle).flatMap(([cycle, xs]) =>
  xs.map((d, i) => ({cycle, aligned: d.aligned, dt: d.dt, n: i + 1, avg: d3.mean(xs.slice(0, i + 1), (e) => e.overperformance)}))
    .filter((d) => d.n >= 10));
const cur = spec.filter((d) => d.cycle === CUR);
const curAvg = d3.mean(cur, (d) => d.overperformance);
const flipsD = cur.filter((d) => d.flipped && d.winner === "D").length;
const flipsR = cur.filter((d) => d.flipped && d.winner === "R").length;
const baseline = cur[0]?.pres_baseline ?? "the last";
```

<p class="kicker">Special elections · Latest race ${date(cur.at(-1).date)}</p>

# ${Math.abs(curAvg) < 0.5 ? "Special elections are running even with the usual partisan lean" : `${curAvg > 0 ? "Democrats" : "Republicans"} are running ${Math.round(Math.abs(curAvg))} points ahead of the usual lean in special elections`}

<p class="dek">When a seat opens up between regular elections, a special election fills it. Few people vote in them, so the result says a lot about which party's voters are eager to show up. We compare each result with how the same district voted for president in ${baseline}. Across ${cur.length} races this cycle, the result has shifted ${curAvg > 0 ? "toward Democrats" : "toward Republicans"} by ${Math.abs(curAvg).toFixed(1)} points on average. This is one of the three readings behind <a href="./national">our national estimate</a>.</p>

```js
display(html`<div class="stat-row">
  <div class="s"><div class="k">Races this cycle</div><div class="v">${cur.length}</div></div>
  <div class="s"><div class="k">Average shift</div><div class="v">${shift(curAvg)}</div></div>
  <div class="s"><div class="k">Shifted toward Democrats</div><div class="v">${pct(cur.filter((d) => d.overperformance > 0).length / cur.length)}</div></div>
  <div class="s"><div class="k">Seats flipped</div><div class="v">${flipsD} to D · ${flipsR} to R</div></div>
</div>`);
```

## The running average, cycle by cycle

```js
const cycles = [...new Set(running.map((d) => d.cycle))];
const ends = cycles.map((c) => running.filter((d) => d.cycle === c).at(-1));
const electionDay = new Date(CUR + 1, 10, 3);
display(resize((w) => Plot.plot({
  width: w, height: 340, marginLeft: 44, marginRight: w < 560 ? 44 : 96,
  x: {label: null, type: "utc", domain: [new Date(CUR, 0, 1), new Date(CUR + 1, 10, 10)], tickFormat: w < 560 ? "%b %y" : "%b %Y"},
  y: {label: "Average shift toward Democrats (points)", grid: true, tickFormat: (v) => (v > 0 ? `D+${v}` : v < 0 ? `R+${-v}` : "0")},
  style,
  marks: [
    Plot.ruleY([0], {stroke: t.axis}),
    Plot.ruleX([electionDay], {stroke: t.axis, strokeDasharray: "3,3"}),
    Plot.text([electionDay], {x: (d) => d, frameAnchor: "top", text: () => "Election Day", dy: 2, textAnchor: "end", dx: -4, fill: t["ink-3"]}),
    Plot.line(running.filter((d) => d.cycle !== CUR), {x: "aligned", y: "avg", z: "cycle", stroke: t["ink-3"], strokeWidth: 1.5, strokeOpacity: 0.7}),
    Plot.line(running.filter((d) => d.cycle === CUR), {x: "aligned", y: "avg", stroke: t.ink, strokeWidth: 3}),
    Plot.dot(ends.filter((d) => d.cycle === CUR), {x: "aligned", y: "avg", r: 5, fill: t.ink, stroke: t.surface, strokeWidth: 2}),
    Plot.text(ends, {x: "aligned", y: "avg", text: (d) => (w < 560 ? `${String(d.cycle).slice(2)}–${String(d.cycle + 1).slice(2)}` : `${cycleLabel(d.cycle)} ${shift(d.avg)}`), dx: 8, textAnchor: "start",
      fill: (d) => (d.cycle === CUR ? t.ink : t["ink-3"]), fontWeight: (d) => (d.cycle === CUR ? 700 : 500)}),
    Plot.tip(running, Plot.pointer({x: "aligned", y: "avg", title: (d) => `${cycleLabel(d.cycle)} cycle, as of ${date(d.dt.toISOString().slice(0, 10))}\nAverage of the first ${d.n} races: ${shift(d.avg)}`}))
  ]
})));
```

<p class="caption">The average shift across all special elections so far in each two-year cycle, updated with each new race. Past cycles are lined up with this one: for 2017–18, "Jan ${CUR}" stands for January 2017. Each line starts once 10 races are in, the point at which the model starts using this reading. Shifts are measured against the previous presidential election.</p>

## Every race this cycle

```js
display(resize((w) => Plot.plot({
  width: w, height: 320, marginLeft: 44,
  x: {label: null, type: "utc", ticks: d3.utcMonth.every(w < 560 ? 6 : 3), tickFormat: w < 560 ? "%b %y" : "%b %Y"},
  y: {label: "Shift toward Democrats (points)", grid: true, tickFormat: (v) => (v > 0 ? `D+${v}` : v < 0 ? `R+${-v}` : "0")},
  style,
  marks: [
    Plot.ruleY([0], {stroke: t.axis}),
    ...[["state legislature", 4], ["US House", 7]].map(([ch, r]) => Plot.dot(cur.filter((d) => d.chamber === ch), {x: "dt", y: "overperformance", r,
      fill: (d) => (d.overperformance >= 0 ? t.dem : t.rep), fillOpacity: 0.7, stroke: t.surface, strokeWidth: 1.5})),
    Plot.line(running.filter((d) => d.cycle === CUR), {x: "dt", y: "avg", stroke: t.ink, strokeWidth: 2.5}),
    Plot.tip(cur, Plot.pointer({x: "dt", y: "overperformance", title: (d) => `${d.state_name} ${d.office}\n${date(d.date)}\nResult ${margin(d.special_margin)} vs. president ${margin(d.pres_margin)}\nShift ${shift(d.overperformance)}${d.flipped ? `\nFlipped from ${d.held_by} to ${d.winner}` : ""}`}))
  ]
})));
```

<p class="caption">Each dot is one race; larger dots are U.S. House seats, the rest state legislative seats. Blue dots shifted toward Democrats compared with the district's ${baseline} presidential vote, red toward Republicans. The line is the running average.</p>

```js
function shiftBar(v) {
  const el = document.createElement("span");
  el.className = "sp-shift";
  const w = Math.min(Math.abs(v), 40) / 40 * 50;
  el.innerHTML = `<i></i><b style="${v >= 0 ? "left:50%" : `left:${50 - w}%`};width:${w}%;background:${v >= 0 ? t.dem : t.rep}"></b>`;
  const lab = document.createElement("span");
  lab.className = "sp-shift-lab";
  lab.textContent = shift(v);
  const cell = document.createElement("span");
  cell.className = "sp-shift-cell";
  cell.append(el, lab);
  return cell;
}
const rows = [...cur].reverse().map((d) => ({...d, _search: `${d.state_name} ${d.state_po} ${d.office}`.toLowerCase()}));
display(raceTable(rows, [
  {key: "date", label: "Date", sort: true, defaultDir: -1, render: (d) => Object.assign(document.createElement("span"), {textContent: date(d.date), style: "white-space:nowrap"})},
  {key: "state_name", label: "State", sort: true},
  {key: "office", label: "Seat", sort: true},
  {key: "special_margin", label: "Result", num: true, sort: true, render: (d) => marginShort(d.special_margin)},
  {key: "pres_margin", label: `President ${baseline}`, num: true, sort: true, render: (d) => marginShort(d.pres_margin)},
  {key: "overperformance", label: "Shift", sort: true, defaultDir: -1, render: (d) => shiftBar(d.overperformance)},
  {key: "flipped", label: "Flipped", render: (d) => (d.flipped ? `${d.held_by} → ${d.winner}` : "")}
], {filters: [{key: "chamber", label: "All seats", options: [["US House", "U.S. House"], ["state legislature", "State legislature"]], test: (d, v) => d.chamber === v}],
    pageSize: 25, placeholder: "Search states and seats"}));
```

<p class="caption">Only races where both a Democrat and a Republican ran. "Result" is the Democrat's margin over the Republican (or the reverse) in the special election; "President ${baseline}" is how the same district voted for president.</p>

## What special elections said before, and what happened

```js
const specHist = national.history.filter((d) => d.specials_implied != null)
  .map((d) => ({...d, miss: d.house_margin == null ? null : d.specials_implied - d.house_margin}));
const specPast = specHist.filter((d) => d.miss != null);
display(html`<div class="table-wrap"><table class="wsu-table">
  <thead><tr><th>Cycle</th><th class="num">Races by late Sept.</th><th class="num">Average shift</th><th class="num">Points to a House vote of</th><th class="num">Actual House vote</th></tr></thead>
  <tbody>${specHist.map((d) => html`<tr>
    <td>${cycleLabel(d.year - 1)}</td>
    <td class="num">${d.specials_n}</td>
    <td class="num">${shift(d.specials_overperf)}</td>
    <td class="num">${margin(d.specials_implied)}</td>
    <td class="num">${d.house_margin == null ? html`<span class="muted">Nov. ${d.year}</span>` : margin(d.house_margin)}</td>
  </tr>`)}</tbody>
</table></div>`);
```

```js
const specRead = national.reads.find((d) => d.read === "specials");
const thisCycle = specHist.find((d) => d.house_margin == null);
const [lo, hi] = d3.extent(specPast, (d) => Math.round(d.miss));
const missRange = lo === hi ? `about ${lo} points` : `${lo} to ${hi} points`;
display(html`<p>To turn the average shift into a national number, add it to the last presidential result: if the country voted ${margin(thisCycle.last_pres_margin)} for president and specials are running ${shift(thisCycle.specials_overperf)}, they point to a House vote around ${margin(thisCycle.specials_implied)}. In each of the ${["zero", "one", "two", "three", "four"][specPast.length] ?? specPast.length} past cycles this pointed the right way but ran ${missRange} too Democratic, probably because the people who vote in specials lean more Democratic than the people who vote in November. Three cycles is not much to go on, so the model learns that offset cautiously and subtracts it: this cycle's ${margin(thisCycle.specials_implied)} becomes ${margin(specRead.dem_margin)}. That reading gets ${pct(specRead.weight)} of the weight in <a href="./national">our national estimate</a>, alongside the generic ballot and the fundamentals.</p>`);
```

<p class="caption">Special-election results from <a href="https://www.the-downballot.com">The Downballot</a>'s special elections Big Board (formerly Daily Kos Elections), updated every morning. The 2023–24 cycle isn't included in the source data we use.</p>
