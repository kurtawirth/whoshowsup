---
title: Polls
---

```js
import {pct, margin, date, raceTable, raceLink, sides, withSearch} from "./components/wsu.js";
const races = FileAttachment("data/races.json").json();
const details = FileAttachment("data/race_detail.json").json();
const firms = FileAttachment("data/pollsters.json").json();
const top = FileAttachment("data/topline.json").json();
```

# Every poll we use, and how we count it

<p class="dek">Our forecast reads every public general-election poll of a 2026 Senate, governor or House race we can find. Before averaging them, it makes three corrections, all learned from how past polls compared with results.</p>

<div class="callout">
<b>1. Who paid for it.</b> A poll released by a campaign or party has historically made its side look 3 to 6 points better than the result (more in House races). We shift those polls back by that much and count them at half weight.<br>
<b>2. The firm's track record.</b> Some firms' polls have leaned toward one party over many elections. We shift each firm's polls by its past lean relative to other firms, shrunk toward zero for firms with few past polls.<br>
<b>3. Undecided voters.</b> When many voters are undecided, the model allows for them breaking unevenly, based on how undecideds have broken in past races.
</div>

## How we adjust each pollster

<p class="caption">Every firm with a 2026 race poll. "Our correction" is how far we move each of its polls; it comes from the firm's record in past elections, so a firm without a record gets none. "Sponsored" counts polls paid for by a campaign or party, which are also shifted and half-weighted (correction 1 above). Generic-ballot polls are on the <a href="./national#the-generic-ballot">national page</a>.</p>

```js
{
  const corr = (c) => (Math.abs(c) < 0.25 ? "none" : `${c > 0 ? "toward D" : "toward R"} ${Math.abs(c).toFixed(1)}`);
  const rows = firms.map((f) => ({...f, _search: `${f.name} ${f.firm}`.toLowerCase()}));
  display(raceTable(rows, [
    {key: "name", label: "Pollster", sort: true},
    {key: "polls", label: "2026 polls", num: true, sort: true, defaultDir: -1},
    {key: "races", label: "Races", num: true, sort: true, defaultDir: -1},
    {key: "record", label: "Past polls on record", num: true, sort: true, defaultDir: -1, render: (f) => (f.record ? f.record.toLocaleString() : "none")},
    {key: "correction", label: "Our correction", num: true, sort: true, sortValue: (f) => f.correction, render: (f) => corr(f.correction)},
    {key: "partisan", label: "Sponsored", num: true, sort: true, defaultDir: -1, render: (f) => (f.partisan ? `${f.partisan} of ${f.polls}` : "–")}
  ], {placeholder: "Search pollsters", noun: "pollster", pageSize: 25, sort: {key: "polls", dir: -1}}));
}
```

## Every 2026 race poll

<p class="caption">Newest first. The margin is between the two major candidates, with undecided and other respondents set aside (Osborn counts on the Democratic side in Nebraska). Click a race to see its polls charted against our average.</p>

```js
{
  const byId = new Map(races.map((r) => [r.race_id, r]));
  const rows = [];
  for (const [id, d] of Object.entries(details)) {
    const r = byId.get(id);
    if (!r || !d.polls) continue;
    const s = sides(r);
    for (const p of d.polls) rows.push({...p, race_id: id, label: r.label, office: r.office, race: r, dTag: s.dTag,
      _search: `${r.label} ${r.state_name} ${p.pollster} ${p.sponsors ?? ""} ${s.d} ${s.r}`.toLowerCase()});
  }
  rows.sort((a, b) => d3.descending(a.end, b.end));
  const officeName = {SEN: "Senate", GOV: "Governor", HOUSE: "House"};
  const popName = {lv: "Likely voters", rv: "Registered voters", a: "Adults", v: "Voters"};
  display(raceTable(rows, [
    {key: "end", label: "Ended", sort: true, defaultDir: -1, render: (p) => date(p.end).replace(", 2026", "")},
    {key: "label", label: "Race", sort: true, render: (p) => raceLink(p.race, `${p.label}${p.office === "GOV" ? " (gov.)" : p.office === "SEN" && !p.race.special ? " (Sen.)" : ""}`)},
    {key: "pollster", label: "Pollster", sort: true, render: (p) => {
      const a = document.createElement(p.url ? "a" : "span");
      if (p.url) { a.href = p.url; a.rel = "nofollow noopener"; a.target = "_blank"; }
      a.textContent = p.pollster + (p.partisan ? ` (${p.partisan}-sponsored)` : "");
      return a;
    }},
    {key: "pop", label: "Sample", render: (p) => `${p.n ? Math.round(p.n).toLocaleString() : "?"} ${p.pop ? p.pop.toUpperCase() : ""}`.trim()},
    {key: "d", label: "D", num: true, render: (p) => (p.d != null ? `${Math.round(p.d)}` : "–")},
    {key: "r", label: "R", num: true, render: (p) => (p.r != null ? `${Math.round(p.r)}` : "–")},
    {key: "margin", label: "Margin", num: true, sort: true, render: (p) => margin(p.margin).replace("D+", `${p.dTag}+`)}
  ], {placeholder: "Search races, pollsters, candidates", noun: "poll", pageSize: 50, sort: {key: "end", dir: -1},
      filters: [{key: "office", label: "All offices", options: [["SEN", "Senate"], ["GOV", "Governor"], ["HOUSE", "House"]], test: (p, v) => p.office === v}]}));
}
```

<p class="caption">Poll data from <a href="https://votehub.com">VoteHub</a> (CC BY 4.0), <a href="https://votes.decisiondeskhq.com/polls">Decision Desk HQ</a> and Wikipedia. Links go to each poll's release where the source provides one.</p>
