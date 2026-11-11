// After the election: each race's result next to our final forecast and the other forecasters' final calls.
// Reads data/scorecard.json (midterms_2026/export_results.py), rebuilt with every results update.
import {html} from "npm:htl";
import {tokens, pct, margin, sides, link} from "./wsu.js";

export const PICK = {"Safe D": "D", "Likely D": "D", "Lean D": "D", "Tilt D": "D", "Toss-up": null,
  "Tilt R": "R", "Lean R": "R", "Likely R": "R", "Safe R": "R"};
const lastName = (s) => String(s ?? "").trim().split(/\s+/).filter((w) => !/^(Jr\.?|Sr\.?|I{2,3})$/.test(w)).pop();

/** Names and tags for each side of a race, and a margin written with the candidates' tags ("D+7.9", "I+3.0"). */
export function sideInfo(r) {
  const s = sides(r);
  const tag = (side) => (side === "D" ? s.dTag : s.rTag);
  const name = (side) => (side === "D" ? s.d : s.r);
  const m = (v) => (v == null ? "–" : Math.abs(v) < 0.05 ? "Even" : `${tag(v > 0 ? "D" : "R")}+${Math.abs(v).toFixed(1)}`);
  return {s, tag, name, last: (side) => lastName(name(side)), m};
}

/** Whose chance our final forecast favored, in words: "Lombardo 50%". */
export function ourPick(r, row) {
  const {last} = sideInfo(r);
  return row.fav ? `${last(row.fav)} ${pct(Math.max(row.p, 1 - row.p))}` : "Even, 50%";
}

/** One forecaster's grade on a race: right, wrong or (a Toss-up) no pick. */
export function grade(pick, called) {
  return pick == null ? "none" : pick === called ? "right" : "wrong";
}
const MARK = {right: "✓", wrong: "✗", none: "–"};
const WORD = {right: "picked the winner", wrong: "missed", none: "no pick"};

/** The result box at the top of a race page. */
export function resultBox(r, row, sc, {outletMeta = []} = {}) {
  const t = tokens(), I = sideInfo(r);
  const w = row.called, lose = w === "D" ? "R" : "D";
  const color = (side) => (I.tag(side) === "I" ? t.ind : side === "D" ? t.dem : t.rep);
  const two = (row.d ?? 0) + (row.r ?? 0);
  const share = (side) => (two ? `${((100 * (side === "D" ? row.d : row.r)) / two).toFixed(1)}%` : "–");
  const ours = grade(row.fav, w);
  const when = new Date(sc.asof).toLocaleDateString("en-US", {month: "short", day: "numeric", timeZone: "America/New_York"});
  const chip = (side) => html`<span class="party-chip ${I.tag(side).toLowerCase()}">${I.tag(side)}</span>`;
  let vs;
  // near-final counts in ordinary two-candidate races get a provisional comparison, labeled with the share counted
  const twoWay = r.race_type === "standard" && (row.d ?? 0) > 0 && (row.r ?? 0) > 0;
  const prov = !row.graded && twoWay && row.margin != null && (row.pct ?? 0) >= 85;
  if (row.graded || prov) {
    const miss = row.graded ? row.miss : row.margin - row.med;
    const inside = row.graded ? row.inside : row.lo <= row.margin && row.margin <= row.hi;
    const toward = miss > 0 ? "D" : "R";
    vs = html`<div><div class="k">Result vs. our forecast</div><div class="v">${Math.abs(miss) < 0.05 ? "Right on" : `${Math.abs(miss).toFixed(1)} points more ${I.last(toward)}`}</div>
      <div class="cmp-p">${inside ? "Inside" : "Outside"} our 80% range (${I.m(row.lo)} to ${I.m(row.hi)})${prov ? `, with ${row.pct}% counted` : ""}</div></div>`;
  } else {
    vs = twoWay
      ? html`<div><div class="k">Result vs. our forecast</div><div class="v">Still counting</div><div class="cmp-p">Margins are compared once most of the vote is counted (now ${row.pct}%).</div></div>`
      : html`<div><div class="k">Result vs. our forecast</div><div class="v">Not compared</div><div class="cmp-p">Margins are compared only in races with one candidate from each major party.</div></div>`;
  }
  const raters = outletMeta.filter((o) => row.outlets?.[o.name]).map((o) => {
    const v = row.outlets[o.name], g = grade(PICK[v], w);
    return html`<li class="g-${g}"><span class="rr-name">${o.short}</span><span class="cmp-pill" style="background:${t[v]};color:${v.startsWith("Safe") || v.startsWith("Likely") ? "#fff" : "#111"}">${v}</span><span class="rr-mark" title="${WORD[g]}">${MARK[g]}</span></li>`;
  });
  if (row.pi != null) {
    const side = row.pi > 0.5 ? "D" : row.pi < 0.5 ? "R" : null, g = grade(side, w);
    raters.push(html`<li class="g-${g}"><span class="rr-name">PredictIt</span><span class="rr-p">${side ? `${I.last(side)} ${pct(Math.max(row.pi, 1 - row.pi))}` : "50/50"}</span><span class="rr-mark" title="${WORD[g]}">${MARK[g]}</span></li>`);
  }
  return html`<div class="result-box">
    <div class="result-head">${chip(w)} <b>${I.name(w)} wins</b><span class="result-tag ${ours}">${ours === "right" ? "Our forecast picked the winner" : ours === "wrong" ? "Our forecast missed" : "Our forecast called it even"}</span></div>
    <p class="result-line">${I.last(w)} <b style="color:${color(w)}">${share(w)}</b> · ${I.last(lose)} <b style="color:${color(lose)}">${share(lose)}</b> of the two-candidate vote (${I.m(row.margin)})${row.pct != null ? `, ${row.pct}% counted` : ""}. Called by civicAPI; counts as of ${when}.</p>
    <div class="result-grid">
      <div><div class="k">Our final forecast</div><div class="v">${ourPick(r, row)}</div><div class="cmp-p">Most likely result ${I.m(row.med)}</div></div>
      ${vs}
    </div>
    ${raters.length ? html`<div class="result-raters"><div class="k">How the other forecasters called it</div><ul>
      ${(() => { const v = r.rating, g = grade(PICK[v], w);
        return html`<li class="g-${g}"><span class="rr-name"><b>Who Shows Up</b> <span class="muted">(${ourPick(r, row)})</span></span><span class="cmp-pill" style="background:${t[v]};color:${v.startsWith("Safe") || v.startsWith("Likely") ? "#fff" : "#111"}">${v}</span><span class="rr-mark" title="${WORD[g]}">${MARK[g]}</span></li>`; })()}${raters}</ul></div>` : ""}
    <p class="result-more"><a href="${link("scorecard")}">How our forecast did in every race, and against the other forecasters →</a></p>
  </div>`;
}

/** A chamber's result: seats won as called, against our forecast's most likely number and 80% range. */
export function seatCard(label, c, unit, {href = null} = {}) {
  const t = tokens();
  const total = c.seats_total, lo = Math.max(0, Math.min(c.p10, c.d_called) - (unit === "House" ? 25 : 6)), hi = Math.min(total, Math.max(c.p90, c.d_called + c.d_leading) + (unit === "House" ? 25 : 6));
  const x = (v) => `${(100 * (v - lo)) / (hi - lo)}%`;
  const dTotal = c.d_called, rTotal = c.r_called;
  const parts = [["Democrats", c.d_leading], ["Republicans", c.r_leading], ["independents", c.i_leading]].filter(([, n]) => n);
  const leaders = !c.uncalled ? "" : c.uncalled === 1 && parts.length === 1 ? ` 1 still uncalled, with ${parts[0][0]} ahead.`
    : ` ${c.uncalled} still uncalled: ${parts.map(([who, n]) => `${who} lead in ${n}`).join(", ")}.`;
  const where = dTotal > c.p90 ? "above the top of our 80% range" : dTotal < c.p10 ? "below the bottom of our 80% range" : "inside our 80% range";
  const card = html`<div class="hero-card">
    <div class="label">${label}</div>
    <div class="seat-split"><span style="color:${t.dem}">${dTotal}</span><small>D</small><span class="dash">–</span><span style="color:${t.rep}">${rTotal}</span><small>R</small>${c.i_called ? html`<span class="dash">–</span><span style="color:${t.ind}">${c.i_called}</span><small>I</small>` : ""}</div>
    <div class="sub">${unit === "Governors" ? "governorships won" : "seats won"}, as called.${leaders}</div>
    <div class="seat-scale"><div class="track"></div><div class="band" style="left:${x(c.p10)};width:calc(${x(c.p90)} - ${x(c.p10)})"></div><div class="med" style="left:${x(c.median)}"></div><div class="act" style="left:${x(dTotal)};background:${t.dem}"></div></div>
    <div class="seat-scale-lab"><span style="left:${x(c.p10)}">${c.p10}</span><span style="left:${x(c.median)}">${c.median}</span><span style="left:${x(c.p90)}">${c.p90}</span></div>
    <div class="sub" style="margin-top:8px">Our forecast: <b>${c.median}</b> Democratic ${unit === "Governors" ? "governors" : "seats"} most likely, ${c.p10}–${c.p90} in 80% of simulations (gray band).${c.p_control_d != null ? ` Democrats won control in ${pct(c.p_control_d)} of simulations; Republicans in ${100 - Math.round(100 * c.p_control_d)}%.` : ""} The called total so far is ${where}; our simulations gave ${dTotal} or more Democratic ${unit === "Governors" ? "governors" : "seats"} a ${pct(c.p_at_least_called)} chance.</div>
  </div>`;
  if (!href) return card;
  const a = document.createElement("a");
  a.className = "hero-card";
  a.href = href;
  a.append(...card.childNodes);
  return a;
}
