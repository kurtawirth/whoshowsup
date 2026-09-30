---
title: Past results
---

```js
import {tokens, tip, isTouch} from "./components/wsu.js";
import * as topojson from "npm:topojson-client";
const data = FileAttachment("data/counties.json").json();
const topo = FileAttachment("data/counties-10m.json").json();
const states = FileAttachment("data/states.json").json();
```

```js
const t = (dark, tokens());
const params = new URLSearchParams(location.search);
const poOf = Object.fromEntries(Object.entries(states.fips).map(([po, f]) => [f, po]));
const counties = topojson.feature(topo, topo.objects.counties).features;
const stateShapes = topojson.feature(topo, topo.objects.states).features;
// Alaska reports by legislative district rather than borough: shown as one statewide unit
const alaska = stateShapes.find((s) => s.id === "02");
if (alaska) counties.push({...alaska, id: "02000", properties: {name: "Alaska"}});
const nameOf = (fips) => data.names[fips] ?? counties.find((f) => f.id === fips)?.properties.name ?? fips;
const officeName = {PRES: "President", SEN: "Senate", GOV: "Governor"};
const electionLabel = (k) => { const [o, y, sp] = k.split("-"); return `${officeName[o]} ${y}${sp ? " (special)" : ""}`; };
const lean = (m) => (m == null || isNaN(m) ? "–" : Math.abs(m) < 0.05 ? "Even" : m > 0 ? `D+${m.toFixed(1)}` : `R+${(-m).toFixed(1)}`);
const marginOf = (v) => (v && v[0] + v[1] > 0 ? (100 * (v[0] - v[1])) / (v[0] + v[1]) : null);
const shareOf = (v, i) => (v && v[2] ? (100 * v[i]) / v[2] : null);
// the same office four years earlier (presidential: the last presidential race), for the shift view
const previousKey = (k) => { const [o, y, sp] = k.split("-"); return `${o}-${+y - 4}${sp ? "-special" : ""}`; };
// remembered across state and election changes (those rebuild the controls)
const memo = {election: params.get("election") ?? "PRES-2024", shift: params.get("mode") === "shift"};
// Browser history: the address bar follows the view. Opening a state or a county adds a step the back button
// returns to; changing the election or Result/Shift just updates the address.
const nav = {first: true, target: null, timer: null, cur: null};
const viewQuery = ({state, county, election, shift}) => {
  const q = new URLSearchParams();
  if (state) q.set("state", state);
  if (county) q.set("county", county);
  if (election && election !== "PRES-2024") q.set("election", election);
  if (shift) q.set("mode", "shift");
  const s = q.toString();
  return s ? `?${s}` : "";
};
const queryView = (search) => {
  const q = new URLSearchParams(search);
  return {state: (q.get("state") ?? "").toUpperCase(), county: q.get("county"), election: q.get("election") ?? "PRES-2024", shift: q.get("mode") === "shift"};
};
// commit after a short pause, so a click that changes both the state and the county is one step
nav.commit = () => {
  const qs = viewQuery(nav.cur);
  if (qs === location.search) { if (nav.target === qs) nav.target = null; nav.first = false; return; }
  const was = queryView(location.search);
  const newStep = !nav.first && nav.target === null && (was.state !== nav.cur.state || (was.county ?? null) !== (nav.cur.county ?? null));
  history[newStep ? "pushState" : "replaceState"](null, "", location.pathname + qs);
  if (nav.target === qs) nav.target = null;
  nav.first = false;
};
```

<p class="kicker">Past results · County by county</p>

# How every county voted

<p class="dek">Pick a state and an election to see how its counties voted, or how they shifted since the last time. Tap or click a county for its full history: every presidential race since 2000, recent Senate and governor races, and turnout. These are past results only; they are not part of the forecast.</p>

```js
const stateList = Object.entries(states.names).filter(([po]) => po !== "DC").sort((a, b) => a[1].localeCompare(b[1]));
const stateInput = Inputs.select([["", "All states"], ...stateList], {label: "State", width: 190, format: ([, n]) => n, valueof: ([po]) => po,
  value: stateList.find(([po]) => po === (params.get("state") ?? "").toUpperCase()) ? (params.get("state") ?? "").toUpperCase() : ""});
const statePo = Generators.input(stateInput);
```

```js
const inState = (fips) => !statePo || poOf[fips.slice(0, 2)] === statePo;
const available = data.elections.map((e) => e.key).filter((k) => Object.entries(data.results).some(([f, r]) => inState(f) && r[k]));
const electionInput = Inputs.select(available.slice().reverse(), {label: "Election", format: electionLabel, width: 210,
  value: available.includes(memo.election) ? memo.election : available.findLast((k) => k.startsWith("PRES")) ?? available.at(-1)});
const election = Generators.input(electionInput);
```

```js
memo.election = election;
const prevKey = previousKey(election);
const canShift = Object.values(data.results).some((r) => r[prevKey]);
const modeChoices = canShift ? ["Result", `Shift since ${electionLabel(prevKey).replace(/^\w+ /, "")}`] : ["Result"];
const modeInput = Inputs.radio(modeChoices, {value: memo.shift && canShift ? modeChoices[1] : "Result"});
// remember the choice the moment it's made, so rebuilding the controls keeps it
modeInput.addEventListener("input", () => { memo.shift = modeInput.value !== "Result"; });
const mode = Generators.input(modeInput);
```

```js
const picked = Mutable(params.get("county"));
const pick = (fips) => { picked.value = fips; };
```

```js
// Search any county by name (jumps to its state)
const allNames = Object.keys(data.results).filter((f) => poOf[f.slice(0, 2)])
  .map((f) => [`${nameOf(f)}, ${states.names[poOf[f.slice(0, 2)]]}`, f]);
const byLabel = new Map(allNames);
const search = Inputs.text({placeholder: "Find a county", datalist: allNames.map(([l]) => l), width: 240});
search.addEventListener("input", () => {
  const f = byLabel.get(search.value);
  if (!f) return;
  const po = poOf[f.slice(0, 2)];
  if (stateInput.value !== po) { stateInput.value = po; stateInput.dispatchEvent(new Event("input", {bubbles: true})); }
  pick(f);
});
```

```js
// all the controls in one row (re-laid out when the election list changes with the state)
// from a state (or a county in it), one click back to the whole country
function backToNation() {
  pick(null);
  search.value = "";
  stateInput.value = "";
  stateInput.dispatchEvent(new Event("input", {bubbles: true}));
}
const back = statePo ? html`<button class="pr-back" type="button" onclick=${backToNation}>← Back to the national map</button>` : "";
display(html`${back ? html`<div class="pr-backrow">${back}</div>` : ""}<div class="pr-controls">${stateInput}${electionInput}${modeInput}${search}</div>`);
```

```js
// keep the address bar in step with the view
nav.cur = {state: statePo, county: picked, election, shift: mode !== "Result"};
clearTimeout(nav.timer);
nav.timer = setTimeout(nav.commit, 60);
```

```js
// back / forward: put the view the address describes back on screen
function restoreView() {
  const v = queryView(location.search);
  nav.target = viewQuery(v);
  setTimeout(() => { nav.target = null; }, 1500);
  memo.election = v.election;
  memo.shift = v.shift;
  if ((v.county ?? null) !== (picked ?? null)) { search.value = ""; pick(v.county); }
  if (stateInput.value !== v.state) {
    // a new state rebuilds the election and Result/Shift controls from memo
    stateInput.value = v.state;
    stateInput.dispatchEvent(new Event("input", {bubbles: true}));
    return;
  }
  if (electionInput.value !== v.election && available.includes(v.election)) {
    electionInput.value = v.election;
    electionInput.dispatchEvent(new Event("input", {bubbles: true}));
    return;
  }
  const want = v.shift && modeChoices.length > 1 ? modeChoices[1] : "Result";
  if (modeInput.value !== want) { modeInput.value = want; modeInput.dispatchEvent(new Event("input", {bubbles: true})); }
}
addEventListener("popstate", restoreView);
invalidation.then(() => removeEventListener("popstate", restoreView));
```

```js
const shift = mode !== "Result";
const valueOf = (fips) => {
  const r = data.results[fips];
  if (!r) return null;
  const m = marginOf(r[election]);
  if (!shift) return m;
  const m0 = marginOf(r[prevKey]);
  return m == null || m0 == null ? null : m - m0;
};
const span = shift ? 25 : 50;
const neutral = dark ? "#3a3936" : "#ecebe6";
const color = d3.scaleDiverging([-span, 0, span], d3.piecewise(d3.interpolateRgb, [t.rep, neutral, t.dem])).clamp(true);
const shown = counties.filter((f) => poOf[f.id.slice(0, 2)] && (f.id.slice(0, 2) !== "02" || f.id === "02000") && inState(f.id));
// statewide (or national) totals for this election
const tot = shown.reduce((a, f) => { const v = data.results[f.id]?.[election]; if (v) { a[0] += v[0]; a[1] += v[1]; a[2] += v[2]; a.n++; a.d += v[0] > v[1]; } return a; }, Object.assign([0, 0, 0], {n: 0, d: 0}));
// States whose results aren't broken down by county
const NOTES = {
  AK: "Alaska doesn't report election results by borough or county. It reports them by state legislative district, whose lines are redrawn every ten years, so there's no stable local unit to map. Alaska is shown here as one statewide unit, with its full results history.",
  LA: "Louisiana's counties are called parishes."
};
// ...and elections that need a word of context
const ELECTION_NOTES = {
  "GA|SEN-2020": "No candidate won a majority in November, so this race went to a January 2021 runoff, which Democrat Jon Ossoff won. The map shows the November vote.",
  "GA|SEN-2020-special": "This special election put every candidate on one November ballot, several from each party; the map adds them up by party. No one won a majority, and Democrat Raphael Warnock won the January 2021 runoff.",
  "GA|SEN-2022": "No candidate won a majority in November, so this race went to a December runoff, which Democrat Raphael Warnock also won. The map shows the November vote.",
  "LA|SEN-2020": "Louisiana puts every candidate on one ballot; the map adds up each party's candidates.",
  "LA|GOV-2019": "Louisiana puts every candidate on one ballot in October; this is the November runoff between the top two.",
  "LA|GOV-2023": "Louisiana puts every candidate on one ballot; the map adds up each party's candidates. Republican Jeff Landry won outright in October."
};
const notes = [statePo && NOTES[statePo], statePo && ELECTION_NOTES[`${statePo}|${election}`]].filter(Boolean);
if (notes.length) display(html`<div class="pr-note">${notes.map((n) => html`<p>${n}</p>`)}</div>`);
display(tot.n ? html`<p class="pr-summary"><b>${electionLabel(election)}, ${statePo ? states.names[statePo] : "all counties"}:</b>
  ${statePo || election.startsWith("PRES") ? html`${lean(marginOf(tot))} overall (Democrats ${shareOf(tot, 0).toFixed(1)}%, Republicans ${shareOf(tot, 1).toFixed(1)}%). ` : ""}${statePo === "AK" ? "" : `Democrats carried ${tot.d.toLocaleString()} of ${tot.n.toLocaleString()} ${statePo === "LA" ? "parishes" : statePo === "VA" ? "counties and independent cities" : "counties"}${statePo ? "" : " with a race"}.`}</p>` : html`<p class="caption">No county results for this election here.</p>`);
```

```js
function countyMap(width) {
  const focus = statePo ? stateShapes.find((s) => poOf[s.id] === statePo) : null;
  let projection;
  if (focus) {
    const [[lon0, lat0], [lon1, lat1]] = d3.geoBounds(focus);
    const center = lon1 < lon0 ? (lon0 + lon1 + 360) / 2 : (lon0 + lon1) / 2;  // Alaska crosses the 180th meridian
    projection = d3.geoConicEqualArea().parallels([lat0 + (lat1 - lat0) / 6, lat1 - (lat1 - lat0) / 6])
      .rotate([-center, 0]).fitExtent([[8, 8], [967, 602]], focus);
  } else {
    projection = d3.geoAlbersUsa().fitExtent([[4, 4], [971, 606]], {type: "FeatureCollection", features: shown});
  }
  const path = d3.geoPath(projection);
  const [[x0, y0], [x1, y1]] = path.bounds(focus ?? {type: "FeatureCollection", features: shown});
  const vb = [x0 - 6, y0 - 6, x1 - x0 + 12, y1 - y0 + 12];
  const height = Math.min(width * (vb[3] / vb[2]), 620);
  const svg = d3.create("svg").attr("viewBox", vb).attr("width", width).attr("height", height)
    .attr("role", "img").attr("aria-label", `County map of ${electionLabel(election)} results${statePo ? ` in ${states.names[statePo]}` : ""}`)
    .style("max-width", "100%").style("height", "auto").style("display", "block");
  const tt = tip();
  const rows = (f) => {
    const r = data.results[f.id] ?? {}, v = r[election], m = marginOf(v);
    const out = [["t-title", f.id === "02000" ? "Alaska (statewide)" : `${nameOf(f.id)}, ${statePo ? states.names[statePo] : poOf[f.id.slice(0, 2)]}`]];
    if (!v) return [...out, ["t-sub", "No result for this election"]];
    out.push(["t-val", lean(m)], ["t-sub", `Democrats ${shareOf(v, 0).toFixed(1)}%, Republicans ${shareOf(v, 1).toFixed(1)}%`]);
    if (shift && r[prevKey]) out.push(["t-sub", `Shift since ${prevKey.split("-")[1]}: ${m - marginOf(r[prevKey]) >= 0 ? "toward Democrats" : "toward Republicans"} by ${Math.abs(m - marginOf(r[prevKey])).toFixed(1)}`]);
    return out;
  };
  svg.append("g").selectAll("path").data(shown).join("path")
    .attr("d", path).attr("fill", (f) => { const v = valueOf(f.id); return v == null ? t.surface : color(v); })
    .attr("stroke", (f) => (valueOf(f.id) == null ? t["ink-3"] : t.surface)).attr("stroke-dasharray", (f) => (valueOf(f.id) == null ? "2,2" : null))
    .attr("stroke-width", statePo ? 0.6 : 0.15).attr("vector-effect", "non-scaling-stroke")
    .style("cursor", "pointer")
    .on("pointerenter", function (event, f) { if (isTouch(event)) return; d3.select(this).attr("stroke", t.ink).attr("stroke-width", 1.5).raise(); tt.show(event, rows(f)); })
    .on("pointermove", (event) => { if (!isTouch(event)) tt.move(event); })
    .on("pointerleave", function (event, f) { if (isTouch(event)) return; d3.select(this).attr("stroke", valueOf(f.id) == null ? t["ink-3"] : t.surface).attr("stroke-width", statePo ? 0.6 : 0.15); tt.hide(); })
    .on("click", (event, f) => {
      tt.hide();
      pick(f.id);
      const po = poOf[f.id.slice(0, 2)];
      if (!statePo && po) { stateInput.value = po; stateInput.dispatchEvent(new Event("input", {bubbles: true})); }
    });
  // state borders on top
  if (!statePo) svg.append("path").datum(topojson.mesh(topo, topo.objects.states, (a, b) => a !== b && a.id !== "02" && b.id !== "02"))
    .attr("d", path).attr("fill", "none").attr("stroke", t.surface).attr("stroke-width", statePo ? 0 : 1).attr("vector-effect", "non-scaling-stroke");
  if (picked && data.results[picked] && inState(picked)) {
    const f = shown.find((f) => f.id === picked);
    if (f) svg.append("path").datum(f).attr("d", path).attr("fill", "none").attr("stroke", t.ink).attr("stroke-width", 2.5).attr("vector-effect", "non-scaling-stroke").attr("pointer-events", "none");
  }
  return svg.node();
}
display(resize((w) => countyMap(w)));
```

```js
// legend: a diverging bar with its ends labeled
const legendW = 260;
const lg = d3.create("svg").attr("width", legendW).attr("height", 34);
const grad = lg.append("defs").append("linearGradient").attr("id", "pr-grad");
d3.range(0, 1.01, 0.1).forEach((s) => grad.append("stop").attr("offset", s).attr("stop-color", color(-span + 2 * span * s)));
lg.append("rect").attr("x", 0).attr("y", 0).attr("width", legendW).attr("height", 10).attr("rx", 3).attr("fill", "url(#pr-grad)");
lg.selectAll("text").data([[0, shift ? `${span} pts toward R` : `R+${span}`, "start"], [legendW / 2, shift ? "No change" : "Even", "middle"], [legendW, shift ? `${span} toward D` : `D+${span}`, "end"]])
  .join("text").attr("x", (d) => d[0]).attr("y", 28).attr("text-anchor", (d) => d[2]).attr("fill", t["ink-3"]).attr("font-size", 12).attr("font-family", "var(--sans)").text((d) => d[1]);
display(html`<div class="pr-legend">${lg.node()}<span class="muted">${shift ? "Change in the Democratic-minus-Republican margin." : "Democratic-minus-Republican margin."} Pale: close to even. White with a dashed outline: no result.</span></div>`);
```

```js
// the picked county's full history
function countyPanel(fips) {
  const r = data.results[fips], cv = data.cvap[fips] ?? {}, po = poOf[fips.slice(0, 2)];
  const hist = data.elections.filter((e) => r[e.key]).map((e) => {
    const v = r[e.key];
    return {...e, label: electionLabel(e.key), m: marginOf(v), d: shareOf(v, 0), r: shareOf(v, 1), total: v[2],
      turnout: (cv[String(e.year)] ?? cv[String(e.year - 1)]) ? v[2] / (cv[String(e.year)] ?? cv[String(e.year - 1)]) : null};
  });
  const chart = Plot.plot({
    width: Math.min(width, 640), height: 220, marginLeft: 48,
    x: {label: null, ticks: [...new Set(hist.map((d) => d.year))],
      tickFormat: (y) => (width < 560 || new Set(hist.map((d) => d.year)).size > 9 ? `'${String(y).slice(2)}` : String(y))},
    y: {label: "Margin (D minus R)", grid: true, tickFormat: (v) => (v === 0 ? "Even" : v > 0 ? `D+${v}` : `R+${-v}`)},
    symbol: {domain: ["President", "Senate", "Governor"], range: ["circle", "triangle", "square"], legend: true},
    style: {background: "transparent", color: t["ink-3"], fontSize: "12px"},
    marks: [
      Plot.ruleY([0], {stroke: t.axis}),
      Plot.line(hist.filter((d) => d.office === "PRES"), {x: "year", y: "m", stroke: t["ink-3"], strokeWidth: 1.5}),
      Plot.dot(hist, {x: "year", y: "m", symbol: (d) => officeName[d.office], r: 5, fill: (d) => (d.m >= 0 ? t.dem : t.rep), stroke: t.surface, strokeWidth: 1.5}),
      Plot.tip(hist, Plot.pointer({x: "year", y: "m", title: (d) => `${d.label}\n${lean(d.m)}${d.turnout ? `\nTurnout ${Math.round(100 * d.turnout)}% of eligible adults` : ""}`}))
    ]
  });
  const s = data.sensitivity[fips];
  const waveText = s ? `When a party's turnout surges or sags across ${states.names[po]}, this county's ${waveWord(s[0])} for Democrats (${s[0].toFixed(1)}x the state's swing) and ${waveWord(s[1])} for Republicans (${s[1].toFixed(1)}x).` : "";
  return html`<div class="pr-panel">
    <h2>${fips === "02000" ? "Alaska (statewide)" : `${nameOf(fips)}, ${states.names[po]}`}</h2>
    ${waveText ? html`<p>${waveText}</p>` : ""}
    ${chart}
    <div class="table-wrap"><table class="wsu-table">
      <thead><tr><th>Election</th><th class="num">Democrats</th><th class="num">Republicans</th><th class="num">Margin</th><th class="num">Votes</th><th class="num">Turnout</th></tr></thead>
      <tbody>${hist.slice().reverse().map((d) => html`<tr><td>${d.label}</td><td class="num">${d.d.toFixed(1)}%</td><td class="num">${d.r.toFixed(1)}%</td>
        <td class="num"><b style="color:${d.m >= 0 ? t["party-d"] : t["party-r"]}">${lean(d.m)}</b></td><td class="num">${d.total.toLocaleString()}</td>
        <td class="num">${d.turnout ? `${Math.round(100 * d.turnout)}%` : "–"}</td></tr>`)}</tbody>
    </table></div>
    <p class="caption">Turnout is votes cast in that race as a share of the county's adult citizens (Census estimates, available from 2008; odd-year races use the previous year's estimate). Senate and governor results by county are available from 2018 on.</p>
  </div>`;
}
function waveWord(b) { return b >= 1.15 ? "turnout swings harder than the state's" : b <= 0.85 ? "turnout swings less than the state's" : "turnout moves about in step with the state"; }
display(picked && data.results[picked] ? countyPanel(picked) : html`<p class="caption">${isTouchDevice() ? "Tap" : "Click"} a county for its full history.</p>`);
function isTouchDevice() { return matchMedia("(pointer: coarse)").matches; }
```

<p class="caption">County results from the MIT Election Data + Science Lab (presidential 2000-2024; Senate and governor 2018, 2022 and 2024); for races those files don't cover (2020 Senate and governor, 2024 governor, and the odd-year governor races), official results by county from the <a href="https://doi.org/10.7910/DVN/RV80FW">2020 official results collection</a> on Harvard Dataverse, <a href="https://openelections.net">OpenElections</a> (Kansas 2020), the Louisiana Secretary of State (2019), and each race's Wikipedia results table, all checked against official statewide totals. Where one party had several candidates on the same ballot (Georgia's 2020 special election, Louisiana, Alaska), each party's candidates are added together. Arkansas's 2020 Senate race had no Democratic candidate and isn't shown. A handful of places that report separately from their county (Kansas City, Missouri, for example) are left out. Map shapes from the U.S. Census Bureau via us-atlas.</p>
