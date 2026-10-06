---
title: Race forecast
---

```js
import {tokens, pct, pctPair, margin, date, probBar, ratingPill, favoriteText, raceLink, link, sides, shareBar, tpPct, powerText, raceTable} from "../components/wsu.js";
import {marginRange, pollChart, probHistory, pastResults} from "../components/charts.js";
const races = FileAttachment("../data/races.json").json();
const details = FileAttachment("../data/race_detail.json").json();
const top = FileAttachment("../data/topline.json").json();
const markets = FileAttachment("../data/markets.json").json();
const liveModel = FileAttachment("../data/live_model.json").json();
const finePrint = FileAttachment("../data/fine_print.json").json();
const benchFile = FileAttachment("../data/benchmarks.json");
import {raceLive, votesLeft, countyKey} from "../components/live.js";
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
const {d: dName, r: rName, dTag, rTag} = sides(r);
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
    <div class="race-cand right"><div class="name"><span class="party-chip ${rTag === "I" ? "i" : "r"}">${rTag}</span> ${rName}</div>
      <div class="pct" style="color:${rTag === "I" ? t.ind : t.rep}">${pctPair(pD)[1]}</div>
      <div class="role">${r.inc_side === -1 ? "Incumbent" : ""}</div></div>
  </div>`);
  display(probBar(pD, {dLabel: dName, rLabel: rName, dColor: dTag === "I" ? t.ind : t.dem, rColor: rTag === "I" ? t.ind : t.rep}));
  display(html`<p class="dek" style="margin-top:18px">${lead ? dName : rName} wins in ${pct(Math.max(pD, 1 - pD))} of our simulations, ${oddsText(Math.max(pD, 1 - pD))}. The most likely result is ${margin(r.margin_median).replace("D+", `${dTag}+`)}. ${ratingSentence(r)}</p>`);
  if (r.tipping_point != null && (r.office === "SEN" || r.office === "HOUSE")) {
    const chamber = r.office === "SEN" ? "Senate" : "House";
    const peers = races.filter((x) => x.office === r.office && x.tipping_point != null);
    const rank = 1 + peers.filter((x) => x.tipping_point > r.tipping_point).length;
    const more = html`<a href="${link(r.office === "SEN" ? "senate#the-tipping-point" : "house#the-tipping-point")}">How this works</a>`;
    display(r.tipping_point >= 0.005
      ? html`<p class="caption"><b>Tipping point:</b> in ${tpPct(r.tipping_point)} of simulations, this is the race that hands a party control of the ${chamber}, the ${rank === 1 ? "" : `${ordinal(rank)} `}likeliest of ${peers.length}. A vote here is ${powerText(r.voter_power)} the average ${chamber} vote to decide control. ${more}.</p>`
      : html`<p class="caption"><b>Tipping point:</b> this race decides control of the ${chamber} in fewer than 1 in 200 simulations. ${more}.</p>`);
  }
  // the margin in people: our most likely result as a number of votes, next to the people who could change it
  if (r.expected_votes) {
    const people = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)} million` : n >= 1e4 ? `${Math.round(n / 1000).toLocaleString()},000` : (Math.round(n / 100) * 100).toLocaleString());
    const mv = (Math.abs(r.margin_median) / 100) * r.expected_votes;
    const lead = r.margin_median >= 0 ? dName : rName;
    const stay = r.eligible && r.votes22 ? r.eligible - r.votes22 : null;
    const ratio = stay && mv >= 0.0025 * r.expected_votes ? stay / mv : null;  // no ratio for a near tie
    display(html`<p class="caption"><b>In people:</b> ${mv < 0.0025 * r.expected_votes
      ? `our most likely result is close to a tie among roughly ${people(r.expected_votes)} votes we expect cast.`
      : `our most likely result is ${lead} by about ${people(mv)} votes, out of roughly ${people(r.expected_votes)} we expect cast.`}
      ${stay ? `About ${people(stay)} eligible ${r.state_name} adults didn't vote in 2022${ratio && ratio >= 2 ? `, more than ${ratio >= 10 ? Math.floor(ratio).toLocaleString() : ratio.toFixed(0)} times that margin` : ""}.` : ""}
      Expected turnout is a rough guide: midterm turnout has swung by a quarter from one cycle to the next.</p>`);
  }
  const mk = markets.races[id];
  if (mk) {
    const mLead = mk.p >= 0.5;
    display(html`<p class="caption">For comparison, traders on <a href="${mk.url}">PredictIt</a> give ${mLead ? dName : rName} a ${pct(Math.max(mk.p, 1 - mk.p))} chance (as of ${date(markets.asof)}). Market prices are shown for reference only and play no part in our forecast. <a href="${link("compare#prediction-markets")}">More on markets</a>.</p>`);
  }
}
// a suggested post for the share buttons, in plain words
const goal = r.office === "HOUSE" ? `to win ${place}` : r.office === "SEN" ? `to win ${r.state_name}'s Senate ${r.special ? "special election" : "race"}` : `to win ${r.state_name}'s race for governor`;
const favP = Math.max(r.p_dem, 1 - r.p_dem), favName = r.p_dem >= 0.5 ? dName : rName;
const an = /^(8|11|18)/.test(pct(favP)) ? "an" : "a";
display(shareBar({path: `/race/${id}`, text: fixed
  ? `Only ${r.race_note === "D" ? "Democrats" : "Republicans"} are on the ballot in ${heading}, so the seat is certain to stay ${r.race_note === "D" ? "Democratic" : "Republican"}. From the Who Shows Up 2026 forecast:`
  : `The Who Shows Up 2026 forecast gives ${favName} ${an} ${pct(favP)} chance ${goal}.`}));
function oddsText(p) { return p >= 0.95 ? "a strong favorite" : p >= 0.8 ? "a clear favorite" : p >= 0.6 ? "a modest favorite" : "close to a coin flip"; }
function ratingSentence(r) { return `We rate it <b>${r.rating}</b>.`.replace(/<\/?b>/g, ""); }
```

```js
// Election night: this race's count straight from civicAPI (components/live.js), once a minute while the page is
// visible; ?direct in the address turns it on early, for testing
const night = fixed ? null : raceLive(r, liveModel.civic[id], {Generators, force: new URLSearchParams(location.search).has("direct")});
```

```js
if (night?.x) {
  const x = night.x, tot = x.d + x.r;
  const v = votesLeft(x);
  const k = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(2)} million` : n.toLocaleString());
  const who = (s) => (s === "D" ? dName : rName);
  display(html`<div class="callout live-box"><b>${x.called ? `${who(x.called)} wins` : tot ? "Counting" : "Election night"}</b>
    ${tot ? html` · ${x.pct}% counted<br>${dName} ${k(x.d)} (${((100 * x.d) / tot).toFixed(1)}%) · ${rName} ${k(x.r)} (${((100 * x.r) / tot).toFixed(1)}%)
      ${v && !x.called ? html`<br>${v.locked ? `${who(v.leader)}'s lead of ${k(v.lead)} is bigger than the roughly ${k(v.left)} votes left.` : `About ${k(v.left)} votes left; ${who(v.leader === "D" ? "R" : "D")} needs ${Math.round(v.need * 100)}% of them to catch up.`}` : ""}`
      : " · No votes counted yet."}
    <span class="muted"> Results from <a href="https://civicapi.org">civicAPI</a>, updated ${new Date(night.at).toLocaleTimeString("en-US", {timeZone: "America/New_York", hour: "numeric", minute: "2-digit"})} ET; calls are civicAPI's. "Votes left" is estimated from the share counted so far.</span></div>`);
}
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
  const undNote = (r.poll_undecided ?? 0) >= 0.08
    ? `About ${Math.round(r.poll_undecided * 100)}% of the people in these polls are undecided or backing someone else; the model expects them to split closer to evenly than the decided voters, and allows a wider range.` : "";
  const sponsorNote = sp.length ? `After correcting ${sp.length} campaign- or party-sponsored poll${sp.length === 1 ? "" : "s"} for ${sp.length === 1 ? "its" : "their"} sponsor's usual lean (see Polls below).` : "";
  const hasPolls = r.poll_count > 0 && r.poll_avg != null && r.poll_weight > 0;
  const row = (label, value, why, cls = "") => html`<div class="row ${cls}"><div>${label}</div><div class="v">${value}</div><div></div>${why ? html`<div class="why">${why}</div>` : ""}</div>`;
  const usd = (v) => (v >= 1e6 ? `$${(v / 1e6).toFixed(1)} million` : `$${Math.round(v / 1000).toLocaleString()},000`);
  const moneyNote = r.dem_money != null && r.rep_money != null
    ? ` Campaign money so far (cash on hand plus spending this year, from FEC reports): ${dName} ${usd(r.dem_money)}, ${rName} ${usd(r.rep_money)}${Math.abs(r.money_adj ?? 0) >= 0.5 ? `, worth about ${Math.abs(r.money_adj).toFixed(1)} points to ${r.money_adj > 0 ? dName : rName} in a race this close` : ""}.`
    : "";
  const inc = r.inc_side === 1 ? `${dName} is the incumbent` : r.inc_side === -1 ? `${rName} is the incumbent`
    : r.incumbent && [dName, rName].includes(r.incumbent) ? `${r.incumbent} is the incumbent` : "No incumbent on the ballot";
  display(html`<h2>What's driving the forecast</h2>
  <div class="factor-list">
    ${row(r.office === "HOUSE" ? "2024 presidential result in this district" : "2024 presidential result in this state", margin(start), r.office === "HOUSE" && r.lines_changed ? "Recalculated for the district's new 2026 lines." : "")}
    ${row("National environment shift", `${shift >= 0 ? "D +" : "R +"}${Math.abs(shift).toFixed(1)}`, `Our national estimate moves from ${margin(top.nat_pres24)} in 2024 to about ${margin(top.nat_median)} in the House vote.`)}
    ${row("Incumbency, candidates, money and local factors", `${other >= 0 ? "D +" : "R +"}${Math.abs(other).toFixed(1)}`, `${inc}.${moneyNote}${r.prior_edge != null ? ` Last time, the incumbent ran ${Math.abs(r.prior_edge).toFixed(0)} points ${r.prior_edge >= 0 ? "ahead of" : "behind"} expectations; part of that carries forward.` : ""}${r.quality_diff && Math.abs(r.quality_adj ?? 0) >= 0.3 ? ` Candidate experience edge: ${r.quality_diff > 0 ? dName : rName}.` : ""}${Math.abs(r.ideology_adj ?? 0) >= 0.5 ? ` Judged by their donors, ${r.ideology_adj > 0 ? dName : rName} is the more moderate of the two for their party, worth about ${Math.abs(r.ideology_adj).toFixed(1)} points in a race this close.` : ""}${r.office === "HOUSE" && Math.abs(start - top.nat_pres24) < 15 ? " Includes the close-seat effect found in past elections." : ""}`)}
    ${row("Fundamentals estimate", margin(r.fundamentals_mean), "", "total")}
    ${hasPolls ? row(`Poll average (${r.poll_count} poll${r.poll_count === 1 ? "" : "s"})`, margin(r.poll_avg), `${sponsorNote ? `${sponsorNote} ` : ""}${undNote ? `${undNote} ` : ""}Polls get ${Math.round(r.poll_weight * 100)}% of the weight here, based on how many there are and how accurate race polling has been at this point in past elections.`) : row("Polls", "None", "No public polls, so this forecast rests on fundamentals.")}
    ${row("Final forecast (median)", margin(r.margin_median), "", "total")}
  </div>`);
  if (hasPolls && r.p_fund != null && r.p_poll != null) {
    const ch = (p) => (p >= 0.5 ? `${pct(p)} ${dTag}` : `${pct(1 - p)} ${rTag}`);
    const agree = (r.p_fund >= 0.5) === (r.p_poll >= 0.5);
    display(html`<h3>Fundamentals alone, polls alone, and both</h3>
    <div class="stat-row">
      <div class="s"><div class="k">Fundamentals alone</div><div class="v">${ch(r.p_fund)}</div></div>
      <div class="s"><div class="k">Polls alone</div><div class="v">${ch(r.p_poll)}</div></div>
      <div class="s"><div class="k">Our forecast</div><div class="v">${ch(r.p_dem)}</div></div>
    </div>
    <p class="caption">${agree
      ? "The two reads point the same way here. Two independent reads that agree make the forecast more confident than either one alone, which is why ours can be higher than both."
      : `The two reads disagree here. Our forecast lands between them, closer to the polls the more of them there are and the more accurate polling of races like this has been (they get ${Math.round(r.poll_weight * 100)}% of the weight).`} The chances shown for each read include our uncertainty about the national environment.</p>`);
  }
}
```

```js
const polls = det.polls ?? [];
if (polls.length) {
  const sp = polls.filter((p) => p.partisan);
  const bySide = {D: sp.filter((p) => p.partisan === "D").length, R: sp.filter((p) => p.partisan === "R").length};
  const shift = sp.length ? Math.abs(sp[0].margin - sp[0].adj) : 0;
  const sideText = [bySide.D ? `${bySide.D} ${bySide.D === 1 ? "was" : "were"} paid for by Democrats` : "", bySide.R ? `${bySide.R} by Republicans` : ""].filter(Boolean).join(" and ");
  display(html`<h2>Polls</h2><p class="caption">Two-party margin of each general-election poll, as we count it after our corrections for who paid for it, the firm's track record and undecided voters (hover a poll for details; a hollow diamond marks a published number that differs by half a point or more). The line is our polling average, the same one the forecast uses: each poll's weight halves every 14 days, larger and likely-voter samples count more, and the line turns blue or red with whoever leads.</p>`);
  if (sp.length) display(html`<div class="callout"><b>Why our average can differ from the polls you see.</b> ${sp.length === polls.length ? `${polls.length === 1 ? "The only poll here was" : `All ${polls.length} polls here were`} paid for by ${bySide.D && bySide.R ? "the campaigns or parties" : bySide.D ? "Democrats" : "Republicans"}.` : `Of these ${polls.length} polls, ${sideText}.`} Polls released by a campaign or party have historically made their side look about ${shift.toFixed(0)} points better than the result, so we shift each one by that much before counting it, and count it at half weight. On the chart, a hollow diamond is a poll as published and the solid dot is how we count it.</div>`);
  display(pollChart(polls, {width: Math.min(width, 1000), dLabel: dTag}));
  const tbl = html`<div class="table-wrap"><table class="wsu-table"><thead><tr>
    <th>Pollster</th><th>Dates</th><th class="num hide-sm">Sample</th><th class="num">${dName}</th><th class="num">${rName}</th><th class="num">Margin</th><th class="hide-sm">Source</th></tr></thead>
    <tbody>${polls.slice(0, 60).map((p) => html`<tr>
      <td>${p.pollster}${p.partisan ? html` <span class="rating-pill" style="background:${t.hair};color:${t.ink}">${p.partisan}-sponsored</span>` : ""}</td>
      <td>${p.start && p.start !== p.end ? `${date(p.start).replace(/, \d{4}/, "")}–` : ""}${date(p.end)}</td>
      <td class="num hide-sm">${p.n ? `${Math.round(p.n).toLocaleString()} ${String(p.pop ?? "").toUpperCase()}` : "–"}</td>
      <td class="num">${p.d}%</td><td class="num">${p.r}%</td>
      <td class="num">${margin(p.margin).replace("D+", `${dTag}+`).replace("R+", `${rTag}+`)}${Math.abs(p.adj - p.margin) >= 0.5 ? html`<div class="adj">counted as ${margin(p.adj).replace("D+", `${dTag}+`).replace("R+", `${rTag}+`)}</div>` : ""}</td>
      <td class="hide-sm">${p.url ? html`<a href="${p.url}" target="_blank" rel="noopener">${p.url.includes("wikipedia.org") ? "List" : "Source"}</a>` : ""}</td>
    </tr>`)}</tbody></table></div>`;
  display(tbl);
  if (polls.length > 60) display(html`<p class="caption">Showing the 60 most recent of ${polls.length} polls.</p>`);
}
```

```js
// The poll fine print: details from inside the polls that The Turnout has reported (export_site_data.fine_print)
{
  const notes = finePrint.filter((x) => x.race === id);
  if (notes.length) {
    const groups = d3.groups(notes, (x) => x.group);
    display(html`<h2>Poll fine print</h2><p class="caption">Details from inside the polls, beyond the topline, as reported in <a href="https://theturnout.substack.com">The Turnout</a>, our weekly newsletter. Newest first.</p>
    <div class="fine-print">${groups.map(([g, list]) => html`<h3>${g}</h3><ul class="tight">${list.map((x) => html`<li><b>${x.measure}:</b> ${x.value} <span class="muted">(${x.link ? html`<a href="${x.link}">${x.poll}</a>` : x.poll})</span></li>`)}</ul>`)}</div>`);
  }
}
```

```js
// County benchmarks (Senate and governor races): what each county would show if the race landed exactly on our
// most likely margin (export_site_data.benchmarks); on election night, each county's count next to it
const bench = !fixed && r.office !== "HOUSE" && r.state_po !== "AK" ? (await benchFile.json())[id] ?? null : null;
```

```js
if (bench) {
  const L = night?.counties;
  const tag = (m) => (m >= 0 ? dTag : rTag);
  const fm = (m) => (Math.abs(m) < 0.05 ? "Even" : `${tag(m)}+${Math.abs(m).toFixed(1)}`);
  const rows = bench.map(([name, fips, b, p24, share]) => {
    const c = L?.get(countyKey(name));
    const tot = c ? c.d + c.r : 0;
    const now = tot ? (100 * (c.d - c.r)) / tot : null;
    return {name, b, p24, share, c, now, gap: now == null ? null : now - b, _search: name.toLowerCase()};
  });
  const unit = r.state_po === "LA" ? "parish" : "county";
  display(html`<h2>County benchmarks</h2><p class="caption">What each ${unit} would show if the race landed exactly on our most likely result, ${fm(r.margin_median)} statewide: each starts from its 2024 presidential result and moves the way our forecast moves races (mostly through who turns out). ${L ? `On election night, compare the count so far with the benchmark: a candidate running ahead of the benchmark in most places is outrunning our forecast. Early counts can mislead, since mail and Election Day ballots are often counted at different times.` : "On election night, each one's count so far appears next to it."}</p>`);
  const cols = [
    {key: "name", label: unit === "parish" ? "Parish" : "County", sort: true},
    {key: "share", label: "Share of the vote", num: true, sort: true, defaultDir: -1, render: (x) => `${(x.share * 100).toFixed(x.share < 0.01 ? 1 : 0)}%`},
    {key: "p24", label: "2024 president", num: true, sort: true, render: (x) => fm(x.p24)},
    {key: "b", label: "Benchmark", num: true, sort: true, render: (x) => fm(x.b)}
  ];
  if (L) cols.push(
    {key: "now", label: "Count so far", num: true, sort: true, render: (x) => (x.now == null ? "–" : `${fm(x.now)} (${x.c.pct}%)`)},
    {key: "gap", label: "vs. benchmark", num: true, sort: true, render: (x) => (x.gap == null ? "" : `${x.gap >= 0 ? dTag : rTag} ${Math.abs(x.gap).toFixed(1)} ahead`)});
  display(raceTable(rows, cols, {search: rows.length > 15, placeholder: `Search ${unit === "parish" ? "parishes" : "counties"}`, noun: unit === "parish" ? "parish" : "county", pageSize: 15, sort: {key: "share", dir: -1}}));
}
```

```js
if ((det.past ?? []).length) {
  display(html`<h2>Past results</h2><p class="caption">${r.office === "HOUSE" ? "Presidential margins within this district's current lines." : "Statewide results since 2000, two-party margin."}</p>`);
  display(pastResults(det.past, {width: Math.min(width, 800)}));
  if (r.office !== "HOUSE" && r.state_po !== "AK") display(html`<p><a href="${link(`past-results?state=${r.state_po}`)}">See how each ${r.state_po === "LA" ? "parish" : "county"} in ${r.state_name} voted →</a></p>`);
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
