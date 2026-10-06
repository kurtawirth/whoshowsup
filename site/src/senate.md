---
title: Senate forecast
---

```js
import {tokens, pct, margin, date, stateMap, ratingLegend, ratingPill, raceTable, raceLink, miniBar, favoriteText, withSearch, RATINGS, RACE_SORTS, raceHref, tip, shareBar, tippingTable, tpPct, powerText} from "./components/wsu.js";
import {seatChart} from "./components/charts.js";
const top = FileAttachment("data/topline.json").json();
const seats = FileAttachment("data/seats.json").json();
const races = FileAttachment("data/races.json").json();
const topo = FileAttachment("data/states-albers-10m.json").json();
const states = FileAttachment("data/states.json").json();
```

```js
const t = (dark, tokens());
const sen = races.filter((r) => r.office === "SEN");
const q = Math.max(top.p_senate_d, 1 - top.p_senate_d);
const lead = top.p_senate_d >= 0.5 ? "Democrats" : "Republicans";
const headline = q < 0.55 ? "The Senate is a toss-up" : `${lead} ${q >= 0.8 ? "are favored" : "have a slight edge"} in the race for the Senate`;
```

<p class="kicker">Senate · Updated ${date(top.forecast_date)}</p>

# ${headline}

<p class="dek">Democrats win a majority in ${pct(top.p_senate_d)} of our simulations. Republicans hold 53 seats today and Democrats 47 (including two independents who caucus with them). Of the 35 seats on the ballot, Republicans are defending 22, so Democrats need a net gain of four. The vice president breaks ties.</p>

```js
{
const side = (p) => (p >= 0.5 ? ["Democrats", p] : ["Republicans", 1 - p]);
const [sp, sv] = side(top.p_senate_d);
display(shareBar({path: "/senate", text: `The Who Shows Up 2026 Senate forecast: ${sp} win the Senate in ${pct(sv)} of our simulations.`}));
}
```

## The map

```js
display(ratingLegend({independent: true, noRace: "No Senate race in 2026"}));
display(stateMap(races, topo, states, {office: "SEN", width: Math.min(width, 1000)}));
```

<p class="caption">Florida and Ohio hold special elections to fill the rest of Marco Rubio's and JD Vance's terms. Nebraska's race pits Republican Pete Ricketts against independent Dan Osborn, with no Democrat on the ballot. On a phone, pinch or tap + to zoom in, then tap a state to preview it.</p>

## The path to 51

<p class="caption">All 100 seats after the election, lined up from most Democratic to most Republican. The 65 seats not on the ballot are shown faded; the 35 races are ordered by the chance Democrats (or Osborn) win and colored by our rating. Democrats need the 51st.</p>

```js
function pathTo51(w) {
  // One row of 100 seats on wide screens (two on phones): most Democratic on the left.
  const sorted = [...sen].sort((a, b) => b.p_dem - a.p_dem);
  const seatsArr = [
    ...d3.range(34).map(() => ({kind: "D", label: "Democratic seat not up in 2026"})),
    ...sorted.map((r) => ({kind: "race", r})),
    ...d3.range(31).map(() => ({kind: "R", label: "Republican seat not up in 2026"}))
  ];
  const cols = w < 700 ? 50 : 100, gap = 2;
  const cw = (w - gap * (cols - 1)) / cols, ch = cols === 100 ? 44 : 30;
  const rows = 100 / cols, top = 30;
  const H = top + rows * (ch + gap) + 22;
  const svg = d3.create("svg").attr("width", w).attr("height", H).attr("viewBox", [0, 0, w, H]);
  const tp = tip();
  seatsArr.forEach((s, i) => {
    const x = (i % cols) * (cw + gap), y = top + Math.floor(i / cols) * (ch + gap);
    const fill = s.kind === "D" ? t["party-d"] : s.kind === "R" ? t["party-r"] : s.r.race_type === "independent" ? t.ind : t[s.r.rating];
    const parent = s.kind === "race" ? svg.append("a").attr("href", raceHref(s.r.race_id)) : svg;
    parent.append("rect").attr("x", x).attr("y", y).attr("width", cw).attr("height", ch).attr("rx", 2).attr("fill", fill)
      .attr("fill-opacity", s.kind === "race" ? 1 : 0.3)
      .on("pointerenter", (e) => tp.show(e, s.kind === "race"
        ? [["t-title", `Seat ${i + 1}: ${s.r.label}`], ["t-val", favoriteText(s.r)], ["t-sub", s.r.rating]]
        : [["t-title", `Seat ${i + 1}`], ["t-sub", s.label]]))
      .on("pointermove", (e) => tp.move(e)).on("pointerleave", () => tp.hide());
    if (i === 50) {
      svg.append("line").attr("x1", x + cw / 2).attr("x2", x + cw / 2).attr("y1", top - 8).attr("y2", y + ch + 4)
        .attr("stroke", t.ink).attr("stroke-width", 1.5);
      svg.append("text").attr("x", Math.min(Math.max(x + cw / 2, 40), w - 40)).attr("y", top - 14).attr("text-anchor", "middle")
        .attr("font-size", 12).attr("font-weight", 700).attr("fill", t.ink).text("51st seat");
    }
  });
  svg.append("text").attr("x", 0).attr("y", H - 4).attr("font-size", 12).attr("fill", t["ink-3"]).text("← Most Democratic");
  svg.append("text").attr("x", w).attr("y", H - 4).attr("text-anchor", "end").attr("font-size", 12).attr("fill", t["ink-3"]).text("Most Republican →");
  return svg.node();
}
display(pathTo51(width));
```

```js
const tipping = [...sen].sort((a, b) => b.p_dem - a.p_dem)[50 - 34];
const who = tipping.race_type === "independent" ? "Osborn" : "Democrats";
display(html`<p>The 51st seat, the one that decides control if every race breaks in order, is currently <strong>${tipping.label}</strong>. ${tipping.p_dem >= 0.5 ? `${who} win it in ${pct(tipping.p_dem)}` : `Republicans win it in ${pct(1 - tipping.p_dem)}`} of simulations.</p>`);
```

## The tipping point

<p class="caption">Races don't break in order, so we also ask each of the 20,000 simulations: lining up the seats the winning party took from its safest to its closest, which one got it to a majority (51 for Democrats; 50 for Republicans, with Vance's tiebreak)? A race's tipping-point chance is how often it was that seat. "Vote's sway" divides that chance by the votes we expect in the race, so a 3× state is one where a vote is three times as likely to decide control as the average vote cast in this year's Senate races.</p>

```js
{
  const ranked = sen.filter((r) => r.tipping_point > 0).sort((a, b) => b.tipping_point - a.tipping_point);
  const [first, second] = ranked;
  const sway = sen.filter((r) => r.tipping_point >= 0.01).sort((a, b) => b.voter_power - a.voter_power)[0];
  const gap = top.senate_tp_gap;
  const noMaj = top.p_senate_no_majority ?? 0;
  display(html`<p>The likeliest tipping point is <strong>${raceLink(first)}</strong> (${tpPct(first.tipping_point)} of simulations), followed by ${raceLink(second)} (${tpPct(second.tipping_point)}). In the typical simulation the tipping-point state runs about ${Math.abs(gap).toFixed(0)} points ${gap < 0 ? "more Republican" : "more Democratic"} than the national House vote, so a national ${margin(top.nat_median)} is closer to ${margin(top.nat_median + gap)} where control is decided. A vote counts most in ${raceLink(sway, sway.state_name)}, where it is ${powerText(sway.voter_power)} the average Senate vote to decide control.</p>
  ${noMaj >= 0.005 ? html`<p class="caption">In ${pct(noMaj)} of simulations, an Osborn win leaves neither party with a majority, and control turns on Nebraska's result and whom Osborn sides with. Nebraska counts as the tipping point in those simulations.</p>` : ""}`);
  display(tippingTable(sen));
}
```

## How the Senate could split

<p class="caption">Each bar is one possible split of the 100 seats; the percentage is how often it came up in 20,000 simulations. It takes 51 seats to control the Senate, and at 50–50 Vice President Vance breaks ties for Republicans.</p>

```js
display(seatChart(seats.senate, 51, {width, label: "Senate", total: 100, height: 250, pControl: top.p_senate_d}));
```

## Every Senate race

```js
const columns = [
  {key: "label", label: "State", sort: true, render: (r) => raceLink(r)},
  {key: "dem_candidate", label: "Democrat", render: (r) => r.race_type === "independent" ? `${r.race_note} (I)` : r.dem_name ?? "–"},
  {key: "rep_candidate", label: "Republican", render: (r) => r.rep_name ?? "–"},
  {key: "incumbent", label: "Incumbent", render: (r) => `${r.incumbent} (${r.incumbent_party})`},
  {key: "poll_count", label: "Polls", num: true, sort: true, defaultDir: -1, render: (r) => r.poll_count ?? 0},
  {key: "margin_median", label: "Forecast margin", num: true, sort: true, render: (r) => margin(r.margin_median)},
  {key: "p_dem", label: "Chance", num: true, sort: true, defaultDir: -1, render: (r) => favoriteText(r)},
  {key: "bar", label: "", render: (r) => miniBar(r.p_dem)},
  {key: "rating", label: "Rating", sort: true, sortValue: (r) => RATINGS.indexOf(r.rating), render: (r) => ratingPill(r.rating)}
];
display(raceTable(withSearch(sen), columns, {sorts: RACE_SORTS, pageSize: 40}));
```
