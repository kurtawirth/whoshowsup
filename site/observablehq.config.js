// Who Shows Up -- site configuration (Observable Framework).
import {readFileSync} from "node:fs";

// Links are written site-root-relative ("/house"); Framework rewrites them relative to each page, so they work under any hosting base path.
const base = process.env.SITE_BASE ?? "/";
const races = JSON.parse(readFileSync(new URL("./src/data/races.json", import.meta.url), "utf-8"));

const nav = [
  ["/", "Overview"],
  ["/house", "House"],
  ["/senate", "Senate"],
  ["/governors", "Governors"],
  ["/national", "The national picture"],
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
  head: `
<meta name="description" content="Who Shows Up: a turnout-first forecast of the 2026 U.S. midterm elections.">
<link rel="icon" href="data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><path d='M16 2 28 9v14L16 30 4 23V9z' fill='#184f95'/><path d='M16 2 28 9v14L16 30z' fill='#a3232a'/><path d='m10.5 16.5 4 4 7.5-9' fill='none' stroke='#fff' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'/></svg>`
  )}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap" rel="stylesheet">`,
  header: ({path}) => `
<a class="wsu-brand" href="/">
  <svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2 28 9v14L16 30 4 23V9z" fill="var(--safe-d)"/><path d="M16 2 28 9v14L16 30z" fill="var(--safe-r)"/><path d="m10.5 16.5 4 4 7.5-9" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
  <span>Who Shows Up</span>
</a>
<nav class="wsu-nav" aria-label="Sections">${nav.map(([p, n]) => `<a href="${p}"${section(path) === p ? ' aria-current="page"' : ""}>${n}</a>`).join("")}</nav>`,
  footer: `
<div class="wsu-footer">
  <p><strong>Who Shows Up</strong> is an independent, turnout-first forecast of the 2026 midterms by <a href="https://github.com/kurtawirth">Kurt Wirth, Ph.D.</a>
  It uses no pundit ratings and no other forecasters' models.</p>
  <p>Poll data from <a href="https://votehub.com">VoteHub</a> (CC BY 4.0), <a href="https://polls.decisiondeskhq.com">Decision Desk HQ</a>, and Wikipedia;
  results from the <a href="https://electionlab.mit.edu">MIT Election Data + Science Lab</a>; district presidential results and special elections from
  <a href="https://www.the-downballot.com">The Downballot</a>; historical polls from FiveThirtyEight's public archive; hex layout adapted from
  Pitch Interactive's Tilegrams. Full source: <a href="https://github.com/kurtawirth/whoshowsup">GitHub</a>.</p>
</div>`
};
