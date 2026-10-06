---
title: Download the data
---

```js
import {date} from "./components/wsu.js";
const info = FileAttachment("data/downloads.json").json();
const files = [
  [FileAttachment("data/downloads/races.csv"), "races.csv", "Today's forecast for every race: each side's chance, the expected margin and its 80% range, our rating, the fundamentals-only and polls-only reads, the poll average and its weight, and each race's tipping-point chance and vote's sway."],
  [FileAttachment("data/downloads/race_history.csv"), "race_history.csv", "Every race's Democratic chance and expected margin on every day we've published a forecast."],
  [FileAttachment("data/downloads/topline_history.csv"), "topline_history.csv", "The headline numbers over time: national House vote, chance of controlling each chamber, and seat ranges."],
  [FileAttachment("data/downloads/poll_miss_scenarios.csv"), "poll_miss_scenarios.csv", "The forecast rerun as if this year's polls miss the way each year's did, 2012–2024 (see What if)."],
  [FileAttachment("data/downloads/pollster_adjustments.csv"), "pollster_adjustments.csv", "Every firm with a 2026 race poll: its poll count, track record, our correction and its sponsored polls (see Polls)."]
];
```

# Download the data

<p class="dek">Our forecast's numbers, as CSV files you can open in any spreadsheet. They update every morning with the forecast.</p>

```js
display(html`<div class="downloads">${files.map(([f, name, what]) => html`<div class="dl">
  <a class="dl-name" href="${f.href}" download="${name}">${name}</a>
  <span class="dl-rows">${(info.rows[name] ?? 0).toLocaleString()} rows</span>
  <p>${what}</p></div>`)}</div>
  <p class="caption">Files as of ${date(info.date)}. Margins are Democratic minus Republican, in points of the two-party vote; chances run from 0 to 1. In Nebraska's Senate race and Alaska's House race, the Democratic side is the independent (Osborn, Hill).</p>`);
```

## Using these numbers

You're welcome to use, chart and share these files. Please credit **Who Shows Up** and link to [whoshowsup.net](https://whoshowsup.net).

Raw poll data isn't included here: the polls come from [VoteHub](https://votehub.com), [Decision Desk HQ](https://votes.decisiondeskhq.com/polls) and Wikipedia, each under its own terms. Every poll we use is listed on the [Polls](./polls) page with a link to its source. The code behind the forecast is on [GitHub](https://github.com/kurtawirth/whoshowsup).
