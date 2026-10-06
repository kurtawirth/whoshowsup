// Preview images for shared race links: one 1200x630 card per race (dist/share/race/<race_id>.png) with the
// matchup and today's odds, in the site's own fonts and colors. Run after the build:
//
//   node share-cards.js            (CHROME_PATH=... to pick the browser)
//
// The deploy workflow runs it on GitHub's build machine, so the ~500 images are made fresh with every update and
// never committed. It draws each card as a small web page in a headless Chrome/Edge (driven over the DevTools
// protocol, with Node's built-in WebSocket) and screenshots it. Any card it can't make gets a copy of the site-wide
// share.png instead, so a race link always has a preview.
import {spawn} from "node:child_process";
import {copyFileSync, existsSync, mkdirSync, rmSync} from "node:fs";
import {writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {races, top, raceFacts, esc} from "./seo.js";

const OUT = "dist/share/race";
const FALLBACK = "dist/share.png";
const BROWSERS = [process.env.CHROME_PATH, "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium-browser",
  "/usr/bin/chromium", "C:/Program Files/Google/Chrome/Application/chrome.exe", "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"];
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const pctText = (p) => (p >= 0.995 ? ">99%" : p <= 0.005 ? "<1%" : `${Math.round(p * 100)}%`);
// both sides of a race, adding up to 100 (82.5% would otherwise show as 83% and 18%): the leader is rounded and
// the other side gets the rest, the same rule as the race pages (components/wsu.js pctPair)
const pctPair = (pD) => {
  const lead = Math.max(pD, 1 - pD);
  if (lead >= 0.995) return pD >= 0.5 ? [">99%", "<1%"] : ["<1%", ">99%"];
  const L = Math.round(lead * 100), other = `${100 - L}%`;
  return pD >= 0.5 ? [`${L}%`, other] : [other, `${L}%`];
};
const last = (s) => String(s ?? "").trim().split(/\s+/).filter((w) => !/^(Jr\.?|Sr\.?|I{2,3})$/.test(w)).pop();
const day = new Date(`${top.forecast_date}T12:00:00`).toLocaleDateString("en-US", {month: "short", day: "numeric"});
const lean = (m, d, r) => (Math.abs(m) < 0.05 ? "even" : m > 0 ? `${d} +${m.toFixed(1)}` : `${r} +${(-m).toFixed(1)}`);
const COLOR = {D: "#2a78d6", R: "#d6403a", I: "#6b4fbb"};
const LOGO = `<svg viewBox="0 0 32 32" width="56" height="56"><path d="M16 2 28 9v14L16 30 4 23V9z" fill="#184f95"/><path d="M16 2 28 9v14L16 30z" fill="#a3232a"/><path d="m10.5 16.5 4 4 7.5-9" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

// One card's HTML (the page's styles are in PAGE below)
function card(r) {
  const {place, d, rep, dTag, rTag, same} = raceFacts(r);
  const head = `<div class="top">${LOGO}<span class="brand">Who Shows Up</span><span class="when">2026 forecast · ${esc(day)}</span></div>`;
  const foot = `<div class="foot"><span class="url">whoshowsup.net/race/${esc(r.race_id)}</span><span class="tag">A turnout-first forecast, updated daily</span></div>`;
  if (same) {
    const party = r.race_note === "D" ? "Democrats" : "Republicans";
    return `${head}<div class="place">${esc(place)}</div><div class="only">Only ${party} are on the November ballot</div>
      <div class="sub">${esc(String(r.dem_candidate ?? r.rep_candidate ?? "").replaceAll(";", " and"))}</div>${foot}`;
  }
  const p = r.p_dem, cut = Math.round(1072 * p);
  const side = (name, tag, prob, right) => `<div class="cand${right ? " right" : ""}">
      <div class="name"><span class="fit">${esc(name)}</span> <span class="chip" style="background:${COLOR[tag]}">${tag}</span></div>
      <div class="pct" style="color:${COLOR[tag]}">${prob}</div></div>`;
  return `${head}<div class="place">${esc(place)}</div>
    <div class="cands">${side(d, dTag, pctPair(p)[0], false)}<div class="vs">chance of<br>winning</div>${side(rep, rTag, pctPair(p)[1], true)}</div>
    <div class="bar"><div style="width:${cut}px;background:${COLOR[dTag]}"></div><div style="flex:1;background:${COLOR[rTag]}"></div></div>
    <div class="sub">Expected margin: ${esc(lean(r.margin_median, last(d), last(rep)))} · Rated ${esc(r.rating)}</div>${foot}`;
}

const PAGE = `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Source+Serif+4:opsz,wght@8..60,600;8..60,700&display=block">
<style>
  html, body { margin: 0; background: #f9f9f7; }
  #card { width: 1200px; height: 630px; box-sizing: border-box; padding: 52px 64px 44px; display: flex; flex-direction: column;
    font-family: Inter, "Segoe UI", Arial, sans-serif; color: #0b0b0b; overflow: hidden; }
  .top { display: flex; align-items: center; gap: 18px; padding-bottom: 26px; border-bottom: 2px solid #e4e2dc; }
  .brand { font-weight: 800; font-size: 36px; letter-spacing: -0.02em; }
  .when { margin-left: auto; font-size: 26px; color: #898781; }
  .place { font-family: "Source Serif 4", Georgia, serif; font-weight: 700; font-size: 54px; line-height: 1.1; margin-top: 30px; white-space: nowrap; }
  .cands { display: flex; align-items: flex-end; margin-top: 26px; }
  .cand { flex: 1; min-width: 0; }
  .cand.right { text-align: right; }
  .name { font-size: 32px; font-weight: 600; white-space: nowrap; }
  .chip { display: inline-block; color: #fff; font-size: 20px; font-weight: 700; padding: 3px 10px; border-radius: 6px; vertical-align: 4px; }
  .pct { font-size: 104px; font-weight: 800; line-height: 1; margin-top: 6px; letter-spacing: -0.03em; }
  .vs { font-size: 22px; color: #898781; text-align: center; padding: 0 24px 18px; line-height: 1.3; }
  .bar { display: flex; gap: 4px; height: 18px; margin-top: 22px; border-radius: 9px; overflow: hidden; }
  .sub { font-size: 28px; color: #52514e; margin-top: 24px; }
  .only { font-family: "Source Serif 4", Georgia, serif; font-size: 44px; font-weight: 600; margin-top: 40px; }
  .foot { margin-top: auto; display: flex; align-items: baseline; padding-top: 22px; border-top: 2px solid #e4e2dc; }
  .url { font-size: 28px; font-weight: 600; }
  .tag { margin-left: auto; font-size: 24px; color: #898781; }
</style></head><body><div id="card"></div></body></html>`;

// shrink any line that doesn't fit its box (long names, long place names)
const FIT = `(() => {
  for (const el of document.querySelectorAll(".place, .name")) {
    let size = parseFloat(getComputedStyle(el).fontSize);
    const box = el.closest(".cand") ?? el.parentElement;
    while (el.scrollWidth > box.clientWidth && size > 16) { size -= 1; el.style.fontSize = size + "px"; }
  }
  return true;
})()`;

async function render() {
  const exe = BROWSERS.find((p) => p && existsSync(p));
  if (!exe) throw new Error("no Chrome or Edge found (set CHROME_PATH)");
  const port = 9300 + Math.floor(Math.random() * 500);
  const profile = join(tmpdir(), `wsu-cards-${Date.now()}`);
  const browser = spawn(exe, ["--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars", `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`, "about:blank"], {stdio: "ignore"});
  try {
    let targets;
    for (let i = 0; i < 80 && !targets?.some((t) => t.type === "page"); i++) {
      try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch {}
      await wait(250);
    }
    const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
    await new Promise((ok, bad) => { ws.addEventListener("open", ok); ws.addEventListener("error", bad); });
    let id = 0;
    const pending = new Map();
    ws.addEventListener("message", (e) => { const m = JSON.parse(e.data); pending.get(m.id)?.(m); pending.delete(m.id); });
    const send = (method, params = {}) => new Promise((ok) => { pending.set(++id, ok); ws.send(JSON.stringify({id, method, params})); });
    const run = async (expression) => {
      const res = await send("Runtime.evaluate", {expression, awaitPromise: true, returnByValue: true});
      if (res.result?.exceptionDetails) throw new Error(res.result.exceptionDetails.text);
      return res.result?.result?.value;
    };
    await send("Emulation.setDeviceMetricsOverride", {width: 1200, height: 630, deviceScaleFactor: 1, mobile: false});
    const page = join(profile, "card.html");
    await writeFile(page, PAGE);
    await send("Page.enable");
    await send("Page.navigate", {url: "file:///" + page.split("\\").join("/")});
    for (let i = 0; i < 40 && !(await run("document.readyState === 'complete'").catch(() => false)); i++) await wait(250);
    await run("document.fonts.ready.then(() => true)");
    let made = 0;
    for (const r of races) {
      try {
        await run(`document.getElementById("card").innerHTML = ${JSON.stringify(card(r))}; document.fonts.ready.then(() => ${FIT})`);
        const shot = await send("Page.captureScreenshot", {format: "png", clip: {x: 0, y: 0, width: 1200, height: 630, scale: 1}});
        await writeFile(join(OUT, `${r.race_id}.png`), Buffer.from(shot.result.data, "base64"));
        made++;
      } catch (e) { console.warn(`share card failed for ${r.race_id}: ${e.message}`); }
    }
    ws.close();
    return made;
  } finally {
    browser.kill();
    await wait(500);
    try { rmSync(profile, {recursive: true, force: true}); } catch {}
  }
}

mkdirSync(OUT, {recursive: true});
let made = 0;
try { made = await render(); } catch (e) { console.warn(`share cards: ${e.message}`); }
// any race still without a card gets the site-wide image
let filled = 0;
for (const r of races) {
  const f = join(OUT, `${r.race_id}.png`);
  if (!existsSync(f) && existsSync(FALLBACK)) { copyFileSync(FALLBACK, f); filled++; }
}
console.log(`share cards: ${made} drawn${filled ? `, ${filled} using the site-wide image` : ""}`);
process.exit(0);
