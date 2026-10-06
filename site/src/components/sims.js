// The forecast's simulated elections, in the browser: the What if page and election night keep the simulations
// that match a scenario (or weight them) and recount. The file comes from export_site_data.sims_export():
// 10,000 simulations, each with the national House vote, how much of the national swing came from turnout,
// both chambers' totals, the number of Democratic governors, and the winner of every race that isn't a lock.

export function loadSims(buffer, meta) {
  const n = meta.n;
  const dv = new DataView(buffer);
  let o = 0;
  const E = new Float32Array(n), house = new Uint16Array(n), a = new Float32Array(n), sen = new Uint8Array(n), gov = new Uint8Array(n);
  for (let s = 0; s < n; s++) E[s] = dv.getInt16(o + 2 * s, true) / 100;
  o += 2 * n;
  for (let s = 0; s < n; s++) house[s] = dv.getUint16(o + 2 * s, true);
  o += 2 * n;
  for (let s = 0; s < n; s++) a[s] = dv.getUint8(o + s) / 255;
  o += n;
  sen.set(new Uint8Array(buffer, o, n)); o += n;
  gov.set(new Uint8Array(buffer, o, n)); o += n;
  const bits = new Uint8Array(buffer, o);
  const index = new Map(meta.races.map((id, i) => [id, i]));
  const rb = meta.row_bytes;
  // did the Democratic side (or the independent) win race i in simulation s?
  const won = (i, s) => (bits[i * rb + (s >> 3)] >> (s & 7)) & 1;
  return {n, E, a, house, sen, gov, index, won, races: meta.races};
}

/** Weights for a scenario: picks = Map(race_id -> "D" | "R"), env = {target, bw} (national House vote), how = "turnout" | "persuasion" | null. */
export function weigh(sims, {picks = new Map(), env = null, how = null} = {}) {
  const w = new Float64Array(sims.n).fill(1);
  const conds = [...picks].map(([id, side]) => [sims.index.get(id), side === "D" ? 1 : 0]).filter(([i]) => i != null);
  for (let s = 0; s < sims.n; s++) {
    for (const [i, v] of conds) if (sims.won(i, s) !== v) { w[s] = 0; break; }
    if (!w[s]) continue;
    if (env) w[s] *= Math.exp(-0.5 * ((sims.E[s] - env.target) / env.bw) ** 2);
    if (how === "turnout" && sims.a[s] < 2 / 3) w[s] = 0;
    if (how === "persuasion" && sims.a[s] >= 0.5) w[s] = 0;
  }
  return w;
}

/** Chamber odds, seat medians and each stored race's chance under weights w. */
export function summarize(sims, w) {
  let tot = 0, tot2 = 0, sD = 0, hD = 0, envSum = 0;
  for (let s = 0; s < sims.n; s++) {
    const x = w[s];
    if (!x) continue;
    tot += x; tot2 += x * x;
    if (sims.sen[s] >= 51) sD += x;
    if (sims.house[s] >= 218) hD += x;
    envSum += x * sims.E[s];
  }
  if (!tot) return {ess: 0};
  const wMedian = (arr) => {
    const idx = Array.from(arr.keys()).filter((s) => w[s]).sort((p, q) => arr[p] - arr[q]);
    let c = 0;
    for (const s of idx) { c += w[s]; if (c >= tot / 2) return arr[s]; }
    return arr[idx[idx.length - 1]];
  };
  const p = new Float64Array(sims.races.length);
  for (let i = 0; i < sims.races.length; i++) {
    let x = 0;
    for (let s = 0; s < sims.n; s++) if (w[s] && sims.won(i, s)) x += w[s];
    p[i] = x / tot;
  }
  return {
    ess: (tot * tot) / tot2,                    // effective number of simulations behind the numbers
    pSen: sD / tot, pHouse: hD / tot, env: envSum / tot,
    senMedian: wMedian(sims.sen), houseMedian: wMedian(sims.house), govMedian: wMedian(sims.gov),
    p: Object.fromEntries(sims.races.map((id, i) => [id, p[i]]))
  };
}

/** National House margin if Democratic turnout runs x (e.g. -0.05) relative to Republican turnout, from a baseline margin. */
export function turnoutToMargin(x, base) {
  const s0 = (base / 100 + 1) / 2;
  const s = (s0 * (1 + x)) / (s0 * (1 + x) + (1 - s0));
  return (2 * s - 1) * 100;
}
