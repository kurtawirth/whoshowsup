// Who Shows Up -- shared charts (Observable Plot). Thin marks, hairline axes,
// selective labels, a hover tip on every chart.
import * as Plot from "npm:@observablehq/plot";
import * as d3 from "npm:d3";
import {tokens, pct, margin, date} from "./wsu.js";

const base = (t) => ({background: "transparent", color: t["ink-3"], fontSize: "12px", fontFamily: "var(--sans)"});

/** How the seats could split across all simulations, party-neutral and self-explaining:
 *  a one-line summary on top ("Democratic control in 58% of simulations | Republican control in 42%"),
 *  bars colored by who controls in that outcome, and each labelled split spelled out in two
 *  colored lines under the axis ("51 D" over "49 R"). */
export function seatChart(dist, need, {width, label, total, height = 230,
    sides = ["Republican control", "Democratic control"], tieNeutral = false, pControl = null}) {
  const t = tokens();
  const shown = dist.filter((d) => d.p > 0.0004);
  const isTie = (d) => tieNeutral && d.seats * 2 === total;
  const pD = pControl ?? d3.sum(dist.filter((d) => d.seats >= need), (d) => d.p);
  const pTie = d3.sum(dist.filter(isTie), (d) => d.p);
  const pR = 1 - pD - pTie;
  const fmtP = pct;  // same rounding as the headline cards
  const summary = document.createElement("div");
  summary.className = "seat-summary";
  summary.innerHTML = `<span class="d">${sides[1]} in <b>${fmtP(pD)}</b> of simulations</span>`
    + `<span class="r">${sides[0]} in <b>${fmtP(pR)}</b></span>`
    + (pTie > 0.005 ? `<span class="n">Tie in <b>${fmtP(pTie)}</b></span>` : "");

  // Which splits get a label under the axis: every one if they fit, else a round-number step.
  const lo = d3.min(shown, (d) => d.seats), hi = d3.max(shown, (d) => d.seats);
  const perLabel = 46;
  const fit = Math.floor((width - 16) / perLabel);
  const step = [1, 2, 5, 10, 20, 25, 50].find((s) => (hi - lo) / s + 1 <= fit) ?? 50;
  const ticks = d3.range(Math.ceil(lo / step) * step, hi + 1, step);
  const labelPct = shown.length <= 16 && width >= 420;
  // Widen the x range if a side of the control line is too narrow for its label.
  let x0 = lo - 0.6, x1 = hi + 0.6;
  const room = (text) => text.length * 7 + 14;
  for (let i = 0; i < 3; i++) {
    const px = (width - 16) / (x1 - x0), line = need - 0.5;
    if ((line - x0) * px < room(sides[0])) x0 = line - room(sides[0]) / px;
    if ((x1 - line) * px < room(sides[1])) x1 = line + room(sides[1]) / px;
  }

  const plot = Plot.plot({
    width, height, marginLeft: 8, marginRight: 8, marginBottom: 40, marginTop: labelPct ? 38 : 24,
    x: {axis: null, domain: [x0, x1]},
    y: {axis: null},
    style: base(t),
    marks: [
      Plot.rectY(shown, {x1: (d) => d.seats - 0.42, x2: (d) => d.seats + 0.42, y: "p",
        fill: (d) => (d.seats >= need ? t.dem : isTie(d) ? t["Toss-up"] : t.rep), rx: 2}),
      labelPct ? Plot.text(shown.filter((d) => d.p >= 0.01), {x: "seats", y: "p", dy: -8, text: (d) => fmtP(d.p),
        fill: t["ink-2"], fontSize: 11}) : null,
      Plot.ruleX([need - 0.5], {stroke: t.ink, strokeWidth: 1}),
      Plot.text([need - 0.5], {x: (d) => d, frameAnchor: "top", dy: labelPct ? -30 : -16, dx: -8, textAnchor: "end",
        text: () => sides[0], fill: t.rep, fontSize: 12, fontWeight: 650}),
      Plot.text([need - 0.5], {x: (d) => d, frameAnchor: "top", dy: labelPct ? -30 : -16, dx: 8, textAnchor: "start",
        text: () => sides[1], fill: t.dem, fontSize: 12, fontWeight: 650}),
      Plot.ruleY([0], {stroke: t.axis}),
      Plot.text(ticks, {x: (d) => d, y: 0, dy: 13, text: (d) => `${d} D`, fill: t.dem, fontSize: 11, fontWeight: 600}),
      Plot.text(ticks, {x: (d) => d, y: 0, dy: 27, text: (d) => `${total - d} R`, fill: t.rep, fontSize: 11, fontWeight: 600}),
      Plot.tip(shown, Plot.pointerX({x: "seats", y: "p",
        title: (d) => `${d.seats} Democrats, ${total - d.seats} Republicans\n${d.seats >= need ? sides[1] : isTie(d) ? "Tie" : sides[0]}\n${(d.p * 100).toFixed(1)}% of simulations`}))
    ]
  });
  const wrap = document.createElement("div");
  wrap.append(summary, plot);
  return wrap;
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
  const zones = d3.range(0, 241).map((i) => {
    const x = at(5) + ((at(95) - at(5)) * i) / 240;
    const b = x >= at(25) && x <= at(75) ? bands[1] : bands[0];
    return {x, tip: `${b.label} fall between\n${margin(b.a)} and ${margin(b.b)}`};
  });
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
      // Hover zones follow the bands: the dark middle reports the 50% range, the light ends the 90% range.
      Plot.tip(zones, Plot.pointerX({x: "x", y: 0.5, maxRadius: 12, title: "tip"}))
    ]
  });
}

/** Polls over time (two-party margin), with the model's trend. Sponsored polls are drawn where they
 *  were published (hollow diamond) with a dotted line to where the model counts them after correcting
 *  for the sponsor's historical lean; the trend uses the corrected values, exactly as the model does. */
export function pollChart(polls, {width, height = 260, halfLife = 14, dLabel = "D", yLabel = "Poll margin (two-party)"}) {
  const t = tokens();
  const data = polls.filter((p) => p.end && p.margin != null)
    .map((p) => ({...p, date: new Date(`${p.end}T12:00:00`), sponsored: !!p.partisan, adj: p.adj ?? p.margin}));
  if (!data.length) return null;
  const fmt = (v) => (Math.abs(v) < 0.05 ? "Even" : margin(v).replace(".0", "").replace("D+", `${dLabel}+`));
  // Trend: at each day, the average of corrected polls to date, weight halving every 14 days
  // and half weight for sponsored polls (as the model does).
  const first = d3.min(data, (d) => d.date), last = d3.max(data, (d) => d.date);
  const raw = [];
  for (let d = new Date(first); d <= last; d.setDate(d.getDate() + 2)) {
    let w = 0, s = 0;
    for (const p of data) {
      const age = (d - p.date) / 864e5;
      if (age < 0) continue;
      const wi = Math.pow(0.5, age / halfLife) * (p.sponsored ? 0.5 : 1);
      w += wi; s += wi * p.adj;
    }
    if (w > 0.15) raw.push({date: new Date(d), margin: s / w});
  }
  // Split the trend where it crosses zero so each side takes its party's color.
  const trend = [];
  let seg = 0;
  raw.forEach((p, i) => {
    const prev = raw[i - 1];
    if (prev && (prev.margin >= 0) !== (p.margin >= 0)) {
      const f = prev.margin / (prev.margin - p.margin);
      const cross = new Date(+prev.date + f * (p.date - prev.date));
      trend.push({date: cross, margin: 0, seg});
      seg += 1;
      trend.push({date: cross, margin: 0, seg});
    }
    trend.push({...p, seg});
  });
  const segDem = d3.rollup(trend, (v) => d3.mean(v, (d) => d.margin) >= 0, (d) => d.seg);
  const ext = Math.max(8, ...data.map((d) => Math.max(Math.abs(d.margin), Math.abs(d.adj)))) + 2;
  const sponsored = data.filter((d) => d.sponsored);
  const plot = Plot.plot({
    width, height, marginLeft: 44, marginRight: 12,
    x: {label: null, type: "utc"},
    y: {domain: [-ext, ext], label: yLabel, grid: true, tickFormat: fmt},
    style: base(t),
    marks: [
      Plot.rect([0], {x1: first, x2: last, y1: 0, y2: ext, fill: t.dem, fillOpacity: 0.035}),
      Plot.rect([0], {x1: first, x2: last, y1: -ext, y2: 0, fill: t.rep, fillOpacity: 0.035}),
      Plot.ruleY([0], {stroke: t.axis}),
      Plot.ruleX(sponsored, {x: "date", y1: "margin", y2: "adj", stroke: t["ink-3"], strokeOpacity: 0.6, strokeDasharray: "2,2"}),
      Plot.dot(sponsored, {x: "date", y: "margin", r: 4.5, symbol: "diamond", fill: "none",
        stroke: (d) => (d.margin >= 0 ? t.dem : t.rep), strokeWidth: 1.5, strokeOpacity: 0.8}),
      Plot.dot(data, {x: "date", y: "adj", r: 4, fill: (d) => (d.adj >= 0 ? t.dem : t.rep),
        fillOpacity: 0.7, stroke: t.surface, strokeWidth: 1}),
      Plot.line(trend, {x: "date", y: "margin", z: "seg", stroke: (d) => (segDem.get(d.seg) ? t.dem : t.rep),
        strokeWidth: 2.5, curve: "monotone-x", strokeLinejoin: "round"}),
      Plot.tip(data, Plot.pointer({x: "date", y: "adj",
        title: (d) => `${d.pollster}${d.sponsored ? ` (${d.partisan}-sponsored)` : ""}\n${date(d.end)}${d.n ? ` · ${Math.round(d.n)} ${String(d.pop || "").toUpperCase()}` : ""}\n` +
          (d.sponsored ? `Published: ${fmt(d.margin)}\nCounted as: ${fmt(d.adj)} after sponsor correction` : fmt(d.margin)) +
          (d.url ? "\nClick to open the poll" : "")}))
    ]
  });
  // Clicking while a poll is highlighted opens its original release in a new tab.
  plot.addEventListener("input", () => { plot.style.cursor = plot.value?.url ? "pointer" : ""; });
  plot.addEventListener("click", () => { if (plot.value?.url) window.open(plot.value.url, "_blank", "noopener"); });
  return plot;
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
