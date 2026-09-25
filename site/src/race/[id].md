---
title: Race forecast
---

```js
import {tokens, pct, pctPair, margin, date, probBar, ratingPill, favoriteText, raceLink, link} from "../components/wsu.js";
import {marginRange, pollChart, probHistory, pastResults} from "../components/charts.js";
const races = FileAttachment("../data/races.json").json();
const details = FileAttachment("../data/race_detail.json").json();
const top = FileAttachment("../data/topline.json").json();
```

```js
const t = (dark, tokens());
const id = observable.params.id;
const r = races.find((x) => x.race_id === id);
const det = details[id] ?? {polls: [], past: [], history: []};
const officeName = {HOUSE: "House", SEN: "Senate", GOV: "Governor"}[r.office];
const place = r.office === "HOUSE" ? `${r.state_name}'s ${r.district === 0 ? "at-large district" : `${ordinal(r.district)} District`}` : r.state_name;
function ordinal(n) { const s = ["th", "st", "nd", "rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); }
const first = (s) => String(s ?? "").split(";")[0].trim();
const dName = r.race_type === "independent" ? r.race_note : first(r.dem_candidate) || "Democrat";
const rName = first(r.rep_candidate) || "Republican";
const dTag = r.race_type === "independent" ? "I" : "D";
const fixed = r.race_type === "same_party";
const heading = fixed ? `${place} ${officeName === "House" ? "House" : officeName} race`
  : `${place}${r.office === "HOUSE" ? "" : ` ${officeName}${r.special ? " special election" : ""}`}`;
```

```js
display(html`<p class="kicker"><a href="${link(r.office === "HOUSE" ? "house" : r.office === "SEN" ? "senate" : "governors")}">${officeName}</a> · ${r.state_name} · Updated ${date(top.forecast_date)}</p>`);
```

```js
display(fixed ? html`<h1 class="race-title">${heading}</h1>`
  : html`<h1 class="race-title">${heading}:<span class="matchup">${dName} vs. ${rName}</span></h1>`);
```

```js
if (fixed) {
  display(html`<p class="dek">Only ${r.race_note === "D" ? "Democrats" : "Republicans"} are on the November ballot here (${String(r.dem_candidate ?? r.rep_candidate ?? "").replaceAll(";", " and")}), so the seat is certain to stay ${r.race_note === "D" ? "Democratic" : "Republican"}.</p>`);
} else {
  const pD = r.p_dem, lead = pD >= 0.5;
  display(html`<div class="race-head">
    <div class="race-cand"><div class="name">${dName} <span class="party-chip ${dTag === "I" ? "i" : "d"}">${dTag}</span></div>
      <div class="pct" style="color:${dTag === "I" ? t.ind : t.dem}">${pctPair(pD)[0]}</div>
      <div class="role">${r.inc_side === 1 ? "Incumbent" : ""}</div></div>
    <div class="race-vs">chance of winning</div>
    <div class="race-cand right"><div class="name"><span class="party-chip r">R</span> ${rName}</div>
      <div class="pct" style="color:${t.rep}">${pctPair(pD)[1]}</div>
      <div class="role">${r.inc_side === -1 ? "Incumbent" : ""}</div></div>
  </div>`);
  display(probBar(pD, {dLabel: dName, rLabel: rName, dColor: dTag === "I" ? t.ind : t.dem}));
  display(html`<p class="dek" style="margin-top:18px">${lead ? dName : rName} wins in ${pct(Math.max(pD, 1 - pD))} of our simulations, ${oddsText(Math.max(pD, 1 - pD))}. The most likely result is ${margin(r.margin_median).replace("D+", `${dTag}+`)}. ${ratingSentence(r)}</p>`);
}
function oddsText(p) { return p >= 0.95 ? "a near-certain win" : p >= 0.8 ? "a clear favorite" : p >= 0.6 ? "a modest favorite" : "close to a coin flip"; }
function ratingSentence(r) { return `We rate it <b>${r.rating}</b>.`.replace(/<\/?b>/g, ""); }
```

```js
if (!fixed && det.quantiles) {
  display(html`<h2>The range of outcomes</h2><p class="caption">Where the final margin lands across 20,000 simulations. The darker band holds the middle half of outcomes; the lighter band holds 90%.</p>`);
  display(marginRange(det.quantiles, {width: Math.min(width, 900)}));
}
```

```js
if (!fixed) {
  const start = r.pres24;
  const shift = top.nat_median - top.nat_pres24;
  const other = r.fundamentals_mean - (start + shift);
  const sp = (det.polls ?? []).filter((p) => p.partisan);
  const sponsorNote = sp.length ? `After correcting ${sp.length} campaign- or party-sponsored poll${sp.length === 1 ? "" : "s"} for ${sp.length === 1 ? "its" : "their"} sponsor's usual lean (see Polls below).` : "";
  const hasPolls = r.poll_count > 0 && r.poll_avg != null && r.poll_weight > 0;
  const row = (label, value, why, cls = "") => html`<div class="row ${cls}"><div>${label}</div><div class="v">${value}</div><div></div>${why ? html`<div class="why">${why}</div>` : ""}</div>`;
  const usd = (v) => (v >= 1e6 ? `$${(v / 1e6).toFixed(1)} million` : `$${Math.round(v / 1000).toLocaleString()},000`);
  const moneyNote = r.dem_money != null && r.rep_money != null
    ? ` Campaign money so far (cash on hand plus spending this year, from FEC reports): ${dName} ${usd(r.dem_money)}, ${rName} ${usd(r.rep_money)}${Math.abs(r.money_adj ?? 0) >= 0.5 ? `, worth about ${Math.abs(r.money_adj).toFixed(1)} points to ${r.money_adj > 0 ? dName : rName} in a race this close` : ""}.`
    : "";
  const inc = r.inc_side === 1 ? `${dName} is the incumbent` : r.inc_side === -1 ? `${rName} is the incumbent` : "No incumbent on the ballot";
  display(html`<h2>What's driving the forecast</h2>
  <div class="factor-list">
    ${row(r.office === "HOUSE" ? "2024 presidential result in this district" : "2024 presidential result in this state", margin(start), r.office === "HOUSE" && r.lines_changed ? "Recalculated for the district's new 2026 lines." : "")}
    ${row("National environment shift", `${shift >= 0 ? "+" : "–"}${Math.abs(shift).toFixed(1)}`, `The nation is expected to move from ${margin(top.nat_pres24)} in 2024 to about ${margin(top.nat_median)} in the House vote.`)}
    ${row("Incumbency, candidates, money and local factors", `${other >= 0 ? "D +" : "R +"}${Math.abs(other).toFixed(1)}`, `${inc}.${moneyNote}${r.prior_edge != null ? ` Last time, the incumbent ran ${Math.abs(r.prior_edge).toFixed(0)} points ${r.prior_edge >= 0 ? "ahead of" : "behind"} expectations; part of that carries forward.` : ""}${r.quality_diff && Math.abs(r.quality_adj ?? 0) >= 0.3 ? ` Candidate experience edge: ${r.quality_diff > 0 ? dName : rName}.` : ""}${r.office === "HOUSE" && Math.abs(start - top.nat_pres24) < 15 ? " Includes the close-seat effect found in past elections." : ""}`)}
    ${row("Fundamentals estimate", margin(r.fundamentals_mean), "", "total")}
    ${hasPolls ? row(`Poll average (${r.poll_count} poll${r.poll_count === 1 ? "" : "s"})`, margin(r.poll_avg), `${sponsorNote ? `${sponsorNote} ` : ""}Polls get ${Math.round(r.poll_weight * 100)}% of the weight here, based on how many there are and how accurate race polling has been at this point in past elections.`) : row("Polls", "None", "No public polls, so this forecast rests on fundamentals.")}
    ${row("Final forecast (median)", margin(r.margin_median), "", "total")}
  </div>`);
}
```

```js
const polls = det.polls ?? [];
if (polls.length) {
  const sp = polls.filter((p) => p.partisan);
  const bySide = {D: sp.filter((p) => p.partisan === "D").length, R: sp.filter((p) => p.partisan === "R").length};
  const shift = sp.length ? Math.abs(sp[0].margin - sp[0].adj) : 0;
  const sideText = [bySide.D ? `${bySide.D} ${bySide.D === 1 ? "was" : "were"} paid for by Democrats` : "", bySide.R ? `${bySide.R} by Republicans` : ""].filter(Boolean).join(" and ");
  display(html`<h2>Polls</h2><p class="caption">Two-party margin of each general-election poll. The line is our polling average: each poll's weight halves every 14 days, and it turns blue or red with whoever leads.</p>`);
  if (sp.length) display(html`<div class="callout"><b>Why our average can differ from the polls you see.</b> ${sp.length === polls.length ? `${polls.length === 1 ? "The only poll here was" : `All ${polls.length} polls here were`} paid for by ${bySide.D && bySide.R ? "the campaigns or parties" : bySide.D ? "Democrats" : "Republicans"}.` : `Of these ${polls.length} polls, ${sideText}.`} Polls released by a campaign or party have historically made their side look about ${shift.toFixed(0)} points better than the result, so we shift each one by that much before counting it, and count it at half weight. On the chart, the hollow diamond is the poll as published and the solid dot is how we count it.</div>`);
  display(pollChart(polls, {width: Math.min(width, 1000), dLabel: dTag}));
  const tbl = html`<div class="table-wrap"><table class="wsu-table"><thead><tr>
    <th>Pollster</th><th>Dates</th><th class="num hide-sm">Sample</th><th class="num">${dName}</th><th class="num">${rName}</th><th class="num">Margin</th><th class="hide-sm">Source</th></tr></thead>
    <tbody>${polls.slice(0, 60).map((p) => html`<tr>
      <td>${p.pollster}${p.partisan ? html` <span class="rating-pill" style="background:${t.hair};color:${t.ink}">${p.partisan}-sponsored</span>` : ""}</td>
      <td>${p.start && p.start !== p.end ? `${date(p.start).replace(/, \d{4}/, "")}–` : ""}${date(p.end)}</td>
      <td class="num hide-sm">${p.n ? `${Math.round(p.n).toLocaleString()} ${String(p.pop ?? "").toUpperCase()}` : "–"}</td>
      <td class="num">${p.d}%</td><td class="num">${p.r}%</td>
      <td class="num">${margin(p.margin).replace("D+", `${dTag}+`)}${p.partisan ? html`<div class="adj">counted as ${margin(p.adj).replace("D+", `${dTag}+`)}</div>` : ""}</td>
      <td class="hide-sm">${p.url ? html`<a href="${p.url}" target="_blank" rel="noopener">${p.url.includes("wikipedia.org") ? "List" : "Source"}</a>` : ""}</td>
    </tr>`)}</tbody></table></div>`;
  display(tbl);
  if (polls.length > 60) display(html`<p class="caption">Showing the 60 most recent of ${polls.length} polls.</p>`);
}
```

```js
if ((det.past ?? []).length) {
  display(html`<h2>Past results</h2><p class="caption">${r.office === "HOUSE" ? "Presidential margins within this district's current lines." : "Statewide results since 2000, two-party margin."}</p>`);
  display(pastResults(det.past, {width: Math.min(width, 800)}));
}
```

```js
if ((det.history ?? []).length >= 2 && !fixed) {
  display(html`<h2>How this forecast has changed</h2>`);
  display(probHistory(det.history, {width: Math.min(width, 900), label: `Chance ${dName} wins`}));
}
```

```js
const inState = races.filter((x) => x.state_po === r.state_po && x.race_id !== r.race_id);
const officeOrder = {GOV: 0, SEN: 1, HOUSE: 2};
const others = [
  ...inState.filter((x) => x.office !== "HOUSE").sort((a, b) => officeOrder[a.office] - officeOrder[b.office] || a.special - b.special),
  ...inState.filter((x) => x.office === "HOUSE" && x.race_type !== "same_party")
    .sort((a, b) => Math.abs(a.p_dem - 0.5) - Math.abs(b.p_dem - 0.5)).slice(0, 6)
];
if (others.length) {
  display(html`<h2>Other ${r.state_name} races</h2><p class="caption">Statewide races first, then the state's most competitive House districts.</p>
    <div class="table-wrap"><table class="wsu-table"><tbody>${others.map((x) => html`<tr><td>${raceLink(x, x.office === "HOUSE" ? `House: ${x.label}` : `${{SEN: "Senate", GOV: "Governor"}[x.office]}${x.special ? " (special)" : ""}`)}</td><td class="num">${favoriteText(x)}</td><td>${ratingPill(x.rating)}</td></tr>`)}</tbody></table></div>`);
}
```
