// Who Shows Up -- site configuration (Observable Framework).
import {readFileSync} from "node:fs";

// Links are written site-root-relative ("/house"); Framework rewrites them relative to each page, so they work under any hosting base path.
const base = process.env.SITE_BASE ?? "/";
const races = JSON.parse(readFileSync(new URL("./src/data/races.json", import.meta.url), "utf-8"));
const top = JSON.parse(readFileSync(new URL("./src/data/topline.json", import.meta.url), "utf-8"));

// Preview tags for shared links (Facebook, X, iMessage, Slack...): each page's own title and a line with
// today's odds; race pages name the matchup and our odds. The image is regenerated with every daily run;
// ?d= makes apps fetch the new one instead of a cached copy.
const SITE_URL = "https://whoshowsup.net";
const pctText = (p) => (p >= 0.995 ? ">99%" : p <= 0.005 ? "<1%" : `${Math.round(p * 100)}%`);
const fav = (p, d = "Democrats", r = "Republicans") => `${p >= 0.5 ? d : r} ${pctText(Math.max(p, 1 - p))}`;
const updated = new Date(`${top.forecast_date}T12:00:00`).toLocaleDateString("en-US", {month: "short", day: "numeric"});
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
const byRace = new Map(races.map((r) => [`/race/${r.race_id}`, r]));
function preview({title, path}) {
  const r = byRace.get(path);
  let t = title && title !== "2026 Midterm Forecast" ? `${title} | Who Shows Up` : "Who Shows Up: 2026 midterm forecast";
  let desc = `Chance of winning control: House ${fav(top.p_house_d)}, Senate ${fav(top.p_senate_d)} (updated ${updated}). A turnout-first forecast of every House, Senate and governor race.`;
  if (r) {
    const office = {HOUSE: "", SEN: " Senate", GOV: " governor"}[r.office];
    const nth = (n) => n + (["th", "st", "nd", "rd"][(n % 100 - 20) % 10] || ["th", "st", "nd", "rd"][n % 100] || "th");
    const place = r.office === "HOUSE" ? `${r.state_name}'s ${r.district === 0 ? "at-large House seat" : `${nth(r.district)} District`}`
      : `${r.state_name}${office}${r.special ? " special" : ""}`;
    const ind = r.race_type === "independent", indD = ind && Boolean(r.rep_candidate);
    const d = indD ? r.race_note : r.dem_name, rep = ind && !indD ? r.race_note : r.rep_name;
    t = r.race_type === "same_party" ? `${place} | Who Shows Up` : `${place}: ${d} vs. ${rep} | Who Shows Up`;
    const tail = desc.split(". ").slice(-1)[0];
    desc = r.race_type === "same_party"
      ? `Only ${r.race_note === "D" ? "Democrats" : "Republicans"} are on the November ballot here. ${tail}`
      : `Our forecast: ${fav(r.p_dem, d, rep)} to win (updated ${updated}). ${tail}`;
  }
  const url = `${SITE_URL}${path === "/index" ? "/" : path}`, img = `${SITE_URL}/share.png?d=${top.forecast_date}`;
  return `<meta property="og:type" content="website">
<meta property="og:site_name" content="Who Shows Up">
<meta property="og:title" content="${esc(t)}">
<meta property="og:description" content="${esc(desc)}">
<meta property="og:url" content="${esc(url)}">
<meta property="og:image" content="${img}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="${esc(`Who Shows Up forecast, ${updated}: House ${fav(top.p_house_d)}, Senate ${fav(top.p_senate_d)} to win control`)}">
<meta name="twitter:card" content="summary_large_image">`;
}

const nav = [
  ["/", "Overview"],
  ["/house", "House"],
  ["/senate", "Senate"],
  ["/governors", "Governors"],
  ["/national", "The national picture"],
  ["/specials", "Special elections"],
  ["/early-vote", "Early vote"],
  ["/results", "Election night"],
  ["/past-results", "Past results"],
  ["/compare", "Compare"],
  ["/methodology", "How it works"]
];

// Which nav item a page belongs to (race pages count under their chamber).
function section(path = "") {
  const m = path.match(/^\/race\/(house|senate|governor)-/);
  if (m) return {house: "/house", senate: "/senate", governor: "/governors"}[m[1]];
  return path === "/index" || path === "/" ? "/" : path;
}

export default {
  title: "Who Shows Up",
  root: "src",
  output: "dist",
  base,
  sidebar: false,
  toc: false,
  pager: false,
  search: false,
  style: "style.css",
  pages: nav.map(([path, name]) => ({name, path})),
  // One page per race: /race/house-tx-28, /race/senate-ga, /race/governor-az ...
  dynamicPaths: races.map((r) => `/race/${r.race_id}`),
  head: (page) => preview(page) + `
<meta name="description" content="Who Shows Up: a turnout-first forecast of the 2026 U.S. midterm elections.">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon-32.png" type="image/png" sizes="32x32">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap" rel="stylesheet">
<script>
// A tab left open across a site update still asks for the previous build's files (their names carry a
// fingerprint, and each update replaces them), so it breaks. When the tab comes back into view, or a
// file fails to load, check whether the site changed since this page loaded; if it did, reload.
(() => {
  const RE = /(?:_file|_import|_npm|_observablehq)\\/[^"'\\s)]+\\.[0-9a-f]{8}\\.[a-z]+/g;
  let ours = null, busy = false, last = 0;
  const snapshot = () => { ours ??= new Set(document.documentElement.outerHTML.match(RE) ?? []); };
  document.addEventListener("DOMContentLoaded", snapshot);
  async function check() {
    if (busy || Date.now() - last < 30000) return;
    busy = true; last = Date.now(); snapshot();
    try {
      const html = await (await fetch(location.pathname, {cache: "no-store"})).text();
      if ((html.match(RE) ?? []).some((f) => !ours.has(f))) location.reload();
    } catch {} finally { busy = false; }
  }
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") check(); });
  addEventListener("pageshow", (e) => { if (e.persisted) check(); });
  addEventListener("error", (e) => { if (e.target !== window) check(); }, true);
  addEventListener("unhandledrejection", check);
  // Phones: a chart's info box stays up after a tap (charts only clear it when a mouse leaves), so a
  // tap anywhere outside a chart closes its box.
  addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse") return;
    for (const svg of document.querySelectorAll('svg[class^="plot"]'))
      if (!svg.contains(e.target)) svg.dispatchEvent(new PointerEvent("pointerleave", {pointerType: "mouse"}));
  }, true);
})();
</script>`,
  header: ({path}) => `
<a class="wsu-brand" href="/">
  <svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2 28 9v14L16 30 4 23V9z" fill="var(--safe-d)"/><path d="M16 2 28 9v14L16 30z" fill="var(--safe-r)"/><path d="m10.5 16.5 4 4 7.5-9" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
  <span>Who Shows Up</span>
</a>
<nav class="wsu-nav" aria-label="Sections">${nav.map(([p, n]) => `<a href="${p}"${section(path) === p ? ' aria-current="page"' : ""}>${n}</a>`).join("")}</nav>`,
  footer: `
<div class="wsu-footer">
  <p><strong>Who Shows Up</strong> is an independent, turnout-first forecast of the 2026 midterms by <a href="https://github.com/kurtawirth">Kurt Wirth, Ph.D.</a>
  It uses no pundit ratings and no other forecasters' models. Built with <a href="https://www.anthropic.com/claude">Claude</a>, Anthropic's AI model, which wrote the code under the author's direction; the modeling choices are the author's (<a href="${base}methodology#how-this-was-built">more</a>).</p>
  <p>Poll data from <a href="https://votehub.com">VoteHub</a> (CC BY 4.0), <a href="https://votes.decisiondeskhq.com/polls">Decision Desk HQ</a>, and Wikipedia;
  results from the <a href="https://electionlab.mit.edu">MIT Election Data + Science Lab</a>; district presidential results and special elections from
  <a href="https://www.the-downballot.com">The Downballot</a>; historical polls from FiveThirtyEight's public archive; campaign finance from the
  <a href="https://www.fec.gov/data/">Federal Election Commission</a>; early-vote counts and election-night results from <a href="https://civicapi.org">civicAPI</a>; prediction-market prices (shown for comparison only) from <a href="https://www.predictit.org">PredictIt</a>; candidate ideology scores from Adam Bonica's
  <a href="https://data.stanford.edu/dime">Database on Ideology, Money in Politics, and Elections</a> (DIME, Stanford University Libraries, ODC-BY 1.0); hex layout adapted from
  Pitch Interactive's Tilegrams. Full source: <a href="https://github.com/kurtawirth/whoshowsup">GitHub</a>.</p>
</div>`
};
