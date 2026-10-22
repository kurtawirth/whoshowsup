// One race on election night, the same panel on the Election night page (click a race) and on its race page:
// the votes counted against the total we expect, the line each candidate has to reach to win, what's left, how the
// counted counties compare with our forecast, turnout, and the county-by-county count. Display only.
import {html} from "npm:htl";
import {pct, sides, raceHref, raceTable} from "./wsu.js";
import {raceMath} from "./live.js";

export const lastName = (s) => String(s).trim().split(/\s+/).filter((w) => !/^(Jr\.?|Sr\.?|I{2,3})$/.test(w)).pop();
/** votes, rounded for reading: "1.8 million", "412,000", "9,800" */
export const k = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)} million` : n >= 1e4 ? `${Math.round(n / 1000).toLocaleString()},000` : (Math.round(n / 100) * 100 || Math.round(n)).toLocaleString());
const chip = (tag) => html`<span class="party-chip ${tag.toLowerCase()}">${tag}</span>`;

/** A race with its count, in the shape the panel reads. r: races.json row; x: its count {pct, d, r, margin, called}. */
export function nightRace(r, x = {}, {bench = null, pNow = null, mNow = null} = {}) {
  const s = sides(r);
  const counted = (x.d ?? 0) + (x.r ?? 0) > 0;
  return {...r, s, x, b: bench, pNow, mNow, counted, called: x.called ?? null,
    lead: counted ? (x.margin >= 0 ? "D" : "R") : null, fav: r.p_dem >= 0.5 ? "D" : "R",
    tagOf: (side) => (side === "D" ? s.dTag : s.rTag), nameOf: (side) => (side === "D" ? s.d : s.r)};
}
/** "Paxton +2.3" */
export function sideText(d, m) { const side = m >= 0 ? "D" : "R"; return `${lastName(d.nameOf(side))} +${Math.abs(m).toFixed(1)}`; }

/** The finish line: our estimate of the two-party total (the turnout we expected, giving way to the count's own
 *  pace as more of it is in; never less than what's already counted), half of it to win, and what's left. */
export function finish(d, m) {
  let total = m.expected ?? 0;
  if (m.projected && m.pct >= 5) total = total ? (1 - m.pct / 100) * total + (m.pct / 100) * m.projected : m.projected;
  total = Math.max(total, m.counted);
  return total ? {total, line: total / 2, left: Math.max(total - m.counted, 0), adjusted: Boolean(m.expected && Math.abs(total / m.expected - 1) > 0.01)} : null;
}

/** The panel. counties: Map(countyKey -> {d, r, pct}) or null; link: show "Full race page"; countyTable: the
 *  county-by-county table (race pages have their own, in the county benchmarks). */
export function racePanel(d, counties, {link = true, countyTable = true} = {}) {
  const m = raceMath(d, d.x, d.b, counties);
  const D = lastName(d.nameOf("D")), R = lastName(d.nameOf("R"));
  const out = [];
  const odds = d.pNow != null && !d.called ? ` · Live odds: ${lastName(d.nameOf(d.pNow >= 0.5 ? "D" : "R"))} ${pct(Math.max(d.pNow, 1 - d.pNow))}` : "";
  out.push(html`<p class="rd-meta">This morning we gave ${lastName(d.nameOf(d.fav))} ${pct(Math.max(d.p_dem, 1 - d.p_dem))}${odds}${link ? html` · <a href="${raceHref(d.race_id)}">Full race page</a>` : ""}</p>`);
  const f = finish(d, m);
  if (!m.counted) {
    out.push(html`<p>No votes counted yet.${f ? ` We expect about ${k(f.total)} votes for the two main sides, so about ${k(f.line)} to win.` : ""}</p>`);
    return out;
  }

  // the count so far, where we now expect each side to finish, and the line it takes to win
  if (f) {
    const order = (d.called ?? d.lead) === "R" ? ["R", "D"] : ["D", "R"];
    const mNow = d.called ? d.x.margin : d.mNow ?? d.margin_median;  // live estimate of the final margin
    const votesOf = (side) => d.x[side === "D" ? "d" : "r"] ?? 0;
    const expOf = (side) => f.total * (0.5 + (side === "D" ? mNow : -mNow) / 200);
    const scale = Math.max(expOf("D"), expOf("R"), f.line, votesOf("D"), votesOf("R")) * 1.08;
    const X = (v) => `${Math.min(100, (100 * v) / scale).toFixed(2)}%`;
    const bar = (side) => {
      const votes = votesOf(side), exp = expOf(side), more = f.line - votes;
      const el = html`<div class="rn-bar" role="img" aria-label="${d.nameOf(side)}: ${votes.toLocaleString()} votes counted; expected to finish near ${k(exp)}; ${k(f.line)} needed to win"></div>`;
      el.innerHTML = `<b class="${d.tagOf(side).toLowerCase()}" style="width:${X(votes)}"></b>`
        + (d.called ? "" : `<i class="exp" style="left:${X(exp)}"></i>`) + `<u style="left:${X(f.line)}"></u>`;
      const note = d.called ? (d.called === side ? "Won" : "")
        : `Now expected to finish near ${k(exp)}${more > 0 ? ` · needs ${k(more)} more to win${f.left ? ` (${Math.min(100, Math.round((100 * more) / f.left))}% of what's left)` : ""}` : " · already past the line"}`;
      return html`<div class="rn-cand">
        <div class="rn-top">${chip(d.tagOf(side))} <span class="rn-name">${d.nameOf(side)}</span> <b>${votes.toLocaleString()}</b> <span class="muted">${((100 * votes) / m.counted).toFixed(1)}%</span></div>
        ${el}<div class="rn-go">${note}</div></div>`;
    };
    out.push(html`<div class="rn-head"><b>${k(m.counted)}</b> votes counted of about <b>${k(f.total)}</b> we now expect${m.pct ? html` <span class="muted">(civicAPI estimates ${m.pct}%)</span>` : ""}</div>`);
    out.push(html`<div class="rn-race">${order.map(bar)}</div>`);
    out.push(html`<div class="rn-key"><span><b class="sw"></b>counted so far</span>${d.called ? "" : html`<span><i class="sw"></i>where we now expect them to finish</span>`}<span><u class="sw"></u>${k(f.line)} to win: half the ${k(f.total)} votes we now expect${f.adjusted ? ` (we expected ${k(m.expected)} this morning; the count's pace has moved it)` : ""}</span></div>`);
  }

  // three numbers to scan
  const tiles = [];
  if (f && !d.called && m.pct < 100) tiles.push(tile("Votes left", `~${k(f.left)}`, `of the ${k(f.total)} we now expect`));
  if (m.gap != null) tiles.push(tile("Against our forecast", Math.abs(m.gap) < 0.5 ? "On target" : `${lastName(d.nameOf(m.gap > 0 ? "D" : "R"))} +${Math.abs(m.gap).toFixed(1)}`,
    `in the counties counted so far: we expected ${sideText(d, m.expectedNow)} there; the count is ${sideText(d, (100 * m.lead) / m.counted)}`));
  else tiles.push(tile("Against our forecast", sideText(d, d.x.margin), `the count so far; our most likely result was ${sideText(d, d.margin_median)}${d.office === "HOUSE" ? " (no county breakdown for House districts, so early counts can mislead)" : ""}`));
  if (m.turnout != null) {
    const lean = m.turnoutLean ?? {};
    tiles.push(tile("Turnout", `${m.turnout >= 0 ? "+" : "−"}${Math.round(Math.abs(m.turnout) * 100)}%`,
      `on pace for ~${k(m.projected)} against the ${k(m.expected)} we expected${lean.D != null && lean.R != null ? `; Democratic-leaning counties ${sign(lean.D)}, Republican-leaning ${sign(lean.R)}` : ""}`));
  }
  out.push(html`<div class="rn-tiles">${tiles}</div>`);

  // county by county, folded away until asked for
  const cr = (m.countyRows ?? []).filter((c) => c.counted);
  if (cr.length && countyTable) {
    const unit = d.state_po === "LA" ? "parish" : "county", units = unit === "parish" ? "parishes" : "counties";
    const box = html`<details class="rn-counties"><summary>County by county (${cr.length} of ${m.countyRows.length} ${units} reporting)</summary></details>`;
    box.addEventListener("toggle", () => {
      if (!box.open || box.querySelector("table")) return;
      box.append(raceTable([...m.countyRows].sort((x, y) => y.share - x.share), [
        {key: "label", label: unit === "parish" ? "Parish" : "County", sort: true},
        {key: "pct", label: "Counted", num: true, sort: true, defaultDir: -1, render: (c) => (c.counted ? `${c.pct}%` : "")},
        {key: "margin", label: "Count", num: true, sort: true, render: (c) => (c.margin == null ? "" : sideText(d, c.margin))},
        {key: "bench", label: "Benchmark", num: true, sort: true, render: (c) => sideText(d, c.bench)},
        {key: "gap", label: "vs. benchmark", num: true, sort: true, render: (c) => (c.gap == null ? "" : `${lastName(d.nameOf(c.gap >= 0 ? "D" : "R"))} +${Math.abs(c.gap).toFixed(1)}`)},
        {key: "turnout", label: "Turnout vs. expected", num: true, sort: true, render: (c) => (c.turnout == null ? "" : sign(c.turnout))}
      ], {search: m.countyRows.length > 15, placeholder: `Search ${units}`, noun: unit, pageSize: 10}),
      html`<p class="caption">Benchmark: what each ${unit} would show if the race landed exactly on our most likely result. A side running ahead of the benchmark in most places is outrunning our forecast.</p>`);
    });
    out.push(box);
  }
  return out;
}
const sign = (x) => `${x >= 0 ? "+" : "−"}${Math.round(Math.abs(x) * 100)}%`;
const tile = (label, value, note) => html`<div class="rn-tile"><div class="k">${label}</div><div class="v">${value}</div><div class="n">${note}</div></div>`;
