// Search and AI-readability for Who Shows Up: each page's title and description, a plain-text summary that
// crawlers can read without running JavaScript, and the site-wide files search engines and AI tools look for
// (sitemap.xml, robots.txt, llms.txt, llms-full.txt). Everything is built from the day's forecast data, so it
// updates with every daily run. Used by observablehq.config.js (page head) and postbuild.js (after the build).
import {readFileSync} from "node:fs";

export const SITE_URL = "https://whoshowsup.net";
const load = (f) => JSON.parse(readFileSync(new URL(`./src/data/${f}`, import.meta.url), "utf-8"));
export const races = load("races.json");
export const top = load("topline.json");

const pctText = (p) => (p >= 0.995 ? ">99%" : p <= 0.005 ? "<1%" : `${Math.round(p * 100)}%`);
export const fav = (p, d = "Democrats", r = "Republicans") => `${p >= 0.5 ? d : r} ${pctText(Math.max(p, 1 - p))}`;
export const updated = new Date(`${top.forecast_date}T12:00:00`).toLocaleDateString("en-US", {month: "short", day: "numeric"});
const updatedLong = new Date(`${top.forecast_date}T12:00:00`).toLocaleDateString("en-US", {month: "long", day: "numeric", year: "numeric"});
export const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
// "D+7.1" for parties, "Jackson +4.0" for candidates
const lean = (m, d = "D", r = "R") => { const sp = (x) => (x.length > 1 ? " " : ""); return Math.abs(m) < 0.05 ? "even" : m > 0 ? `${d}${sp(d)}+${m.toFixed(1)}` : `${r}${sp(r)}+${(-m).toFixed(1)}`; };
const article = (p) => (/^(8|11|18)/.test(pctText(p)) ? "an" : "a");
const last = (s) => String(s ?? "").trim().split(/\s+/).filter((w) => !/^(Jr\.?|Sr\.?|I{2,3})$/.test(w)).pop();
const nth = (n) => n + (["th", "st", "nd", "rd"][(n % 100 - 20) % 10] || ["th", "st", "nd", "rd"][n % 100] || "th");
const urlOf = (path) => `${SITE_URL}${path === "/index" || path === "/" ? "/" : path}`;
const tail = "A turnout-first forecast of every House, Senate and governor race.";

// The site's main pages: title (as shown in search results) and description
export const PAGES = {
  "/index": ["2026 Midterm Election Forecast: House, Senate and Governor Odds",
    `Who Shows Up forecasts the 2026 midterms: House ${fav(top.p_house_d)}, Senate ${fav(top.p_senate_d)} to win control (updated ${updated}). ${tail}`],
  "/house": ["2026 House Forecast: Every District",
    `Democrats win the House in ${pctText(top.p_house_d)} of our simulations, with about ${Math.round(top.house_median)} seats (updated ${updated}). Odds for all 435 districts.`],
  "/senate": ["2026 Senate Forecast: Every Race",
    `Democrats win the Senate in ${pctText(top.p_senate_d)} of our simulations (updated ${updated}). Odds, polls and expected margins for all 35 Senate races.`],
  "/governors": ["2026 Governor Forecasts: All 36 Races",
    `Democrats win about ${Math.round(top.gov_median)} of 36 governor's races in our forecast (updated ${updated}). Odds and polls for every race.`],
  "/national": ["2026 Generic Ballot and National Environment",
    `Our estimate of the 2026 national House vote: ${lean(top.nat_median)} (updated ${updated}), from the generic ballot, special elections and fundamentals.`],
  "/specials": ["Special Elections This Cycle: Results vs. Partisan Lean",
    "Every special election this cycle compared with how the same district voted for president: the turnout signal behind the forecast."],
  "/early-vote": ["2026 Early Vote Tracker by State",
    "Ballots cast before Election Day 2026, state by state: who is turning out early."],
  "/results": ["2026 Election Night Results, Live",
    "Live 2026 midterm results on election night, race by race, compared with our forecast."],
  "/past-results": ["County Election Results 2000-2025: Maps for Every County",
    "How every county voted for president since 2000, and for Senate and governor since 2018, with shifts over time and turnout."],
  "/compare": ["How Our 2026 Forecast Compares",
    "Where Who Shows Up agrees and disagrees with other forecasters, raters and prediction markets, and how the method would have done in past elections."],
  "/methodology": ["How the Forecast Works: Methodology and Track Record",
    "How Who Shows Up forecasts the midterms: the national mood, polls, special elections, simulations, and how the model did in past elections."]
};

// One race: its names, sides and our numbers, in words
export function raceFacts(r) {
  const office = {HOUSE: "", SEN: " Senate", GOV: " governor"}[r.office];
  const place = r.office === "HOUSE" ? `${r.state_name}'s ${r.district === 0 ? "at-large House seat" : `${nth(r.district)} District`}`
    : `${r.state_name}${office}${r.special ? " special election" : ""}`;
  const ind = r.race_type === "independent", indD = ind && Boolean(r.rep_candidate);
  const d = indD ? r.race_note : r.dem_name, rep = ind && !indD ? r.race_note : r.rep_name;
  const dTag = indD ? "I" : "D", rTag = ind && !indD ? "I" : "R";
  return {place, d, rep, dTag, rTag, same: r.race_type === "same_party"};
}

export function racePage(r) {
  const {place, d, rep, dTag, rTag, same} = raceFacts(r);
  // Search titles lead with what people search for: the candidates' names and "polls" (Search Console: "chris
  // deluzio", "mullock vs van drew polls", "nj-2 polls"); the race follows. The page's own heading is unchanged.
  const title = same ? `${place} 2026 forecast` : `${d} vs. ${rep} polls and 2026 forecast (${place})`;
  const desc = same
    ? `Only ${r.race_note === "D" ? "Democrats" : "Republicans"} are on the November 2026 ballot here. ${tail}`
    : `Our forecast: ${fav(r.p_dem, d, rep)} to win (updated ${updated}), with the polls, expected margin and past results. ${tail}`;
  return {title, desc, ogTitle: same ? place : `${place}: ${d} vs. ${rep}`};
}

// Title and description for any page path
export function pageMeta(path) {
  const r = races.find((x) => `/race/${x.race_id}` === path);
  if (r) return racePage(r);
  const [title, desc] = PAGES[path] ?? [null, PAGES["/index"][1]];
  return {title, desc, ogTitle: title};
}

// A race in one plain sentence (for summaries and llms-full.txt)
function raceSentence(r) {
  const {place, d, rep, dTag, rTag, same} = raceFacts(r);
  if (same) return `${place}: only ${r.race_note === "D" ? "Democrats" : "Republicans"} on the ballot.`;
  const leader = r.p_dem >= 0.5 ? d : rep;
  return `${place}: ${d} (${dTag}) vs. ${rep} (${rTag}). ${last(leader)} ${pctText(Math.max(r.p_dem, 1 - r.p_dem))} to win; expected margin ${lean(r.margin_median, last(d), last(rep))}.`;
}

// What a crawler that doesn't run JavaScript should see on each page: the same facts the page shows
export function summaryHtml(path) {
  const link = (p, text) => `<a href="${p}">${esc(text)}</a>`;
  const list = (rs) => `<ul>${rs.map((r) => `<li>${link(`/race/${r.race_id}`, raceSentence(r))}</li>`).join("")}</ul>`;
  const byOffice = (o) => races.filter((r) => r.office === o).sort((a, b) => a.state_name.localeCompare(b.state_name) || a.district - b.district);
  const topline = `<p>As of ${updatedLong}: Democrats win the House in ${pctText(top.p_house_d)} of 20,000 simulations (about ${Math.round(top.house_median)} seats; 218 needed) and the Senate in ${pctText(top.p_senate_d)} (about ${Math.round(top.senate_median)} seats). Expected national House vote: ${lean(top.nat_median)}. Democrats win about ${Math.round(top.gov_median)} of 36 governor's races.</p>`;
  const r = races.find((x) => `/race/${x.race_id}` === path);
  let body;
  if (r) {
    const {place, d, rep, dTag, rTag, same} = raceFacts(r);
    const chamber = {HOUSE: ["/house", "House forecast"], SEN: ["/senate", "Senate forecast"], GOV: ["/governors", "Governor forecasts"]}[r.office];
    const facts = [];
    if (!same) {
      facts.push(`Our forecast gives ${r.p_dem >= 0.5 ? `${d} (${dTag})` : `${rep} (${rTag})`} ${article(Math.max(r.p_dem, 1 - r.p_dem))} ${pctText(Math.max(r.p_dem, 1 - r.p_dem))} chance of winning (rating: ${r.rating}), as of ${updatedLong}.`);
      facts.push(`Expected margin: ${lean(r.margin_median, last(d), last(rep))}; in 80% of simulations the margin falls between ${lean(r.margin_p10, last(d), last(rep))} and ${lean(r.margin_p90, last(d), last(rep))}.`);
      if (r.poll_count) facts.push(`Polling average: ${lean(r.poll_avg, last(d), last(rep))} across ${r.poll_count} poll${r.poll_count === 1 ? "" : "s"}.`);
    } else facts.push(`Only ${r.race_note === "D" ? "Democrats" : "Republicans"} are on the November ballot, so party control isn't in play.`);
    if (r.incumbent) facts.push(`Incumbent: ${r.incumbent}${r.incumbent_party ? ` (${r.incumbent_party})` : ""}.`);
    if (r.pres24 != null) facts.push(`2024 presidential result here: ${lean(r.pres24)}.`);
    body = `<h1>${esc(racePage(r).title)}</h1><p>${esc(facts.join(" "))}</p><p>${link(chamber[0], chamber[1])} · ${link("/methodology", "How the forecast works")}</p>`;
  } else if (path === "/index") {
    body = `<h1>${esc(PAGES["/index"][0])}</h1>${topline}<h2>Senate races</h2>${list(byOffice("SEN"))}<h2>Governor's races</h2>${list(byOffice("GOV"))}<p>${link("/house", "All 435 House races")}</p>`;
  } else if (path === "/house") {
    body = `<h1>${esc(PAGES[path][0])}</h1>${topline}${list(byOffice("HOUSE"))}`;
  } else if (path === "/senate") {
    body = `<h1>${esc(PAGES[path][0])}</h1>${topline}${list(byOffice("SEN"))}`;
  } else if (path === "/governors") {
    body = `<h1>${esc(PAGES[path][0])}</h1>${topline}${list(byOffice("GOV"))}`;
  } else if (PAGES[path]) {
    body = `<h1>${esc(PAGES[path][0])}</h1><p>${esc(PAGES[path][1])}</p>${topline}`;
  } else return "";
  return `<noscript><div class="wsu-static">${body}</div></noscript>`;
}

// Structured data (schema.org) for search engines: what the page is, who made it, when it last changed
export function jsonLd(path) {
  const {title, desc} = pageMeta(path);
  const author = {"@type": "Person", name: "Kurt Wirth", url: "https://github.com/kurtawirth"};
  const page = {"@context": "https://schema.org", "@type": "WebPage", name: title ?? "Who Shows Up", description: desc, url: urlOf(path),
    dateModified: top.forecast_date, inLanguage: "en-US", author, isPartOf: {"@type": "WebSite", name: "Who Shows Up", url: `${SITE_URL}/`}};
  const items = [page];
  if (path === "/index") items.push({"@context": "https://schema.org", "@type": "WebSite", name: "Who Shows Up", alternateName: "Who Shows Up 2026 midterm forecast",
    url: `${SITE_URL}/`, description: PAGES["/index"][1], author, inLanguage: "en-US"});
  return items.map((x) => `<script type="application/ld+json">${JSON.stringify(x).replace(/</g, "\\u003c")}</script>`).join("\n");
}

export const allPaths = () => [...Object.keys(PAGES), ...races.map((r) => `/race/${r.race_id}`)];

export function sitemap() {
  const pri = (p) => (p === "/index" ? "1.0" : p.startsWith("/race/") ? "0.6" : "0.8");
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${allPaths().map((p) => `  <url><loc>${urlOf(p)}</loc><lastmod>${top.forecast_date}</lastmod><changefreq>daily</changefreq><priority>${pri(p)}</priority></url>`).join("\n")}
</urlset>
`;
}

export function robots() {
  return `# Who Shows Up welcomes search engines and AI assistants.
# A plain-text summary of the whole forecast for AI tools: ${SITE_URL}/llms.txt
User-agent: *
Allow: /

Sitemap: ${SITE_URL}/sitemap.xml
`;
}

const ABOUT = `Who Shows Up is an independent, open-source forecast of the 2026 U.S. midterm elections (House, Senate and governors) by Kurt Wirth, Ph.D. Its premise is turnout-first: midterms are decided by whose voters show up, so it reads the electorate's enthusiasm from more than 100 special elections this cycle, blends that with the generic-ballot polls and fundamentals (presidential approval and the midterm penalty) into an estimate of the national House vote, carries that estimate down to every race using each district's partisan lean, incumbency, candidate experience, ideology and campaign money, updates each race with its own polls, and simulates the election 20,000 times with polling errors that move together. Every piece was tested against past elections the model had not seen. It uses no expert ratings, other forecasters' models or prediction markets as inputs. The forecast updates every morning. The code was written by Claude, Anthropic's AI model, under the author's direction; the modeling choices are the author's.`;

export function llmsTxt() {
  const pages = Object.entries(PAGES).map(([p, [t, d]]) => `- [${t}](${urlOf(p)}): ${d}`).join("\n");
  return `# Who Shows Up

> A turnout-first forecast of the 2026 U.S. midterm elections. As of ${updatedLong}: Democrats win the House in ${pctText(top.p_house_d)} of simulations and the Senate in ${pctText(top.p_senate_d)}; expected national House vote ${lean(top.nat_median)}.

${ABOUT}

## Pages

${pages}
- Race pages: ${SITE_URL}/race/{race} for every race, e.g. ${SITE_URL}/race/senate-me, ${SITE_URL}/race/governor-oh, ${SITE_URL}/race/house-pa-7

## Data

- [The full forecast in plain text](${SITE_URL}/llms-full.txt): every race's odds, expected margin and polling average, updated daily
- [Source code and data pipeline](https://github.com/kurtawirth/whoshowsup)
`;
}

export function llmsFullTxt() {
  const section = (o, name) => {
    const rs = races.filter((r) => r.office === o).sort((a, b) => a.state_name.localeCompare(b.state_name) || a.district - b.district);
    return `## ${name}\n\n${rs.map((r) => `- ${raceSentence(r)}${r.poll_count && r.race_type !== "same_party" ? ` Polling average ${lean(r.poll_avg, last(raceFacts(r).d), last(raceFacts(r).rep))} (${r.poll_count} poll${r.poll_count === 1 ? "" : "s"}).` : ""} ${urlOf(`/race/${r.race_id}`)}`).join("\n")}\n`;
  };
  return `# Who Shows Up: the full 2026 midterm forecast

Updated ${updatedLong}. Source: ${SITE_URL}/ (please cite "Who Shows Up" and link to the race page).

${ABOUT}

## Topline

- House: Democrats win control in ${pctText(top.p_house_d)} of 20,000 simulations. Most likely about ${Math.round(top.house_median)} Democratic seats (80% range ${Math.round(top.house_p10)}-${Math.round(top.house_p90)}); 218 needed.
- Senate: Democrats win control in ${pctText(top.p_senate_d)} of simulations. About ${Math.round(top.senate_median)} Democratic seats (80% range ${Math.round(top.senate_p10)}-${Math.round(top.senate_p90)}).
- Governors: Democrats win about ${Math.round(top.gov_median)} of 36 races (80% range ${Math.round(top.gov_p10)}-${Math.round(top.gov_p90)}).
- National House popular vote: ${lean(top.nat_median)} expected (80% range ${lean(top.nat_p10)} to ${lean(top.nat_p90)}).
- Election Day: ${top.election_day}.

Margins are in percentage points between the two leading candidates; "expected margin" is the median of the simulations.

${section("SEN", "Senate races")}
${section("GOV", "Governor's races")}
${section("HOUSE", "House races")}`;
}
