---
title: How our forecast did
---

```js
import {tokens, pct, margin, date, raceLink, raceTable, sides, link, shareBar} from "./components/wsu.js";
import {sideInfo, ourPick, seatCard} from "./components/results.js";
const sc = FileAttachment("data/scorecard.json").json();
const races = FileAttachment("data/races.json").json();
const top = FileAttachment("data/topline.json").json();
```

```js
const t = (dark, tokens());
const byId = new Map(races.map((r) => [r.race_id, r]));
const asof = new Date(sc.asof).toLocaleDateString("en-US", {month: "long", day: "numeric", timeZone: "America/New_York"});
const S = sc.summary, all = S.all;
const officeName = {SEN: "Senate", GOV: "Governor", HOUSE: "House"};
const raceName = (r) => (r.office === "HOUSE" ? `House: ${r.label}` : `${r.state_name} ${r.office === "GOV" ? "governor" : "Senate"}${r.special ? " (special)" : ""}`);
const rows = sc.races.map((w) => ({...w, r: byId.get(w.id)})).filter((w) => w.r);
const called = rows.filter((w) => w.called);
const misses = called.filter((w) => !w.right);
const missBy = {D: misses.filter((w) => w.fav === "D").length, R: misses.filter((w) => w.fav === "R").length};
const party = {D: "Democratic", R: "Republican"};
const share = (a, b) => `${Math.round((100 * a) / b)}%`;
```

<p class="kicker">Scorecard · Results as of ${asof} · Final forecast ${date(sc.forecast_date)}</p>

# How our forecast did

```js
const oneWay = missBy.D === 0 ? "R" : missBy.R === 0 ? "D" : null;
display(html`<p class="dek">Our final forecast picked the winner in ${all.right} of the ${all.n} races called so far (${share(all.right, all.n)}). ${oneWay
  ? `Every one of its ${misses.length} misses went the same way: ${party[oneWay]} favorites who lost. No ${party[oneWay === "D" ? "R" : "D"]} favorite has lost.`
  : `Of its ${misses.length} misses, ${missBy.R} were Republican favorites who lost and ${missBy.D} were Democratic favorites who lost.`} Here's the full accounting, including how the other forecasters did on the same races.</p>`);
```

```js
display(shareBar({path: "/scorecard", label: "Share the scorecard", text: `How did the Who Shows Up 2026 midterm forecast do? It picked the winner in ${all.right} of ${all.n} called races. The full scorecard, against the other forecasters:`}));
```

```js
display(html`<div class="stat-row">
  <div class="s"><div class="k">Winners picked</div><div class="v">${all.right} of ${all.n}</div></div>
  <div class="s"><div class="k">Democratic favorites who won</div><div class="v">${S.fav_D.won} of ${S.fav_D.n}</div></div>
  <div class="s"><div class="k">Republican favorites who won</div><div class="v">${S.fav_R.won} of ${S.fav_R.n}</div></div>
  <div class="s"><div class="k">Misses our odds expected</div><div class="v">about ${Math.round(all.n - all.expected_right)}</div></div>
  <div class="s"><div class="k">Misses</div><div class="v">${misses.length}</div></div>
</div>`);
```

<p class="caption">Results and calls come from civicAPI. Counts are still being finalized, and a few races remain uncalled, so these numbers can still move a little. Races with candidates from only one party are left out.</p>

## The chambers

```js
const C = sc.chambers;
display(html`<div class="hero-grid">${seatCard("House", C.HOUSE, "House")}${seatCard("Senate", C.SEN, "Senate")}${seatCard("Governors", C.GOV, "Governors")}</div>`);
```

<p class="caption">Senate totals include the seats that weren't on the ballot this year. The colored marker is the number of Democratic seats called so far; the line is our forecast's most likely number. For the national House vote, our final forecast expected Democrats to win by 7.5 points (80% range: 5.0 to 10.0); the Cook Political Report's <a href="https://www.cookpolitical.com/vote-tracker/2026/house">vote tracker</a> had Democrats up 12.8 as of November 7.</p>

## When we said 90%, did it happen 90% of the time?

```js
const cal = sc.calibration.map((d) => ({...d, rate: d.won / d.n, label: `${Math.round(d.lo * 100)}–${Math.round(d.hi * 100)}%`}));
display(resize((w) => Plot.plot({
  width: Math.min(w, 720), height: Math.min(w, 720) * 0.62, marginLeft: 52, marginBottom: 44, marginRight: 20, marginTop: 40,
  x: {domain: [0.5, 1], tickFormat: "%", label: "Our favorite's chance →", grid: true},
  y: {domain: [0, 1], tickFormat: "%", label: "↑ How often the favorite won", grid: true},
  r: {range: [4, 22]},
  style: {background: "transparent", color: t["ink-3"], fontSize: "12px"},
  marks: [
    Plot.line([[0.5, 0.5], [1, 1]], {stroke: t.axis, strokeDasharray: "4,4"}),
    Plot.text([[0.72, 0.75]], {text: () => "perfectly calibrated", rotate: -38, fill: t["ink-3"], fontSize: 11}),
    Plot.dot(cal, {x: "said", y: "rate", r: "n", fill: t.ink, fillOpacity: 0.8, stroke: t.surface, strokeWidth: 2}),
    Plot.text(cal.filter((d) => d.n <= 100), {x: "said", y: "rate", text: (d) => `${d.won} of ${d.n}`, dy: -20, fill: t.ink, fontWeight: 600}),
    Plot.text(cal.filter((d) => d.n > 100), {x: "said", y: "rate", text: (d) => `${d.won} of ${d.n}`, dx: -28, textAnchor: "end", fill: t.ink, fontWeight: 600}),
    Plot.tip(cal, Plot.pointer({x: "said", y: "rate", title: (d) => `Favorites at ${d.label}\nAverage chance we gave: ${pct(d.said)}\nWon: ${d.won} of ${d.n} (${pct(d.rate)})`}))
  ]
})));
```

```js
const big = cal.find((d) => d.lo >= 0.97), mid = cal.filter((d) => d.lo >= 0.6 && d.lo < 0.97);
const midWon = d3.sum(mid, (d) => d.won), midN = d3.sum(mid, (d) => d.n), midSaid = d3.sum(mid, (d) => d.said * d.n) / midN;
display(html`<p>Each dot groups races by how sure we were about the favorite; bigger dots hold more races. A well-calibrated forecast's dots sit on the dashed line. Ours did fine at the extremes: favorites we gave 97% or better won ${big ? `${big.won} of ${big.n}` : "nearly all"} races. In the middle it was overconfident: favorites at 60% to 97% won ${midWon} of ${midN} (${pct(midWon / midN)}), when our odds averaged ${pct(midSaid)}. Nearly all of those misses ran in the same direction, which is what happens when one shared assumption is off (here, how many people would vote and for whom) rather than when races miss independently.</p>`);
```

## Forecast vs. result, race by race

```js
const officePick = view(Inputs.radio(["All", "House", "Senate", "Governor"], {value: "All", label: "Show"}));
```

```js
const offKey = {All: null, House: "HOUSE", Senate: "SEN", Governor: "GOV"}[officePick];
const pts = rows.filter((w) => w.graded && (!offKey || w.office === offKey));
const lim = Math.ceil(Math.min(80, Math.max(30, d3.max(pts, (w) => Math.max(Math.abs(w.margin), Math.abs(w.med))) ?? 30)) / 10) * 10;
const winColor = (w) => { const I = sideInfo(w.r); return I.tag(w.margin > 0 ? "D" : "R") === "I" ? t.ind : w.margin > 0 ? t.dem : t.rep; };
display(resize((w) => Plot.plot({
  width: Math.min(w, 760), height: Math.min(w, 760) * 0.8, marginLeft: 56, marginBottom: 44, marginRight: 20,
  x: {domain: [-lim, lim], label: "Our forecast's most likely margin →", tickFormat: (d) => (d === 0 ? "Even" : margin(d).replace(".0", "")), grid: true},
  y: {domain: [-lim, lim], label: "↑ Actual margin", tickFormat: (d) => (d === 0 ? "Even" : margin(d).replace(".0", "")), grid: true},
  style: {background: "transparent", color: t["ink-3"], fontSize: "12px"},
  marks: [
    Plot.rectY([{}], {x1: -lim, x2: 0, y1: 0, y2: lim, fill: t.dem, fillOpacity: 0.05}),
    Plot.rectY([{}], {x1: 0, x2: lim, y1: -lim, y2: 0, fill: t.rep, fillOpacity: 0.05}),
    Plot.ruleX([0], {stroke: t.axis}), Plot.ruleY([0], {stroke: t.axis}),
    Plot.line([[-lim, -lim], [lim, lim]], {stroke: t["ink-3"], strokeDasharray: "4,4"}),
    Plot.dot(pts, {x: "med", y: "margin", r: (w) => (w.right ? 3.5 : 5.5), fill: winColor, fillOpacity: 0.75,
      stroke: (w) => (w.right ? t.surface : t.ink), strokeWidth: (w) => (w.right ? 1 : 2)}),
    Plot.text([[-lim * 0.55, lim * 0.9]], {text: () => "Republican favored, Democrat won", fill: t["ink-2"], fontSize: 11.5}),
    Plot.text([[lim * 0.55, -lim * 0.9]], {text: () => "Democrat favored, Republican won", fill: t["ink-2"], fontSize: 11.5}),
    Plot.tip(pts, Plot.pointer({x: "med", y: "margin", title: (w) => { const I = sideInfo(w.r);
      return `${raceName(w.r)}\nOur forecast: ${ourPick(w.r, w)}, expected ${I.m(w.med)}\nResult: ${I.m(w.margin)} (${w.pct}% counted)\n${w.right ? "Our favorite won" : "Our favorite lost"}`; }}))
  ]
})));
```

```js
const M = sc.margins[offKey ?? "ALL"];
const toward = M.mean_miss >= 0 ? "Democrats" : "Republicans";
display(html`<p class="caption">${M.n} ${officePick === "All" ? "" : `${officePick.toLowerCase()} `}races with a near-final count and one candidate from each major party, each dot colored by the winning side; outlined dots are races where our favorite lost. On the dashed line, the result matched our most likely margin exactly. Dots above it are races where Democrats did better than we expected, and dots below it are races where Republicans did. The results landed above the line in ${M.toward_d} of ${M.n} races. On average they were ${Math.abs(M.mean_miss).toFixed(1)} points more favorable to ${toward} than our forecast, and ${M.inside} of ${M.n} (${share(M.inside, M.n)}) landed inside our 80% range, where 80% should have.</p>`);
```

```js
const tbl = ["HOUSE", "SEN", "GOV"].filter((k) => sc.margins[k]).map((k) => ({k, ...sc.margins[k]}));
display(html`<div class="table-wrap"><table class="wsu-table">
  <thead><tr><th>Office</th><th class="num">Races compared</th><th class="num">Average miss, and which way</th><th class="num">Average size of miss</th><th class="num">Inside our 80% range</th></tr></thead>
  <tbody>${tbl.map((d) => html`<tr><td>${officeName[d.k]}</td><td class="num">${d.n}</td><td class="num">${Math.abs(d.mean_miss).toFixed(1)} points toward ${d.mean_miss >= 0 ? "Democrats" : "Republicans"}</td><td class="num">${d.mean_abs.toFixed(1)} points</td><td class="num">${d.inside} of ${d.n} (${share(d.inside, d.n)})</td></tr>`)}</tbody></table></div>`);
```

## How the other forecasters did

```js
const F = sc.forecasters;
const kindName = {rater: "Expert ratings", model: "Statistical model", market: "Prediction market"};
display(html`<p>Every forecaster below published its final calls before Election Day; none of them fed into ours. Each row compares a forecaster with Who Shows Up <i>on the same races</i>: the ones that forecaster rated and that have been called. Raters and models that use categories (Safe, Likely, Lean) count as picking the side they lean toward; a Toss-up is no pick. PredictIt's favorite is whichever side its final price favored.</p>`);
display(html`<div class="table-wrap"><table class="wsu-table fc-table">
  <thead><tr><th>Forecaster</th><th class="num">Races</th><th class="num">Their picks<br><small>right · wrong · Toss-up</small></th><th class="num us">Our picks, same races<br><small>right · wrong</small></th><th class="num">Where we disagreed<br><small>we were right</small></th><th class="num">Their Toss-ups<br><small>our pick won</small></th></tr></thead>
  <tbody>${F.map((f) => { const dis = f.disagree.length, ours = f.disagree.filter((d) => d.ours_right).length;
    return html`<tr>
    <td><b>${f.short}</b><div class="cmp-p">${kindName[f.kind]}, final as of ${date(f.rated_on)}</div></td>
    <td class="num">${f.n}</td>
    <td class="num">${f.right} · ${f.wrong} · ${f.toss}</td>
    <td class="num us">${f.ours_right} · ${f.ours_wrong}</td>
    <td class="num">${dis ? `${ours} of ${dis}` : "never disagreed"}</td>
    <td class="num">${f.toss ? `${f.toss_ours_right} of ${f.toss}` : "–"}</td></tr>`; })}</tbody></table></div>`);
```

```js
const big3 = F.filter((f) => f.n >= 300), raters = F.filter((f) => f.kind !== "market");
const pi = F.find((f) => f.kind === "market");
const list = (xs) => (xs.length < 3 ? xs.join(" and ") : `${xs.slice(0, -1).join(", ")} and ${xs.at(-1)}`);
const more = big3.filter((f) => f.ours_right > f.right), same = big3.filter((f) => f.ours_right === f.right);
const tossN = d3.sum(big3, (f) => f.toss), tossOurs = d3.sum(big3, (f) => f.toss_ours_right);
const disN = d3.sum(raters, (f) => f.disagree.length), disOurs = d3.sum(raters, (f) => f.disagree.filter((d) => d.ours_right).length);
display(html`<p>Against the forecasters who rated nearly every race (${list(big3.map((f) => f.short))}), the trade-off is clear. ${more.length ? `We picked more winners than ${list(more.map((f) => f.short))}${same.length ? ` and as many as ${list(same.map((f) => f.short))}` : ""}, mostly because we always picked a side while they left ${d3.min(big3, (f) => f.toss)} to ${d3.max(big3, (f) => f.toss)} races as Toss-ups.` : ""} But they made fewer wrong calls: ${list(big3.map((f) => `${f.short} ${f.wrong}`))}, against our ${big3[0]?.ours_wrong}. In their Toss-ups, our pick won ${tossOurs} of ${tossN} times (${share(tossOurs, tossN)}), about what a coin would do. And in the ${disN} cases where a rater or model picked a different winner from ours, ${disOurs === 0 ? "they were right every time" : `we were right ${disOurs} time${disOurs === 1 ? "" : "s"} and they were right ${disN - disOurs}`}.${pi ? ` Against PredictIt's final prices, our forecast was ${pi.ours_brier < pi.brier ? "a little more" : "a little less"} accurate (a Brier score of ${pi.ours_brier.toFixed(3)} for us and ${pi.brier.toFixed(3)} for the market on its ${pi.n} called races; lower is better).` : ""}</p>`);
```

```js
const disRows = F.flatMap((f) => f.disagree.map((d) => ({f, d, w: rows.find((x) => x.id === d.id)}))).filter((x) => x.w);
display(disRows.length ? html`<details><summary>Every race where another forecaster picked a different winner (${disRows.length})</summary>
  <div class="table-wrap"><table class="wsu-table"><thead><tr><th>Race</th><th>Forecaster</th><th>Their call</th><th>Our forecast</th><th>Winner</th></tr></thead>
  <tbody>${disRows.map(({f, d, w}) => { const I = sideInfo(w.r);
    return html`<tr><td>${raceLink(w.r, raceName(w.r))}</td><td>${f.short}</td><td>${typeof d.theirs === "number" ? `${I.last(d.theirs > 0.5 ? "D" : "R")} ${pct(Math.max(d.theirs, 1 - d.theirs))}` : d.theirs}</td><td>${ourPick(w.r, w)}</td><td>${I.last(w.called)} <span class="miss-chip ${d.ours_right ? "right" : "wrong"}">${d.ours_right ? "we were right" : "they were right"}</span></td></tr>`; })}</tbody></table></div></details>` : html``);
```

<p class="caption">Ratings are each outlet's final published ratings, collected before Election Day for our <a href="./compare">Compare page</a>; PredictIt prices are from its free data feed on ${date(sc.forecast_date)}. Margins aren't compared here because most of these forecasters publish categories, not margins.</p>

## Every miss

```js
const missRows = misses.map((w) => ({...w, conf: Math.max(w.p, 1 - w.p)})).sort((a, b) => b.conf - a.conf);
display(html`<div class="table-wrap"><table class="wsu-table">
  <thead><tr><th>Race</th><th>Our favorite</th><th>Winner</th><th class="num">Expected</th><th class="num">Result</th></tr></thead>
  <tbody>${missRows.map((w) => { const I = sideInfo(w.r);
    return html`<tr><td>${raceLink(w.r, raceName(w.r))}</td><td>${ourPick(w.r, w)}</td><td>${I.name(w.called)} (${I.tag(w.called)})</td><td class="num">${I.m(w.med)}</td><td class="num">${I.m(w.margin)}${w.pct != null && w.pct < 95 ? html`<div class="cmp-p">${w.pct}% counted</div>` : ""}</td></tr>`; })}</tbody></table></div>`);
```

## Every called race

```js
const allRows = called.map((w) => { const I = sideInfo(w.r);
  return {...w, race_id: w.id, label: raceName(w.r), conf: Math.max(w.p, 1 - w.p), winner: `${I.name(w.called)} (${I.tag(w.called)})`,
    _search: [raceName(w.r), w.r.state_name, w.r.state_po, w.r.dem_candidate, w.r.rep_candidate].filter(Boolean).join(" ").toLowerCase()}; });
display(raceTable(allRows, [
  {key: "label", label: "Race", sort: true, render: (w) => raceLink(w.r, w.label)},
  {key: "conf", label: "Our forecast", num: true, sort: true, defaultDir: -1, render: (w) => ourPick(w.r, w)},
  {key: "winner", label: "Winner", sort: true},
  {key: "med", label: "Expected", num: true, sort: true, render: (w) => sideInfo(w.r).m(w.med)},
  {key: "margin", label: "Result", num: true, sort: true, render: (w) => sideInfo(w.r).m(w.margin)},
  {key: "miss", label: "vs. forecast", num: true, sort: true, sortValue: (w) => (w.graded ? w.miss : -999), render: (w) => (w.graded ? `${Math.abs(w.miss).toFixed(1)} more ${sideInfo(w.r).last(w.miss > 0 ? "D" : "R")}` : "")},
  {key: "right", label: "", sort: true, render: (w) => html`<span class="miss-chip ${w.right ? "right" : "wrong"}">${w.right ? "✓" : "✗"}</span>`}
], {placeholder: "Search races, states, candidates", pageSize: 25, sort: {key: "conf", dir: 1},
  filters: [
    {key: "office", label: "All offices", options: [["HOUSE", "House"], ["SEN", "Senate"], ["GOV", "Governor"]], test: (w, v) => w.office === v},
    {key: "right", label: "Hits and misses", options: [["1", "Our favorite won"], ["0", "Our favorite lost"]], test: (w, v) => String(+w.right) === v}
  ]}));
```

<p class="caption">"Expected" is our final forecast's most likely margin; "vs. forecast" is how far the result landed from it, shown only for races with a near-final count and one candidate from each major party. Click a race for its full page.</p>

## What we're taking from this

The forecast saw the direction right: it had Democrats favored for the House (${pct(top.p_house_d)}) and the Senate (${pct(top.p_senate_d)}), and those calls held. Where it missed was size. It expected roughly a normal midterm electorate, and far more people voted than that, more of them in Democratic-leaning places. The model allowed for races to miss together, since every simulation shares one national environment, but not by this much, so it was too sure of Republicans in seats that moved toward Democrats.

The model will be rebuilt around those lessons once the voter files, which show who actually voted, come out over the coming months. Until then, the final forecast stays up exactly as it was on November 3, so anyone can check it against the results. [How the model works](./methodology) · [The final forecast](./) · [The Turnout](https://theturnout.substack.com), our newsletter.
