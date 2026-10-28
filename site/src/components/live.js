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
// The first polls close at 6 p.m. ET (23:00 UTC): a count before then is civicAPI testing its feed, which its
// search doesn't flag, so the page doesn't ask until then, nor while our poller reports test data (civic_test).
const NIGHT_START = Date.parse("2026-11-03T23:00:00Z"), NIGHT_END = Date.parse("2026-11-06T05:00:00Z");

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
    // same-party races (two Democrats in a California top-two) are decided before the night: not in the tally
    const contested = new Set(races.filter((r) => r.race_type !== "same_party").map((r) => r.race_id));
    const emit = () => {
      if (!published) return;
      const rehearsal = ["simulation", "practice"].includes(published.mode);
      const fresh = direct && Date.now() - directAt < 4 * 60_000 && !rehearsal && !published.civic_test;
      const races_ = {...(published.races ?? {})};
      if (fresh) {
        for (const [rid, v] of Object.entries(direct)) {
          const old = races_[rid], prev = last[rid];
          // never step backward: a count lower than one already shown keeps the higher one
          const tot = (o) => (o ? (o.d ?? 0) + (o.r ?? 0) : -1);
          const best = [v, old, prev].reduce((a, b) => (tot(b) > tot(a) ? b : a));
          // civicAPI's search has no county breakdown: keep the counties from our published copy
          races_[rid] = {...best, counties: best.counties ?? old?.counties, called: v.called ?? old?.called ?? null};
        }
      }
      last = races_;
      const vals = Object.entries(races_).filter(([rid]) => contested.has(rid)).map(([, v]) => v);
      notify({...published, races: races_, mode: fresh && published.mode === "waiting" ? "live" : published.mode,
        source: fresh ? "direct" : "published", asof: fresh ? new Date(directAt).toISOString() : published.asof,
        called: vals.filter((v) => v.called).length, reporting: vals.filter((v) => (v.d ?? 0) + (v.r ?? 0) > 0).length,
        total: published.total ?? contested.size});
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

/** races: races.json rows; m: live_model.json; L: live races {rid: {pct, d, r, margin, called}}.
 *  partial (optional): {rid: raceMath(...)} for races part-way counted. Each one's own count then moves its odds:
 *  how far its counted areas run from our forecast (against the county benchmarks where we have them, else the
 *  count itself) is weighed against the night's shared shift, trusting the count more as more of it is in, and the
 *  uncounted vote is filled in from the benchmarks of the places still out. Returns each race's chance (p) and
 *  where we now expect its margin to finish (mFinal, the average over the simulated nights). Senate and House
 *  control count only those chambers; governors get their own odds. */
export function liveOdds(races, m, L, {n = 4000, partial = null} = {}) {
  const contested = races.filter((r) => r.race_type !== "same_party");
  const states = [...new Set(contested.map((r) => r.state_po))].sort(), regions = [...new Set(Object.values(m.region))].sort();
  const K = 1 + regions.length + states.length;
  const col = (r) => [0, 1 + Math.max(0, regions.indexOf(m.region[r.state_po])), 1 + regions.length + states.indexOf(r.state_po)];
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
    const p = {r, c, ind, known, counted, mean: r.margin_median, own: own(r), sd: Math.sqrt(own(r)), cur: x?.margin ?? null};
    // part-way counted: what the count says about this race's own miss (g), and how much to trust it (sg, points
    // of noise). The weights come from replaying 2018-2024 Senate and governor counts county by county against our
    // backtest forecasts (research/live_odds/calibrate.py), chosen to hold up across early-ballot skews of 3-9 points.
    const q = partial?.[r.race_id];
    if (known == null && counted == null && q && q.counted && q.pct >= 1) {
      const f = Math.min(q.pct, 95) / 100;
      if (q.gap != null && q.uncounted > 0) {
        Object.assign(p, {g: q.gap, sg: 6 + 2 * (1 - f), C: q.counted, U: q.uncounted, mc: (100 * q.lead) / q.counted, rem: q.benchRem});
      } else {
        Object.assign(p, {g: x.margin - r.margin_median, sg: 0.5 + 6 * (1 - f)});
      }
    }
    return p;
  });
  const pRace = new Float64Array(plan.length), mSum = new Float64Array(plan.length);
  for (let s = 0; s < n; s++) {
    for (let i = 0; i < K; i++) z[i] = gauss();
    for (let i = 0; i < K; i++) { let v = mu[i]; for (let k = 0; k <= i; k++) v += C[i][k] * z[k]; th[i] = v; }
    let sd = 0, hd = 0;
    plan.forEach((p, i) => {
      let final;
      if (p.known != null) final = p.cur ?? p.known;
      else if (p.counted != null) final = p.counted + gauss() * 0.5;
      else {
        const shared = th[p.c[0]] + th[p.c[1]] + th[p.c[2]];
        let miss = shared + p.sd * gauss();
        if (p.g != null) {  // this race's own count, weighed against the night's shared shift
          const v = 1 / (1 / p.own + 1 / p.sg ** 2);
          miss = v * (shared / p.own + p.g / p.sg ** 2) + Math.sqrt(v) * gauss();
        }
        final = (p.U ? (p.C * p.mc + p.U * (p.rem + miss)) / (p.C + p.U) : p.mean + miss) + gauss() * 0.5;
      }
      const won = p.known != null ? p.known > 0 : final > 0;
      mSum[i] += final;
      if (won) pRace[i]++;
      if (won && !p.ind) { if (p.r.office === "SEN") sd++; else if (p.r.office === "HOUSE") hd++; }
    });
    if (m.senate_base + sd >= 51) senD++;
    if (houseFixedD + hd >= 218) houseD++;
  }
  return {pSen: senD / n, pHouse: houseD / n, used, shift: mu[0],
    p: Object.fromEntries(plan.map((p, i) => [p.r.race_id, pRace[i] / n])),
    mFinal: Object.fromEntries(plan.map((p, i) => [p.r.race_id, mSum[i] / n]))};
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

// ---------------------------------------------------------------------------------------------------------
// The results page's drill-in: what's left to count, what each side needs, turnout against what we expected, and
// how the counted areas compare with our forecast. Display only; nothing here feeds the forecast.

/** One race's civicAPI record, with each county's count: {x, counties: Map(countyKey -> {d, r, pct})}. */
export async function fetchRace(race, civicId) {
  const res = await fetch(`https://civicapi.org/api/v2/race/${civicId}`);
  if (!res.ok) throw new Error(res.status);
  const j = await res.json(), x = j.data ?? j;
  const top = race.race_type === "rcv_bloc" ? null : civicSides(race, x.candidates);
  const counties = new Map();
  for (const [k, v] of Object.entries(x.region_results ?? {})) {
    const s = civicSides(race, v.candidates);
    counties.set(countyKey(v.name ?? k), {pct: v.percent_reporting ?? 0, d: s.d, r: s.r});
  }
  return {x: top && {pct: x.percent_reporting ?? 0, d: top.d, r: top.r, called: top.called,
    margin: top.d + top.r ? (100 * (top.d - top.r)) / (top.d + top.r) : null}, counties};
}

/** Counties from our published copy (the rehearsal writes them as {key: [d, r, pct]}), as fetchRace's Map. */
export function countiesOf(x) {
  if (!x?.counties) return null;
  return new Map(Object.entries(x.counties).map(([k, [d, r, pct]]) => [k, {d, r, pct}]));
}

/** What share of the votes left each side needs to finish ahead: {D, R} (0-1; <= 0 means already safe, > 1 means
 *  out of reach), for `left` votes still to count with the D side ahead by `lead` (negative: behind). */
export function needs(left, lead) {
  if (!(left > 0)) return null;
  return {D: (left - lead) / (2 * left), R: (left + lead) / (2 * left)};
}

/** Everything the drill-in shows for one race. r: races.json row; x: its live count {pct, d, r, margin};
 *  bench: its county benchmarks [[name, fips, benchmark margin, 2024 margin, share of the state's vote]];
 *  counties: Map(countyKey -> {d, r, pct}) or null. */
export function raceMath(r, x, bench, counties) {
  const counted = (x?.d ?? 0) + (x?.r ?? 0), pct = x?.pct ?? 0;
  const expected = r.expected_votes ?? null;              // two-party votes we expect (2024 vote x midterm drop-off)
  const lead = (x?.d ?? 0) - (x?.r ?? 0);
  const out = {counted, pct, expected, lead, margin: x?.margin ?? null};
  if (counted && pct >= 5 && pct < 100) {
    out.projected = counted / (pct / 100);                 // where turnout ends if the count's own estimate holds
    out.leftCount = out.projected - counted;
    out.needCount = needs(out.leftCount, lead);
  } else if (counted && pct >= 100) out.projected = counted;
  if (expected && counted && counted < expected && pct < 100) {
    out.leftOurs = expected - counted;                     // if turnout ends where we expected
    out.needOurs = needs(out.leftOurs, lead);
  }
  if (expected && out.projected && pct >= 10) out.turnout = out.projected / expected - 1;
  // counted areas against our forecast: the margin our county benchmarks expect from the counties counted so far
  if (bench && counties && counties.size) {
    let w = 0, wb = 0, projT = 0, expT = 0;
    const lean = {D: [0, 0], R: [0, 0]};
    out.countyRows = bench.map(([name, fips, b, p24, share]) => {
      const c = counties.get(countyKey(name));
      const n = c ? c.d + c.r : 0;
      const row = {key: String(fips), label: name.replace(/ (County|Parish|Borough|Census Area|Municipality)$/, ""), name, share, bench: b,
        pct: c?.pct ?? 0, d: c?.d ?? 0, r: c?.r ?? 0, counted: n};
      if (n) {
        row.margin = (100 * (c.d - c.r)) / n;
        row.gap = row.margin - b;
        w += n; wb += n * b;
        if (expected && c.pct >= 10) {
          const proj = n / (Math.min(c.pct, 100) / 100), exp = share * expected;
          row.turnout = proj / exp - 1;
          projT += proj; expT += exp;
          const side = b >= 0 ? "D" : "R";
          lean[side][0] += proj; lean[side][1] += exp;
        }
      }
      return row;
    });
    if (w) { out.expectedNow = wb / w; out.gap = (100 * lead) / counted - out.expectedNow; out.benchCounted = w; }
    // the vote still out, county by county (from each county's own share counted, or our expectation where it
    // hasn't reported), and the margin our benchmarks give it
    if (expected) {
      let u = 0, ub = 0;
      for (const row of out.countyRows) {
        const left = row.counted && row.pct >= 5 ? (row.counted * (100 - Math.min(row.pct, 100))) / Math.min(row.pct, 100) : Math.max(row.share * expected - row.counted, 0);
        u += left; ub += left * row.bench;
      }
      if (u > 0) { out.uncounted = u; out.benchRem = ub / u; }
    }
    if (expT) out.turnoutCounted = projT / expT - 1;
    out.turnoutLean = Object.fromEntries(Object.entries(lean).filter(([, [p, e]]) => e > 0).map(([k, [p, e]]) => [k, p / e - 1]));
  }
  return out;
}

/** The night so far across every Senate and governor race with county counts: how the counted counties compare
 *  with our benchmarks, and turnout against what we expected, overall and in Democratic- and Republican-leaning
 *  counties. One race per state for turnout (a state's Senate and governor races share their voters). */
export function nightRead(list) {
  let w = 0, wg = 0;
  const T = {all: [0, 0], D: [0, 0], R: [0, 0]};
  const seen = new Set();
  for (const {r, m} of list) {
    if (!m?.countyRows || !m.benchCounted) continue;
    w += m.benchCounted; wg += m.benchCounted * m.gap;
    if (seen.has(r.state_po)) continue;
    seen.add(r.state_po);
    for (const c of m.countyRows) {
      if (c.turnout == null) continue;
      const proj = (c.turnout + 1) * c.share * r.expected_votes, exp = c.share * r.expected_votes;
      for (const k of ["all", c.bench >= 0 ? "D" : "R"]) { T[k][0] += proj; T[k][1] += exp; }
    }
  }
  if (!w) return null;
  const rate = ([p, e]) => (e ? p / e - 1 : null);
  return {gap: wg / w, votes: w, turnout: rate(T.all), turnoutD: rate(T.D), turnoutR: rate(T.R), states: seen.size};
}
