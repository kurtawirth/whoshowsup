// Election night in the browser: results straight from civicAPI (with our own published copy as the fallback),
// and live odds for the House and Senate that update as races finish counting.

// ---------------------------------------------------------------------------------------------------------
// Results. Two requests cover every race we forecast: civicAPI's "General" races (House, most Senate) and its
// "Statewide" races (governors, one Senate special). Every reader asks for exactly these two addresses, so
// civicAPI answers nearly all of them from its 15-second cache; the page asks once a minute, only while it's
// visible, a little later or earlier at random so readers don't arrive in lockstep, and backs off if civicAPI
// is slow or refuses. Whenever civicAPI can't be reached (or a race needs more candidates than its search lists,
// like Alaska's top-four races), the page uses the copy our own poller publishes every few minutes.
const API = "https://civicapi.org/api/v2/race/search?country=US&startDate=2026-11-03&endDate=2026-11-03&limit=50000&election_type=";
const NIGHT_START = Date.parse("2026-11-03T22:30:00Z"), NIGHT_END = Date.parse("2026-11-06T05:00:00Z");

/** Votes for our forecast's D side and R side, and the winner if called (port of core/civic_results._side_votes). */
export function civicSides(r, cands) {
  let indSide = null, indLast = "";
  if (r.race_type === "independent") {
    indSide = r.rep_candidate ? "D" : "R";
    indLast = String(r.race_note ?? "").toLowerCase().trim().split(/\s+/).pop();
  }
  let d = 0, rep = 0, called = null;
  for (const c of cands ?? []) {
    const party = String(c.party ?? ""), name = String(c.name ?? "").toLowerCase();
    let side = party.startsWith("Democrat") ? "D" : party.startsWith("Republican") ? "R" : null;
    if (indSide) side = name.includes(indLast) ? indSide : side === indSide ? null : side;
    const votes = Math.round(Number(c.votes) || 0);
    if (side === "D") d += votes; else if (side === "R") rep += votes;
    if (c.winner && side) called = side;
  }
  return {d, r: rep, called};
}

/** Turn civicAPI search results into our live format: {race_id: {pct, d, r, margin, called}}. */
export function fromCivic(list, races, civic) {
  const byCivic = new Map(Object.entries(civic).map(([rid, cid]) => [cid, rid]));
  const byId = new Map(races.map((r) => [r.race_id, r]));
  const out = {};
  for (const x of list) {
    const rid = byCivic.get(x.id);
    const r = rid && byId.get(rid);
    if (!r || r.race_type === "rcv_bloc") continue;  // Alaska's bloc races need every candidate: the poller has them
    const {d, r: rv, called} = civicSides(r, x.candidates);
    out[rid] = {pct: x.percent_reporting ?? 0, d, r: rv, margin: d + rv ? Math.round((10000 * (d - rv)) / (d + rv)) / 100 : null, called};
  }
  return out;
}

/** A live results stream for the Election night page: our published file, upgraded to civicAPI's direct feed
 *  during the night (or with ?direct in the address, for testing). Yields {mode, asof, races, source, ...}. */
export function liveStream(liveFile, races, civic, {Generators, force = false}) {
  return Generators.observe((notify) => {
    let published = null, direct = null, directAt = 0, last = {};
    let delay = 60_000, timer = null, stopped = false;
    const emit = () => {
      if (!published) return;
      const rehearsal = ["simulation", "practice"].includes(published.mode);
      const fresh = direct && Date.now() - directAt < 4 * 60_000 && !rehearsal;
      const races_ = {...(published.races ?? {})};
      if (fresh) {
        for (const [rid, v] of Object.entries(direct)) {
          const old = races_[rid], prev = last[rid];
          // never step backward: a count lower than one already shown keeps the higher one
          const tot = (o) => (o ? (o.d ?? 0) + (o.r ?? 0) : -1);
          const best = [v, old, prev].reduce((a, b) => (tot(b) > tot(a) ? b : a));
          races_[rid] = {...best, called: v.called ?? old?.called ?? null};
        }
      }
      last = races_;
      const vals = Object.values(races_);
      notify({...published, races: races_, mode: fresh && published.mode === "waiting" ? "live" : published.mode,
        source: fresh ? "direct" : "published", asof: fresh ? new Date(directAt).toISOString() : published.asof,
        called: vals.filter((v) => v.called).length, reporting: vals.filter((v) => (v.d ?? 0) + (v.r ?? 0) > 0).length,
        total: published.total ?? races.filter((r) => r.race_type !== "same_party").length});
    };
    // our published copy: re-read whenever the page's own HTML points at a newer one
    let href = liveFile.href;
    liveFile.json().then((j) => { published = j; emit(); });
    async function checkPublished() {
      try {
        const page = await (await fetch(location.pathname, {cache: "no-store"})).text();
        const m = page.match(/_file\/data\/live\.[0-9a-f]+\.json/);
        if (!m) return;
        const url = new URL(m[0], new URL("./", location.href)).href;
        if (url !== new URL(href, location.href).href) { href = url; published = await (await fetch(url)).json(); emit(); }
      } catch { /* offline or mid-deploy: next time */ }
    }
    async function checkDirect() {
      const now = Date.now();
      if (!force && (now < NIGHT_START || now > NIGHT_END)) return;
      try {
        const got = await Promise.all(["General", "Statewide"].map(async (t) => {
          const res = await fetch(API + t, {mode: "cors"});
          if (!res.ok) throw new Error(res.status);
          return (await res.json()).races ?? [];
        }));
        direct = fromCivic(got.flat(), races, civic);
        directAt = Date.now();
        delay = 60_000;
        emit();
      } catch {
        delay = Math.min(delay * 2, 10 * 60_000);  // civicAPI slow or refusing: back off, lean on our copy
      }
    }
    async function tick() {
      if (stopped) return;
      if (document.visibilityState === "visible") await Promise.all([checkDirect(), checkPublished()]);
      timer = setTimeout(tick, delay + Math.random() * 15_000);
    }
    timer = setTimeout(tick, Math.random() * 5_000);
    const vis = () => { if (document.visibilityState === "visible") { clearTimeout(timer); tick(); } };
    document.addEventListener("visibilitychange", vis);
    return () => { stopped = true; clearTimeout(timer); document.removeEventListener("visibilitychange", vis); };
  });
}

/** What's left in a race being counted: the votes still out (estimated from the share counted so far; civicAPI's
 *  "reporting" share, so approximate), and what share of them the trailing side needs. null before votes or once done. */
export function votesLeft(x) {
  const counted = (x?.d ?? 0) + (x?.r ?? 0), pct = x?.pct ?? 0;
  if (!counted || pct < 5 || pct >= 100) return null;
  const left = Math.round((counted * (100 - pct)) / pct), lead = Math.abs(x.d - x.r);
  return {left, lead, leader: x.d >= x.r ? "D" : "R", locked: lead > left, need: left ? (left + lead) / (2 * left) : null};
}

// ---------------------------------------------------------------------------------------------------------
// Live odds. Our forecast's error has shared parts (national, regional, state) and a part that's each race's
// own (race_model: national environment, REGION_SHOCK_SD, STATE_SHOCK_SD). Races that have finished counting
// (95%+ in) tell us how far the night is running from the forecast in each of those shared parts; we estimate
// them (a Bayesian update), move every race still out by them, and rerun the rest of the night thousands of
// times. Called races count for their winner. Partial counts are not used: early votes skew by ballot type.

function cholesky(A) {
  const n = A.length, L = A.map(() => new Float64Array(n));
  for (let i = 0; i < n; i++) for (let j = 0; j <= i; j++) {
    let s = A[i][j];
    for (let k = 0; k < j; k++) s -= L[i][k] * L[j][k];
    L[i][j] = i === j ? Math.sqrt(Math.max(s, 1e-12)) : s / L[j][j];
  }
  return L;
}
function invertSPD(A) {  // via Cholesky
  const n = A.length, L = cholesky(A), inv = A.map(() => new Float64Array(n));
  for (let c = 0; c < n; c++) {
    const y = new Float64Array(n);
    for (let i = 0; i < n; i++) { let s = i === c ? 1 : 0; for (let k = 0; k < i; k++) s -= L[i][k] * y[k]; y[i] = s / L[i][i]; }
    for (let i = n - 1; i >= 0; i--) { let s = y[i]; for (let k = i + 1; k < n; k++) s -= L[k][i] * inv[k][c]; inv[i][c] = s / L[i][i]; }
  }
  return inv;
}
let spare = null;
function gauss() {
  if (spare != null) { const s = spare; spare = null; return s; }
  let u, v, q;
  do { u = Math.random() * 2 - 1; v = Math.random() * 2 - 1; q = u * u + v * v; } while (q >= 1 || q === 0);
  const f = Math.sqrt((-2 * Math.log(q)) / q);
  spare = v * f;
  return u * f;
}

/** races: races.json rows; m: live_model.json; L: live races {rid: {pct, d, r, margin, called}}. */
export function liveOdds(races, m, L, {n = 4000} = {}) {
  const contested = races.filter((r) => r.race_type !== "same_party" && (r.office === "SEN" || r.office === "HOUSE"));
  const states = [...new Set(contested.map((r) => r.state_po))].sort(), regions = [...new Set(Object.values(m.region))].sort();
  const K = 1 + regions.length + states.length;
  const col = (r) => [0, 1 + regions.indexOf(m.region[r.state_po]), 1 + regions.length + states.indexOf(r.state_po)];
  const prior = [m.env_sd ** 2, ...regions.map(() => m.region_sd ** 2), ...states.map(() => m.state_sd ** 2)];
  const sdTot = (r) => Math.max((r.margin_p90 - r.margin_p10) / 2.563, 2.5);
  const own = (r) => Math.max(sdTot(r) ** 2 - m.env_sd ** 2 - m.region_sd ** 2 - m.state_sd ** 2, 4);
  // observations: races at least 95% counted
  const P = prior.map((v, i) => { const row = new Float64Array(K); row[i] = 1 / v; return row; });
  const b = new Float64Array(K);
  let used = 0;
  for (const r of contested) {
    const x = L[r.race_id];
    if (!x || x.margin == null || (x.pct ?? 0) < 95) continue;
    const e = x.margin - r.margin_median, w = 1 / own(r), c = col(r);
    for (const i of c) { b[i] += w * e; for (const j of c) P[i][j] += w; }
    used++;
  }
  const S = invertSPD(P);
  const mu = S.map((row) => row.reduce((s, v, j) => s + v * b[j], 0));
  const C = cholesky(S);
  // fixed seats
  const houseFixedD = races.filter((r) => r.office === "HOUSE" && r.race_type === "same_party" && r.race_note === "D").length;
  let senD = 0, houseD = 0;
  const z = new Float64Array(K), th = new Float64Array(K);
  const plan = contested.map((r) => {
    const x = L[r.race_id], c = col(r);
    const ind = r.race_type === "independent" && Boolean(r.rep_candidate);
    const known = x?.called ? (x.called === "D" ? 1 : -1) : null;
    const counted = x && x.margin != null && (x.pct ?? 0) >= 95 ? x.margin : null;
    return {r, c, ind, known, counted, mean: r.margin_median, sd: Math.sqrt(own(r))};
  });
  const pRace = new Float64Array(plan.length);
  for (let s = 0; s < n; s++) {
    for (let i = 0; i < K; i++) z[i] = gauss();
    for (let i = 0; i < K; i++) { let v = mu[i]; for (let k = 0; k <= i; k++) v += C[i][k] * z[k]; th[i] = v; }
    let sd = 0, hd = 0;
    plan.forEach((p, i) => {
      let won;
      if (p.known != null) won = p.known > 0;
      else if (p.counted != null) won = p.counted + gauss() * 0.5 > 0;
      else won = p.mean + th[p.c[0]] + th[p.c[1]] + th[p.c[2]] + p.sd * gauss() > 0;
      if (won) pRace[i]++;
      if (won && !p.ind) { if (p.r.office === "SEN") sd++; else hd++; }
    });
    if (m.senate_base + sd >= 51) senD++;
    if (houseFixedD + hd >= 218) houseD++;
  }
  return {pSen: senD / n, pHouse: houseD / n, used, shift: mu[0],
    p: Object.fromEntries(plan.map((p, i) => [p.r.race_id, pRace[i] / n]))};
}

// ---------------------------------------------------------------------------------------------------------
// One race on election night (race pages): civicAPI's full race record, every minute while the page is visible
// (its 15-second cache shared by every reader), with each county's count; nothing before the night unless forced.
// county names, compared without accents, punctuation, spaces or "County"/"Parish" (LaSalle = La Salle Parish);
// civicAPI still calls South Dakota's Oglala Lakota County by its old name, Shannon
const COUNTY_ALIAS = {shannon: "oglalalakota"};
export const countyKey = (s) => {
  const k = String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/\b(county|parish|borough|census area|municipality)\b/g, "").replace(/[^a-z0-9]/g, "");
  return COUNTY_ALIAS[k] ?? k;
};

export function raceLive(race, civicId, {Generators, force = false}) {
  return Generators.observe((notify) => {
    let timer = null, stopped = false, delay = 60_000;
    notify(null);
    async function tick() {
      if (stopped) return;
      const now = Date.now();
      if (civicId && (force || (now >= NIGHT_START && now <= NIGHT_END)) && document.visibilityState === "visible") {
        try {
          const res = await fetch(`https://civicapi.org/api/v2/race/${civicId}`);
          if (!res.ok) throw new Error(res.status);
          const j = await res.json(), x = j.data ?? j;
          const top = race.race_type === "rcv_bloc" ? null : civicSides(race, x.candidates);
          const counties = new Map();
          for (const [k, v] of Object.entries(x.region_results ?? {})) {
            const s = civicSides(race, v.candidates);
            counties.set(countyKey(v.name ?? k), {pct: v.percent_reporting ?? 0, d: s.d, r: s.r});
          }
          notify({x: top && {pct: x.percent_reporting ?? 0, d: top.d, r: top.r, called: top.called,
            margin: top.d + top.r ? (100 * (top.d - top.r)) / (top.d + top.r) : null}, counties, at: Date.now()});
          delay = 60_000;
        } catch { delay = Math.min(delay * 2, 10 * 60_000); }
      }
      timer = setTimeout(tick, delay + Math.random() * 15_000);
    }
    tick();
    const vis = () => { if (document.visibilityState === "visible") { clearTimeout(timer); tick(); } };
    document.addEventListener("visibilitychange", vis);
    return () => { stopped = true; clearTimeout(timer); document.removeEventListener("visibilitychange", vis); };
  });
}
