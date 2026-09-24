// Who Shows Up -- shared components: colors, formatting, tooltip, maps, tables.
import * as d3 from "npm:d3";
import * as topojson from "npm:topojson-client";

export const RATINGS = ["Safe D", "Likely D", "Lean D", "Toss-up", "Lean R", "Likely R", "Safe R"];
const RATING_TOKEN = {
  "Safe D": "--safe-d", "Likely D": "--likely-d", "Lean D": "--lean-d", "Toss-up": "--tossup",
  "Lean R": "--lean-r", "Likely R": "--likely-r", "Safe R": "--safe-r"
};

/** Resolved color tokens for the current theme (SVG attributes can't read CSS variables). */
export function tokens() {
  const cs = getComputedStyle(document.documentElement);
  const get = (v) => cs.getPropertyValue(v).trim();
  const t = {};
  for (const r of RATINGS) t[r] = get(RATING_TOKEN[r]);
  for (const k of ["surface", "page", "ink", "ink-2", "ink-3", "hair", "axis", "dem", "rep", "ind", "card"]) t[k] = get(`--${k}`);
  return t;
}

/** Text color that stays legible on a filled rating tile. */
export function inkOn(fill) {
  const c = d3.lab(fill);
  return c.l > 62 ? "#0b0b0b" : "#ffffff";
}

export const ratingOf = (p) =>
  p >= 0.95 ? "Safe D" : p >= 0.8 ? "Likely D" : p >= 0.6 ? "Lean D" : p > 0.4 ? "Toss-up" : p > 0.2 ? "Lean R" : p > 0.05 ? "Likely R" : "Safe R";

// ---------- formatting ----------
export const pct = (p) => (p >= 0.995 ? ">99%" : p <= 0.005 ? "<1%" : `${Math.round(p * 100)}%`);
export const margin = (m) => (m == null || isNaN(m) ? "–" : m >= 0 ? `D+${Math.abs(m).toFixed(1)}` : `R+${Math.abs(m).toFixed(1)}`);
export const marginShort = (m) => (m == null || isNaN(m) ? "–" : m >= 0 ? `D+${Math.round(Math.abs(m))}` : `R+${Math.round(Math.abs(m))}`);
export const date = (s) => new Date(`${s}T12:00:00`).toLocaleDateString("en-US", {month: "short", day: "numeric", year: "numeric"});
export const shortDate = (s) => new Date(`${s}T12:00:00`).toLocaleDateString("en-US", {month: "short", day: "numeric"});
export function oddsPhrase(p) {
  // "about 3 in 4" style phrasing for probabilities, the way people actually talk
  if (p >= 0.99) return "more than 99 in 100";
  if (p <= 0.01) return "less than 1 in 100";
  const fracs = [[1, 10], [1, 8], [1, 6], [1, 5], [1, 4], [1, 3], [2, 5], [1, 2], [3, 5], [2, 3], [3, 4], [4, 5], [5, 6], [7, 8], [9, 10], [19, 20]];
  let best = fracs[0];
  for (const f of fracs) if (Math.abs(f[0] / f[1] - p) < Math.abs(best[0] / best[1] - p)) best = f;
  return `about ${best[0]} in ${best[1]}`;
}
export const partyName = (r) => (r.race_type === "independent" ? "Osborn (I)" : "Democrats");

/** Relative link to a page from the current page (race pages sit one folder deeper). */
export function link(path) {
  const depth = location.pathname.replace(/\/$/, "").split("/").filter(Boolean).length;
  const inRace = location.pathname.includes("/race/");
  return (inRace ? "../" : "./") + path.replace(/^\//, "");
}
export const raceHref = (id) => link(`race/${id}`);

// ---------- tooltip ----------
let tipEl;
export function tip() {
  if (!tipEl) {
    tipEl = document.createElement("div");
    tipEl.className = "wsu-tip";
    tipEl.setAttribute("role", "tooltip");
    document.body.appendChild(tipEl);
  }
  return {
    show(event, rows) {
      // rows: [[className, text], ...] -- always inserted as text, never HTML
      tipEl.replaceChildren(...rows.map(([cls, text]) => {
        const d = document.createElement("div");
        d.className = cls;
        d.textContent = text;
        return d;
      }));
      tipEl.style.opacity = 1;
      this.move(event);
    },
    move(event) {
      const pad = 14, w = tipEl.offsetWidth, h = tipEl.offsetHeight;
      let x = event.clientX + pad, y = event.clientY + pad;
      if (x + w > innerWidth - 8) x = event.clientX - w - pad;
      if (y + h > innerHeight - 8) y = event.clientY - h - pad;
      tipEl.style.left = `${x}px`;
      tipEl.style.top = `${y}px`;
    },
    hide() { tipEl.style.opacity = 0; }
  };
}

function raceTipRows(r) {
  const who = r.office === "HOUSE" ? `${r.state_name} ${r.district === 0 ? "at-large" : `District ${r.district}`}` : r.label;
  const rows = [["t-title", who]];
  if (r.race_type === "same_party") {
    rows.push(["t-sub", `Only ${r.race_note === "D" ? "Democrats" : "Republicans"} on the November ballot`]);
    return rows;
  }
  const d = r.race_type === "independent" ? `${r.dem_candidate ?? "Osborn"} (I)` : r.dem_candidate ? `${r.dem_candidate} (D)` : "Democrat";
  const rp = r.rep_candidate ? `${String(r.rep_candidate).split(";")[0]} (R)` : "Republican";
  rows.push(["t-sub", `${d} vs. ${rp}`]);
  rows.push(["t-val", r.p_dem >= 0.5 ? `${pct(r.p_dem)} ${r.race_type === "independent" ? "Osborn" : "D"}` : `${pct(1 - r.p_dem)} R`]);
  rows.push(["t-sub", `Forecast margin ${margin(r.margin_median)} · ${r.rating}`]);
  if (r.office === "HOUSE") rows.push(["t-sub", `2024: ${margin(r.pres24)} Trump/Harris${r.lines_changed ? " (new lines)" : ""}`]);
  return rows;
}

// ---------- House hex map ----------
export function hexMap(races, layout, {width = 960} = {}) {
  const t = tokens();
  const byKey = new Map(races.filter((r) => r.office === "HOUSE").map((r) => [`${r.state_po}-${r.district}`, r]));
  const hexes = layout.hexes;
  const x0 = d3.min(hexes, (h) => h.x) - 1, x1 = d3.max(hexes, (h) => h.x) + 1;
  const y0 = Math.min(d3.min(hexes, (h) => h.y) - 1, d3.min(layout.labels ?? [], (d) => d.y - 0.6) ?? Infinity), y1 = d3.max(hexes, (h) => h.y) + 1;
  const k = width / (x1 - x0);
  const height = (y1 - y0) * k;
  const R = k / Math.sqrt(3); // circumradius for unit-width pointy-top hexes
  const gap = Math.max(0.5, Math.min(1, R * 0.07)); // thin seam between tiles; states are separated by open space
  const hexPath = (cx, cy, r) =>
    d3.range(6).map((i) => {
      const a = (Math.PI / 180) * (60 * i - 90);
      return `${i ? "L" : "M"}${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`;
    }).join("") + "Z";
  const X = (x) => (x - x0) * k, Y = (y) => (y - y0) * k;
  const svg = d3.create("svg").attr("viewBox", [0, 0, width, height]).attr("width", width).attr("height", height)
    .attr("role", "img").attr("aria-label", "Hex map of House forecasts, one hexagon per district")
    .style("max-width", "100%").style("height", "auto");
  const t_ = tip();
  const g = svg.append("g");
  g.selectAll("path.hex").data(hexes).join("a")
    .attr("href", (h) => { const r = byKey.get(`${h.state}-${h.district}`); return r ? raceHref(r.race_id) : null; })
    .append("path").attr("class", "hex")
    .attr("d", (h) => hexPath(X(h.x), Y(h.y), R - gap)) // every tile identical
    .attr("fill", (h) => { const r = byKey.get(`${h.state}-${h.district}`); return r ? t[r.rating] : t.hair; })
    .attr("tabindex", 0)
    .on("pointerenter focus", function (event, h) {
      const r = byKey.get(`${h.state}-${h.district}`);
      d3.select(this).attr("stroke", t.ink).attr("stroke-width", 2);
      if (r) t_.show(event, raceTipRows(r));
    })
    .on("pointermove", (event) => t_.move(event))
    .on("pointerleave blur", function () { d3.select(this).attr("stroke", null); t_.hide(); });
  // State names sit in the open space above each state's island (the layout reserves room for them).
  const labels = layout.labels ?? [];
  svg.append("g").style("pointer-events", "none").selectAll("text").data(labels.filter((d) => R >= 9 || d.n >= 6)).join("text")
    .attr("x", (d) => X(d.x)).attr("y", (d) => Y(d.y))
    .attr("text-anchor", "middle").attr("dy", "0.36em")
    .attr("font-size", Math.max(8.5, Math.min(12.5, R * 0.72))).attr("font-weight", 650).attr("letter-spacing", "0.06em")
    .attr("fill", t["ink-2"])
    .text((d) => d.state);
  return svg.node();
}

// ---------- state map (Senate / Governors) ----------
export function stateMap(races, topo, states, {office, width = 960} = {}) {
  const t = tokens();
  const fipsToPo = Object.fromEntries(Object.entries(states.fips).map(([po, f]) => [f, po]));
  const byState = d3.group(races.filter((r) => r.office === office), (r) => r.state_po);
  const feats = topojson.feature(topo, topo.objects.states).features;
  const path = d3.geoPath();
  const height = (width * 610) / 975;
  const svg = d3.create("svg").attr("viewBox", [0, 0, 975, 610]).attr("width", width).attr("height", height)
    .attr("role", "img").attr("aria-label", `Map of ${office === "SEN" ? "Senate" : "governor"} forecasts by state`)
    .style("max-width", "100%").style("height", "auto");
  const t_ = tip();
  const fill = (po) => {
    const rs = byState.get(po);
    if (!rs) return t.surface; // no race: blank, so gray always means "toss-up"
    const main = rs.find((r) => !r.special) ?? rs[0];
    if (main.race_type === "independent") return t.ind;
    return t[main.rating];
  };
  svg.append("g").selectAll("a").data(feats).join("a")
    .attr("href", (f) => { const rs = byState.get(fipsToPo[f.id]); return rs ? raceHref((rs.find((r) => !r.special) ?? rs[0]).race_id) : null; })
    .append("path").attr("d", path)
    .attr("fill", (f) => fill(fipsToPo[f.id]))
    .attr("stroke", (f) => (byState.get(fipsToPo[f.id]) ? t.surface : t.axis))
    .attr("stroke-width", (f) => (byState.get(fipsToPo[f.id]) ? 1.2 : 0.8)).attr("stroke-linejoin", "round")
    .attr("tabindex", (f) => (byState.get(fipsToPo[f.id]) ? 0 : null))
    .on("pointerenter focus", function (event, f) {
      const rs = byState.get(fipsToPo[f.id]);
      if (!rs) return;
      d3.select(this).attr("stroke", t.ink).attr("stroke-width", 2).raise();
      t_.show(event, rs.flatMap((r, i) => (i ? [["t-sub", " "], ...raceTipRows(r)] : raceTipRows(r))));
    })
    .on("pointermove", (event) => t_.move(event))
    .on("pointerleave blur", function (event, f) {
      const has = byState.get(fipsToPo[f.id]);
      d3.select(this).attr("stroke", has ? t.surface : t.axis).attr("stroke-width", has ? 1.2 : 0.8);
      t_.hide();
    });
  // A special election in a state that ALSO has a regular race gets a small marker so the second
  // race isn't hidden. (In 2026, Florida's and Ohio's only Senate races are specials: no marker.)
  const specials = races.filter((r) => r.office === office && r.special
    && byState.get(r.state_po).some((x) => !x.special));
  for (const r of specials) {
    const f = feats.find((f) => fipsToPo[f.id] === r.state_po);
    if (!f) continue;
    const [cx, cy] = path.centroid(f);
    svg.append("a").attr("href", raceHref(r.race_id)).append("circle").attr("cx", cx + 14).attr("cy", cy + 10).attr("r", 7)
      .attr("fill", t[r.rating]).attr("stroke", t.surface).attr("stroke-width", 2)
      .on("pointerenter", (event) => t_.show(event, raceTipRows(r))).on("pointermove", (e) => t_.move(e)).on("pointerleave", () => t_.hide());
  }
  return svg.node();
}

// ---------- legend ----------
export function ratingLegend({independent = false, noRace = null} = {}) {
  const t = tokens();
  const el = document.createElement("div");
  el.className = "legend";
  const items = RATINGS.map((r) => [r, t[r]]);
  if (independent) items.push(["Independent", t.ind]);
  if (noRace) items.push([noRace, t.surface]);
  for (const [label, color] of items) {
    const s = document.createElement("span");
    const i = document.createElement("i");
    i.style.background = color;
    if (color === t.surface) i.style.boxShadow = `inset 0 0 0 1px ${t.axis}`;
    s.append(i, document.createTextNode(label));
    el.append(s);
  }
  return el;
}

export function ratingPill(rating) {
  const t = tokens();
  const s = document.createElement("span");
  s.className = "rating-pill";
  s.style.background = t[rating];
  s.style.color = inkOn(t[rating]);
  s.textContent = rating;
  return s;
}

// ---------- probability bar ----------
export function probBar(pD, {dLabel = "Democrats", rLabel = "Republicans", dColor, rColor} = {}) {
  const t = tokens();
  const wrap = document.createElement("div");
  const bar = document.createElement("div");
  bar.className = "prob-bar";
  const a = document.createElement("div"), b = document.createElement("div");
  a.style.background = dColor ?? t.dem; a.style.width = `${pD * 100}%`;
  b.style.background = rColor ?? t.rep; b.style.width = `${(1 - pD) * 100}%`;
  bar.append(a, b);
  const lg = document.createElement("div");
  lg.className = "prob-legend";
  const l = document.createElement("span"), r = document.createElement("span");
  l.append(Object.assign(document.createElement("b"), {textContent: pct(pD)}), ` ${dLabel}`);
  r.append(`${rLabel} `, Object.assign(document.createElement("b"), {textContent: pct(1 - pD)}));
  lg.append(l, r);
  wrap.append(bar, lg);
  return wrap;
}

// ---------- sortable, searchable race table ----------
/** Sort presets for race tables (shown as a "Sort" menu). */
export const RACE_SORTS = [
  {label: "Most competitive", value: (r) => (r.race_type === "same_party" ? 9 : Math.abs(r.p_dem - 0.5)), dir: 1},
  {label: "Most Democratic", value: (r) => r.p_dem, dir: -1},
  {label: "Most Republican", value: (r) => r.p_dem, dir: 1},
  {label: "State A–Z", value: (r) => `${r.state_name} ${String(r.district ?? 0).padStart(2, "0")}`, dir: 1}
];

export function raceTable(rows, columns, {search = true, filters = [], pageSize = 50, sort, sorts = null} = {}) {
  const root = document.createElement("div");
  const controls = document.createElement("div");
  controls.className = "table-controls";
  let q = "";
  const active = {};
  if (search) {
    const input = document.createElement("input");
    input.type = "search";
    input.placeholder = "Search candidates, states, districts";
    input.setAttribute("aria-label", "Search races");
    input.style.minWidth = "260px";
    input.addEventListener("input", () => { q = input.value.toLowerCase(); shown = pageSize; render(); });
    controls.append(input);
  }
  for (const f of filters) {
    const sel = document.createElement("select");
    sel.setAttribute("aria-label", f.label);
    for (const [v, text] of [["", f.label], ...f.options]) sel.append(new Option(text, v));
    sel.addEventListener("change", () => { active[f.key] = sel.value; shown = pageSize; render(); });
    controls.append(sel);
  }
  let preset = sorts ? sorts[0] : null;
  let sortSel = null;
  if (sorts) {
    sortSel = document.createElement("select");
    sortSel.setAttribute("aria-label", "Sort races");
    sorts.forEach((o, i) => sortSel.append(new Option(`Sort: ${o.label}`, String(i))));
    sortSel.append(new Option("Sort: by column", "col"));
    sortSel.lastChild.hidden = true;
    sortSel.addEventListener("change", () => {
      if (sortSel.value === "col") return;
      preset = sorts[+sortSel.value]; sortCol = null; shown = pageSize; render();
    });
    controls.append(sortSel);
  }
  const count = document.createElement("span");
  count.className = "count";
  controls.append(count);
  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  const table = document.createElement("table");
  table.className = "wsu-table";
  const thead = table.createTHead().insertRow();
  let sortCol = sorts ? null : sort?.key ?? null, sortDir = sort?.dir ?? 1;
  for (const c of columns) {
    const th = document.createElement("th");
    th.textContent = c.label;
    if (c.num) th.className = "num";
    if (c.sort) {
      th.dataset.sort = c.key;
      th.addEventListener("click", () => {
        sortDir = sortCol === c.key ? -sortDir : c.defaultDir ?? 1;
        sortCol = c.key;
        preset = null;
        if (sortSel) sortSel.value = "col";
        render();
      });
    }
    thead.append(th);
  }
  const tbody = table.createTBody();
  wrap.append(table);
  const more = document.createElement("button");
  more.textContent = "Show more";
  Object.assign(more.style, {margin: "14px 0", font: "600 14px var(--sans)", padding: "8px 16px", borderRadius: "8px",
    border: "1px solid var(--axis)", background: "var(--card)", color: "var(--ink)", cursor: "pointer"});
  let shown = pageSize;
  more.addEventListener("click", () => { shown += pageSize; render(); });
  function render() {
    let data = rows.filter((r) => (!q || (r._search ?? "").includes(q)) &&
      filters.every((f) => !active[f.key] || f.test(r, active[f.key])));
    if (preset) {
      data = [...data].sort((a, b) => preset.dir * d3.ascending(preset.value(a), preset.value(b))
        || d3.ascending(a.state_name, b.state_name) || d3.ascending(a.district, b.district));
    } else if (sortCol) {
      const col = columns.find((c) => c.key === sortCol);
      const val = col.sortValue ?? ((r) => r[col.key]);
      data = [...data].sort((a, b) => sortDir * d3.ascending(val(a), val(b)));
    }
    for (const th of thead.children) {
      th.classList.toggle("sorted-asc", th.dataset.sort === sortCol && sortDir === 1);
      th.classList.toggle("sorted-desc", th.dataset.sort === sortCol && sortDir === -1);
    }
    tbody.replaceChildren(...data.slice(0, shown).map((r) => {
      const tr = document.createElement("tr");
      for (const c of columns) {
        const td = document.createElement("td");
        if (c.num) td.className = "num";
        const v = c.render ? c.render(r) : r[c.key];
        if (v instanceof Node) td.append(v); else td.textContent = v ?? "–";
        tr.append(td);
      }
      return tr;
    }));
    count.textContent = `${data.length} race${data.length === 1 ? "" : "s"}`;
    more.style.display = data.length > shown ? "" : "none";
  }
  render();
  root.append(controls, wrap, more);
  return root;
}

export function raceLink(r, text) {
  const a = document.createElement("a");
  a.href = raceHref(r.race_id);
  a.textContent = text ?? r.label;
  return a;
}

export function miniBar(p) {
  const s = document.createElement("span");
  s.className = "mini-bar";
  s.title = `${pct(p)} chance of a Democratic win`;
  const b = document.createElement("b");
  b.style.width = `${p * 100}%`;
  s.append(b);
  return s;
}

export function favoriteText(r) {
  if (r.race_type === "same_party") return r.race_note === "D" ? "D (unopposed)" : "R (unopposed)";
  const who = r.race_type === "independent" ? "Osborn" : "D";
  return r.p_dem >= 0.5 ? `${pct(r.p_dem)} ${who}` : `${pct(1 - r.p_dem)} R`;
}

export function withSearch(races) {
  return races.map((r) => ({...r, _search: [r.label, r.state_name, r.state_po, r.dem_candidate, r.rep_candidate, r.incumbent]
    .filter(Boolean).join(" ").toLowerCase()}));
}
