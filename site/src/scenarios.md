---
title: What if
---

```js
import {pct, margin, date, raceLink, sides, countEvent, shareBar} from "./components/wsu.js";
import {loadSims, weigh, summarize, turnoutToMargin} from "./components/sims.js";
const races = FileAttachment("data/races.json").json();
const top = FileAttachment("data/topline.json").json();
const meta = FileAttachment("data/sims_meta.json").json();
const buf = FileAttachment("data/sims.bin").arrayBuffer();
const pollMiss = FileAttachment("data/poll_miss.json").json();
```

# What if?

<p class="dek">Every number on this site comes from simulating the election thousands of times. Here you choose a scenario, and we keep only the simulations where it happens (or lean on the ones closest to it) and recount. Nothing you do here changes the forecast.</p>

```js
const ui = makeUI(loadSims(buf, meta));
display(ui.bar);
```

## Turn the turnout dial

<p class="caption">Suppose Democrats turn out better or worse than our forecast expects, relative to Republicans. The dial converts that into a national House vote and leans on the simulations that land near it. In our model, part of every national swing comes from turnout and part from persuasion: a turnout-driven swing moves close races more than lopsided ones, while persuasion moves every race by about the same amount.</p>

```js
display(ui.dial);
```

## Pick the winners

<p class="caption">Choose who wins any race and we keep only the simulations where that happened. Every pick leaves fewer simulations, so stacking many unlikely picks makes the numbers rough; the bar above says how many are left.</p>

```js
display(ui.picks);
```

## How the other races move

```js
display(ui.moves);
```

## If the polls miss like they did in…

<p class="caption">Our forecast doesn't assume this year's polls lean either way. Here we rerun it as if every 2026 polling average misses the way its state's final polls did in a past year (pulled toward that year's national average where a state had only a few polls), with the generic ballot missing the same way, and everything else unchanged. These are reruns of the full model, not filtered simulations.</p>

```js
{
  const pm = pollMiss;
  if (!pm) display(html`<p class="caption">Not available today.</p>`);
  else {
    const fc = pm.scenarios.find((s) => s.year === "forecast");
    const years = pm.scenarios.filter((s) => s.year !== "forecast");
    const party = (p) => (p >= 0.5 ? `D ${pct(p)}` : `R ${pct(1 - p)}`);
    const over = (m) => (Math.abs(m) < 0.5 ? "about right" : `${m > 0 ? "Democrats" : "Republicans"} by ${Math.abs(m).toFixed(1)}`);
    display(html`<div class="table-wrap"><table class="wsu-table">
      <thead><tr><th>Polls miss like</th><th>Statewide polls overstated</th><th class="num">Senate control</th><th class="num">House control</th><th class="num">Senate seats (D)</th><th class="num">House seats (D)</th></tr></thead>
      <tbody>
        <tr class="base"><td><b>Our forecast</b></td><td>no lean assumed</td><td class="num">${party(fc.p_senate_d)}</td><td class="num">${party(fc.p_house_d)}</td><td class="num">${fc.senate_median}</td><td class="num">${fc.house_median}</td></tr>
        ${years.map((s) => html`<tr><td>${s.year}</td><td>${over(s.statewide_miss)}</td><td class="num">${party(s.p_senate_d)}</td><td class="num">${party(s.p_house_d)}</td><td class="num">${s.senate_median}</td><td class="num">${s.house_median}</td></tr>`)}
      </tbody></table></div>`);
    const miss = years.filter((s) => s.statewide_miss >= 0.5).length;
    const flips = (k) => years.filter((s) => (s[k] >= 0.5) !== (fc[k] >= 0.5)).map((s) => s.year);
    const list = (a) => (a.length <= 2 ? a.join(" and ") : `${a.slice(0, -1).join(", ")} and ${a[a.length - 1]}`);
    const sen = flips("p_senate_d"), house = flips("p_house_d");
    display(html`<p>In ${miss} of these ${years.length} elections, the final statewide polls overstated Democrats. ${sen.length ? `${fc.p_senate_d >= 0.5 ? "Democrats" : "Republicans"}, our Senate favorites, become the underdogs if the polls miss like they did in ${list(sen)}: the Senate odds rest on races where the polling averages are close.` : "Our Senate favorite stays the favorite in every scenario."} ${house.length ? `The House flips in the ${list(house)} scenario${house.length > 1 ? "s" : ""}.` : `${fc.p_house_d >= 0.5 ? "Democrats" : "Republicans"} stay favored for the House in every scenario, because the House depends far less on polls of individual districts.`}</p>`);
  }
}
```

```js
{
  const pm = pollMiss;
  if (pm) {
    const years = pm.columns.filter((c) => c !== "forecast");
    const pick = Inputs.radio(years, {label: "Senate and governor races if the polls miss like", value: "2020"});
    const out = html`<div></div>`;
    const draw = () => {
      const i = pm.columns.indexOf(pick.value), f = pm.columns.indexOf("forecast");
      const list = races.filter((r) => (r.office === "SEN" || r.office === "GOV") && pm.races[r.race_id])
        .map((r) => ({r, a: pm.races[r.race_id][f], b: pm.races[r.race_id][i]}))
        .filter((x) => Math.abs(x.b - x.a) >= 0.03).sort((x, y) => Math.abs(y.b - y.a) - Math.abs(x.b - x.a)).slice(0, 14);
      const chance = (r, p) => { const s = sides(r); return p >= 0.5 ? `${pct(p)} ${s.dTag === "I" ? "Osborn" : "D"}` : `${pct(1 - p)} R`; };
      out.replaceChildren(html`<div class="table-wrap"><table class="wsu-table"><thead><tr><th>Race</th><th class="num">Our forecast</th><th class="num">If polls miss like ${pick.value}</th></tr></thead>
        <tbody>${list.map((x) => html`<tr><td>${raceLink(x.r, `${x.r.label}${x.r.office === "GOV" ? " (governor)" : x.r.special ? "" : " (Senate)"}`)}</td><td class="num">${chance(x.r, x.a)}</td><td class="num">${chance(x.r, x.b)}</td></tr>`)}</tbody></table></div>`);
    };
    pick.addEventListener("input", draw);
    draw();
    display(pick);
    display(out);
  }
}
```

```js
display(shareBar({path: "/scenarios", text: "Play out the 2026 midterms your way: pick winners or turn the turnout dial and watch the House and Senate odds change.", label: "Share this page"}));
```

```js
function makeUI(sims) {
  const byId = new Map(races.map((r) => [r.race_id, r]));
  const base = summarize(sims, weigh(sims));
  const state = {picks: new Map(), x: null, how: null};
  const last = (s) => String(s ?? "").trim().split(/\s+/).filter((w) => !/^(Jr\.?|Sr\.?|I{2,3})$/.test(w)).pop();
  const chance = (r, p) => {
    const s = sides(r);
    return p >= 0.5 ? `${pct(p)} ${s.dTag === "I" ? last(s.d) : "D"}` : `${pct(1 - p)} ${s.rTag === "I" ? last(s.r) : "R"}`;
  };
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  // ---- the results bar (sticks under the header while you scroll) ----
  const bar = el("div", "scn-bar");
  const stat = (k) => { const s = el("div", "s"); const kk = el("div", "k", k), v = el("div", "v"), was = el("div", "was"); s.append(kk, v, was); bar.append(s); return {v, was}; };
  const sSen = stat("Senate control"), sHouse = stat("House control"), sGov = stat("Governors"), sEnv = stat("National House vote");
  const foot = el("div", "scn-foot");
  const reset = el("button", "scn-reset", "Reset");
  reset.addEventListener("click", () => {
    state.picks.clear(); state.x = null; state.how = null;
    slider.value = 0; howBtns.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.how === "")));
    rows.forEach((r) => r.sync());
    update();
  });
  bar.append(foot, reset);
  // a slim copy along the bottom of the screen once the bar scrolls away
  const mini = el("div", "scn-mini");
  const miniText = el("span");
  const miniReset = el("button", "scn-reset-mini", "Reset");
  miniReset.addEventListener("click", () => reset.click());
  mini.append(miniText, miniReset);
  document.body.append(mini);
  new IntersectionObserver(([e]) => mini.classList.toggle("on", !e.isIntersecting && e.boundingClientRect.top < 0)).observe(bar);
  invalidation.then(() => mini.remove());

  // ---- the turnout dial ----
  const Es = Array.from(sims.E).sort((p, q) => p - q);
  const q = (f) => Es[Math.floor(f * (Es.length - 1))];
  const lo = q(0.01), hi = q(0.99);
  let xmin = 0, xmax = 0;
  for (let x = -0.3; x <= 0.3; x += 0.01) {
    const m = turnoutToMargin(x, top.nat_median);
    if (m >= lo && xmin === 0 && x < 0) xmin = Math.ceil(x * 100);
    if (m <= hi) xmax = Math.floor(x * 100 + 1e-9);
  }
  const dial = el("div", "scn-dial");
  const slider = Object.assign(document.createElement("input"), {type: "range", min: xmin, max: xmax, step: 1, value: 0});
  slider.setAttribute("aria-label", "Democratic turnout relative to Republican turnout, compared with our forecast");
  const dialText = el("p", "scn-dial-text");
  const ends = el("div", "scn-ends");
  ends.append(el("span", null, `← Democratic turnout ${-xmin}% weaker`), el("span", null, `${xmax}% stronger →`));
  slider.addEventListener("input", () => { state.x = +slider.value / 100; schedule(); });
  slider.addEventListener("change", () => countEvent("whatif-dial", "What if: turnout dial"));
  const howRow = el("div", "scn-how");
  howRow.append(el("span", "k", "Where the swing comes from:"));
  const howBtns = [["", "Any mix"], ["turnout", "Mostly turnout"], ["persuasion", "Mostly persuasion"]].map(([v, t]) => {
    const b = el("button", "seg", t);
    b.dataset.how = v;
    b.setAttribute("aria-pressed", String(v === ""));
    b.addEventListener("click", () => {
      state.how = v || null;
      howBtns.forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      update();
    });
    howRow.append(b);
    return b;
  });
  dial.append(slider, ends, dialText, howRow);

  // ---- pick the winners ----
  const stored = sims.races.map((id) => byId.get(id)).filter(Boolean);
  const close = (r) => Math.abs(r.p_dem - 0.5);
  const rows = [];
  function row(r) {
    const s = sides(r);
    const d = el("div", "scn-row");
    const name = el("div", "nm");
    name.append(raceLink(r), el("span", "who", `${s.d} vs. ${s.r}`));
    const now = el("div", "now");
    const seg = el("div", "segs");
    const opts = [["D", last(s.d)], ["", "Either"], ["R", last(s.r)]].map(([v, t]) => {
      const b = el("button", `seg${v === "D" ? (s.dTag === "I" ? " i" : " d") : v === "R" ? " r" : ""}`, t);
      b.addEventListener("click", () => {
        if (v) state.picks.set(r.race_id, v); else state.picks.delete(r.race_id);
        sync();
        update();
        if (v) countEvent("whatif-pick", `What if: ${r.race_id}`);
      });
      seg.append(b);
      return [v, b];
    });
    const sync = () => opts.forEach(([v, b]) => b.setAttribute("aria-pressed", String((state.picks.get(r.race_id) ?? "") === v)));
    sync();
    d.append(name, now, seg);
    const api = {r, node: d, now, sync};
    rows.push(api);
    return d;
  }
  const picks = el("div", "scn-picks");
  const group = (title, list, shown) => {
    const box = el("div", "scn-group");
    box.append(el("h3", null, title));
    const wrap = el("div");
    list.forEach((r, i) => { const n = row(r); if (i >= shown) n.hidden = true; wrap.append(n); });
    box.append(wrap);
    if (list.length > shown) {
      const more = el("button", "scn-more", `Show all ${list.length}`);
      more.addEventListener("click", () => { wrap.querySelectorAll(".scn-row").forEach((n) => (n.hidden = false)); more.remove(); });
      box.append(more);
    }
    return box;
  };
  const sen = stored.filter((r) => r.office === "SEN").sort((a, b) => close(a) - close(b));
  const gov = stored.filter((r) => r.office === "GOV").sort((a, b) => close(a) - close(b));
  const house = stored.filter((r) => r.office === "HOUSE").sort((a, b) => close(a) - close(b));
  picks.append(group("Senate", sen, 12), group("Governors", gov, 8));
  // House: the closest ten, plus a search for any other district that isn't a lock
  const hBox = group("House", house.slice(0, 10), 10);
  const search = Object.assign(document.createElement("input"), {type: "search", placeholder: "Add a House district: try a name, state or district (e.g. TX-34)"});
  search.className = "scn-search";
  const found = el("div");
  search.addEventListener("input", () => {
    const t = search.value.trim().toLowerCase();
    found.replaceChildren();
    if (t.length < 2) return;
    const shownIds = new Set(rows.map((x) => x.r.race_id));
    house.filter((r) => !shownIds.has(r.race_id) && [r.label, r.state_name, r.dem_name, r.rep_name, r.incumbent].filter(Boolean).join(" ").toLowerCase().includes(t))
      .slice(0, 6).forEach((r) => {
        const b = el("button", "scn-add", `+ ${r.label}: ${sides(r).d} vs. ${sides(r).r}`);
        b.addEventListener("click", () => { hBox.querySelector("div").append(row(r)); b.remove(); update(); });
        found.append(b);
      });
  });
  hBox.append(search, found);
  picks.append(hBox);

  // ---- how the other races move ----
  const moves = el("div");

  // ---- recount ----
  let pending = false;
  function schedule() { if (!pending) { pending = true; requestAnimationFrame(() => { pending = false; update(); }); } }
  function update() {
    const target = state.x == null ? null : turnoutToMargin(state.x, top.nat_median);
    const w = weigh(sims, {picks: state.picks, env: target == null ? null : {target, bw: 0.6}, how: state.how});
    const S = summarize(sims, w);
    const active = state.picks.size || state.x != null || state.how;
    const party = (p) => (p >= 0.5 ? `D ${pct(p)}` : `R ${pct(1 - p)}`);
    if (!S.ess) {
      [sSen, sHouse, sGov, sEnv].forEach((x) => { x.v.textContent = "–"; x.was.textContent = ""; });
      foot.textContent = "No simulation matches this combination: our forecast puts it below 1 in 10,000.";
      miniText.textContent = "No simulation matches these picks";
      foot.className = "scn-foot warn";
      rows.forEach((x) => (x.now.textContent = ""));
      moves.replaceChildren(el("p", "caption", "Remove a pick to see how the other races move."));
      return;
    }
    miniText.textContent = `Senate ${party(S.pSen)} · House ${party(S.pHouse)}${active ? ` · ${Math.round(S.ess).toLocaleString()} sims` : ""}`;
    sSen.v.textContent = party(S.pSen);
    sHouse.v.textContent = party(S.pHouse);
    sGov.v.textContent = `${S.govMedian} D`;
    sEnv.v.textContent = margin(S.env);
    sSen.was.textContent = active ? `forecast: ${party(base.pSen)}` : `about ${S.senMedian} D seats`;
    sHouse.was.textContent = active ? `forecast: ${party(base.pHouse)}` : `about ${S.houseMedian} D seats`;
    sGov.was.textContent = active ? `forecast: ${base.govMedian} D` : "median of 36";
    sEnv.was.textContent = active ? `forecast: ${margin(base.env)}` : "average across simulations";
    const left = Math.round(S.ess);
    foot.textContent = active
      ? `Based on ${state.x != null ? "about " : ""}${left.toLocaleString()} of ${sims.n.toLocaleString()} simulations${left < 200 ? ". That's few, so treat these numbers as rough." : "."}`
      : `Our forecast as of ${date(top.forecast_date)}, from ${sims.n.toLocaleString()} simulations. Choose a scenario below.`;
    foot.className = `scn-foot${active && left < 200 ? " warn" : ""}`;
    dialText.textContent = state.x == null
      ? `Dial not set: every national outcome counts, centered on our forecast of ${margin(top.nat_median)}.`
      : state.x === 0
        ? `Turnout lands right where we expect: a national House vote near ${margin(target)}, with the uncertainty about the national mood taken away.`
        : `Democrats turn out ${Math.abs(Math.round(state.x * 100))}% ${state.x > 0 ? "better" : "worse"} than we expect, relative to Republicans: a national House vote near ${margin(target)}.`;
    for (const x of rows) {
      const p = S.p[x.r.race_id];
      x.now.textContent = state.picks.has(x.r.race_id) ? "picked" : chance(x.r, p);
      x.now.classList.toggle("changed", active && Math.abs(p - x.r.p_dem) >= 0.05 && !state.picks.has(x.r.race_id));
    }
    if (!active) { moves.replaceChildren(el("p", "caption", "Pick a winner or turn the dial, and the races that move most will show up here.")); return; }
    const deltas = stored.filter((r) => !state.picks.has(r.race_id))
      .map((r) => ({r, p: S.p[r.race_id], d: S.p[r.race_id] - base.p[r.race_id]}))
      .filter((m) => Math.abs(m.d) >= 0.02).sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 12);
    if (!deltas.length) { moves.replaceChildren(el("p", "caption", "No other race moves by more than 2 points in this scenario.")); return; }
    const t = el("table", "wsu-table");
    t.innerHTML = `<thead><tr><th>Race</th><th class="num">Forecast</th><th class="num">This scenario</th><th class="num">Democratic chance</th></tr></thead>`;
    const tb = t.createTBody();
    for (const m of deltas) {
      const tr = tb.insertRow();
      const c0 = tr.insertCell(); c0.append(raceLink(m.r));
      tr.insertCell().textContent = chance(m.r, base.p[m.r.race_id]);
      tr.insertCell().textContent = chance(m.r, m.p);
      tr.insertCell().textContent = `${m.d > 0 ? "+" : "−"}${Math.round(Math.abs(m.d) * 100)} pts`;
      [1, 2, 3].forEach((i) => (tr.cells[i].className = "num"));
    }
    const wrap = el("div", "table-wrap");
    wrap.append(t);
    moves.replaceChildren(wrap);
  }
  update();
  return {bar, dial, picks, moves};
}
```
