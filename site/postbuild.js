// After "observable build": finish the site for sharing, search engines and AI tools (see seo.js).
// - share.png, the preview image for shared links (written daily by midterms_2026/share_card.py), and the site icons,
//   at fixed addresses
// - each page's own <title>, and a plain-text summary of the page for crawlers that don't run JavaScript
// - sitemap.xml, robots.txt, llms.txt and llms-full.txt, rebuilt from the day's forecast
import {copyFileSync, existsSync, readFileSync, readdirSync, writeFileSync} from "node:fs";
import {join, relative} from "node:path";
import {pageMeta, summaryHtml, sitemap, robots, llmsTxt, llmsFullTxt, esc} from "./seo.js";

for (const f of ["share.png", "favicon.svg", "favicon-32.png", "apple-touch-icon.png"]) if (existsSync(`src/${f}`)) copyFileSync(`src/${f}`, `dist/${f}`);

const pages = (dir) => readdirSync(dir, {withFileTypes: true}).flatMap((e) =>
  e.isDirectory() ? (e.name.startsWith("_") ? [] : pages(join(dir, e.name))) : e.name.endsWith(".html") && !e.name.startsWith("_") ? [join(dir, e.name)] : []);
const MAIN = '<main id="observablehq-main" class="observablehq">';
let n = 0;
for (const file of pages("dist")) {
  const path = "/" + relative("dist", file).split("\\").join("/").replace(/\.html$/, "");
  const {title} = pageMeta(path);
  if (!title) continue;
  let html = readFileSync(file, "utf8");
  html = html.replace(/<title>[^<]*<\/title>/, `<title>${esc(title)} | Who Shows Up</title>`);
  if (html.includes(MAIN)) html = html.replace(MAIN, MAIN + summaryHtml(path));
  writeFileSync(file, html);
  n++;
}
writeFileSync("dist/sitemap.xml", sitemap());
writeFileSync("dist/robots.txt", robots());
writeFileSync("dist/llms.txt", llmsTxt());
writeFileSync("dist/llms-full.txt", llmsFullTxt());
console.log(`postbuild: titles and summaries on ${n} pages; sitemap.xml, robots.txt, llms.txt, llms-full.txt`);
