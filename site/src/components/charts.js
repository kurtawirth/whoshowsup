// Who Shows Up -- shared charts (Observable Plot). Thin marks, hairline axes,
// selective labels, a hover tip on every chart.
import * as Plot from "npm:@observablehq/plot";
import {tokens, pct, margin, date} from "./wsu.js";

const base = (t) => ({background: "transparent", color: t["ink-3"], fontSize: "12px", fontFamily: "var(--sans)"});

/** Seat-count distribution with the control threshold marked. */
export function seatChart(dist, need, {width, label, height = 230}) {
  const t = tokens();
  const shown = dist.filter((d) => d.p > 0.0004);
  return Plot.plot({
    width, height, marginLeft: 8, marginRight: 8, marginBottom: 36, marginTop: 22,
    x: {label: `${label} seats won by Democrats`, labelAnchor: "center", labelOffset: 32, tickFormat: "d", nice: false},
    y: {axis: null},
    style: base(t),
    marks: [
      Plot.rectY(shown, {x1: (d) => d.seats - 0.42, x2: (d) => d.seats + 0.42, y: "p",
        fill: (d) => (d.seats >= need ? t.dem : t.rep), rx: 2}),
      Plot.ruleX([need - 0.5], {stroke: t.ink, strokeWidth: 1}),
      Plot.text([need - 0.5], {x: (d) => d, frameAnchor: "top", dy: -14, textAnchor: "middle",
        text: () => `${need} for control`, fill: t["ink-2"], fontSize: 12, fontWeight: 600}),
      Plot.ruleY([0], {stroke: t.axis}),
      Plot.tip(shown, Plot.pointerX({x: "seats", y: "p",
        title: (d) => `${d.seats} Democratic seats\n${(d.p * 100).toFixed(1)}% of simulations`}))
    ]
  });
}

/** A race's forecast margin as nested ranges (50% and 90%) with the median marked. */
export function marginRange(q, {width, height = 110, actual = null}) {
  // q = margin at the 5th, 10th, ..., 95th percentiles (19 values)
  const t = tokens();
  const at = (p) => q[Math.round(p / 5) - 1];
  const lo = Math.min(at(5), -5), hi = Math.max(at(95), 5);
  const pad = (hi - lo) * 0.08;
  const bands = [
    {a: at(5), b: at(95), label: "90% of simulations", h: 18, o: 0.18},
    {a: at(25), b: at(75), label: "50% of simulations", h: 18, o: 0.4}
  ];
  const med = at(50);
  const col = med >= 0 ? t.dem : t.rep;
  return Plot.plot({
    width, height, marginLeft: 14, marginRight: 14, marginTop: 28, marginBottom: 34,
    x: {domain: [lo - pad, hi + pad], label: "Forecast margin", labelAnchor: "center", labelOffset: 30,
      tickFormat: (d) => (d === 0 ? "Even" : margin(d).replace(".0", ""))},
    y: {axis: null, domain: [0, 1]},
    style: base(t),
    marks: [
      Plot.rectX([{x1: lo - pad, x2: 0}], {x1: "x1", x2: "x2", y1: 0, y2: 1, fill: t.rep, fillOpacity: 0.05}),
      Plot.rectX([{x1: 0, x2: hi + pad}], {x1: "x1", x2: "x2", y1: 0, y2: 1, fill: t.dem, fillOpacity: 0.05}),
      Plot.ruleX([0], {stroke: t.axis}),
      ...bands.map((b) => Plot.rectX([b], {x1: "a", x2: "b", y1: 0.3, y2: 0.7, fill: col, fillOpacity: b.o, rx: 4})),
      Plot.ruleX([med], {y1: 0.2, y2: 0.8, stroke: col, strokeWidth: 3}),
      Plot.text([med], {x: (d) => d, y: 0.9, text: (d) => `Median ${margin(d)}`, fill: t.ink, fontWeight: 700, fontSize: 13}),
      Plot.text([bands[0]], {x: "a", y: 0.12, text: () => margin(at(5)), fill: t["ink-3"], textAnchor: "start"}),
      Plot.text([bands[0]], {x: "b", y: 0.12, text: () => margin(at(95)), fill: t["ink-3"], textAnchor: "end"}),
      Plot.tip(bands, Plot.pointerX({x: (d) => (d.a + d.b) / 2, y: 0.5,
        title: (d) => `${d.label} fall between\n${margin(d.a)} and ${margin(d.b)}`}))
    ]
  });
}

/** Polls over time (two-party margin), with the model's recency-weighted trend. */
export function pollChart(polls, {width, height = 260, halfLife = 14, dLabel = "D", yLabel = "Poll margin (two-party)"}) {
  const t = tokens();
  const data = polls.filter((p) => p.end && p.margin != null)
    .map((p) => ({...p, date: new Date(`${p.end}T12:00:00`), partisanPoll: !!p.partisan}));
  if (!data.length) return null;
  // Trend: at each day, the average of polls to date weighted by a 14-day half-life (as the model does).
  const days = [];
  const first = new Date(Math.min(...data.map((d) => d.date))), last = new Date(Math.max(...data.map((d) => d.date)));
  for (let d = new Date(first); d <= last; d.setDate(d.getDate() + 2)) days.push(new Date(d));
  const trend = days.map((day) => {
    let w = 0, s = 0;
    for (const p of data) {
      const age = (day - p.date) / 864e5;
      if (age < 0) continue;
      const wi = Math.pow(0.5, age / halfLife) * (p.partisanPoll ? 0.5 : 1);
      w += wi; s += wi * p.margin;
    }
    return {date: day, margin: w > 0.15 ? s / w : null};
  }).filter((d) => d.margin != null);
  const ext = Math.max(8, ...data.map((d) => Math.abs(d.margin))) + 2;
  return Plot.plot({
    width, height, marginLeft: 44, marginRight: 12,
    x: {label: null, type: "utc"},
    y: {domain: [-ext, ext], label: yLabel, grid: true,
      tickFormat: (d) => (d === 0 ? "Even" : margin(d).replace(".0", "").replace("D+", `${dLabel}+`))},
    style: base(t),
    marks: [
      Plot.ruleY([0], {stroke: t.axis}),
      Plot.dot(data, {x: "date", y: "margin", r: 4, fill: (d) => (d.margin >= 0 ? t.dem : t.rep), fillOpacity: 0.55,
        stroke: t.surface, strokeWidth: 1.5, symbol: (d) => (d.partisanPoll ? "diamond" : "circle")}),
      Plot.line(trend, {x: "date", y: "margin", stroke: t.ink, strokeWidth: 2, curve: "monotone-x"}),
      Plot.tip(data, Plot.pointer({x: "date", y: "margin",
        title: (d) => `${d.pollster}${d.partisan ? ` (${d.partisan}-sponsored)` : ""}\n${date(d.end)} · ${d.n ? `${Math.round(d.n)} ${String(d.pop || "").toUpperCase()}` : ""}\n${margin(d.margin).replace("D+", `${dLabel}+`)}`}))
    ]
  });
}

/** Forecast probability over time. */
export function probHistory(history, {width, height = 200, label = "Chance of a Democratic win"}) {
  const t = tokens();
  const data = history.map((d) => ({...d, date: new Date(`${d.date}T12:00:00`)}));
  return Plot.plot({
    width, height, marginLeft: 40,
    x: {label: null, type: "utc"},
    y: {domain: [0, 1], tickFormat: "%", label, grid: true},
    style: base(t),
    marks: [
      Plot.ruleY([0.5], {stroke: t.axis}),
      Plot.line(data, {x: "date", y: "p_dem", stroke: t.ink, strokeWidth: 2}),
      Plot.dot(data.slice(-1), {x: "date", y: "p_dem", r: 4, fill: t.ink, stroke: t.surface, strokeWidth: 2}),
      Plot.tip(data, Plot.pointerX({x: "date", y: "p_dem", title: (d) => `${date(d.date.toISOString().slice(0, 10))}\n${pct(d.p_dem)} Democratic`}))
    ]
  });
}

/** Past results as diverging bars (D right, R left). */
export function pastResults(rows, {width}) {
  const t = tokens();
  if (!rows.length) return null;
  const data = rows.map((r) => ({...r, key: `${r.year} ${r.office}`}));
  // Leave ~46px beyond the longest bar for its value label, whatever the chart width.
  const marginLeft = width < 500 ? 96 : 120;
  const half = (width - marginLeft - 20) / 2;
  const ext = (Math.max(10, ...data.map((d) => Math.abs(d.margin))) + 1) / Math.max(0.35, 1 - 46 / half);
  return Plot.plot({
    width, height: 26 * data.length + 40, marginLeft, marginRight: 20,
    x: {domain: [-ext, ext], label: null, tickFormat: (d) => (d === 0 ? "Even" : margin(d).replace(".0", ""))},
    y: {label: null, domain: data.map((d) => d.key)},
    style: base(t),
    marks: [
      Plot.barX(data, {x: "margin", y: "key", fill: (d) => (d.margin >= 0 ? t.dem : t.rep), rx: 3, insetTop: 5, insetBottom: 5}),
      Plot.ruleX([0], {stroke: t.axis}),
      Plot.text(data, {x: "margin", y: "key", text: (d) => margin(d.margin), dx: 6, textAnchor: "start",
        filter: (d) => d.margin >= 0, fill: t["ink-2"]}),
      Plot.text(data, {x: "margin", y: "key", text: (d) => margin(d.margin), dx: -6, textAnchor: "end",
        filter: (d) => d.margin < 0, fill: t["ink-2"]})
    ]
  });
}
