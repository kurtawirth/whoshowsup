// "Your races": look up a ZIP code and see its House, Senate and governor races, and where a vote counts most
// nearby. The ZIP data (zip_lookup.csv, from core/build_zip_districts.py: each ZIP code tabulation area's 2026
// House districts and their share of its residents) loads only when someone looks one up, and the ZIP never
// leaves the browser: it isn't sent to our visit counter or put in the address.
import {pct, raceLink, favoriteText, tpPct, powerText, countEvent} from "./wsu.js";

const MILES = 100;
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const miles = (a, b) => {  // great-circle distance
  const R = 3958.8, rad = Math.PI / 180, dLat = (b.lat - a.lat) * rad, dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
};
const houseId = (st, d) => `house-${st.toLowerCase()}-${d === 0 ? "al" : d}`;

export function zipLookup(races, zipFile) {
  const byId = new Map(races.map((r) => [r.race_id, r]));
  let data = null;
  const load = () => (data ??= zipFile.text().then((t) => {
    const m = new Map();
    for (const line of t.split("\n")) {
      if (!line) continue;
      const [z, lat, lon, cells] = line.split(",");
      m.set(z, {z, lat: +lat, lon: +lon, cells: cells.split("|").map((c) => {
        const [code, share] = c.split(":");
        return {st: code.slice(0, 2), d: +code.slice(2), share: share ? +share / 100 : 1};
      })});
    }
    return m;
  }));

  const root = el("div", "zip-box");
  const form = el("form", "zip-form");
  const input = Object.assign(el("input"), {type: "text", inputMode: "numeric", maxLength: 5, placeholder: "ZIP code", autocomplete: "postal-code"});
  input.setAttribute("aria-label", "Your ZIP code");
  const go = el("button", null, "Show my races");
  go.type = "submit";
  form.append(input, go);
  const out = el("div", "zip-out");
  root.append(form, out);

  const line = (r, extra) => {
    const li = el("li");
    li.append(raceLink(r, r.office === "HOUSE" ? `House: ${r.label}` : `${r.state_name} ${r.office === "SEN" ? "Senate" : "governor"}${r.special ? " (special)" : ""}`));
    li.append(` · ${r.race_type === "same_party" ? `only ${r.race_note === "D" ? "Democrats" : "Republicans"} on the ballot` : favoriteText(r)}`);
    if (r.race_type !== "same_party" && r.tipping_point != null && (r.office === "SEN" || r.office === "HOUSE")) {
      const s = el("div", "muted");
      s.textContent = r.tipping_point >= 0.005
        ? `Tipping point in ${tpPct(r.tipping_point)} of simulations; a vote here is ${powerText(r.voter_power)} the average ${r.office === "SEN" ? "Senate" : "House"} vote to decide control.`
        : "Rarely decides control of the chamber.";
      li.append(s);
    }
    if (extra) li.append(el("div", "muted", extra));
    return li;
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const z = input.value.trim();
    out.replaceChildren();
    if (!/^\d{5}$/.test(z)) { out.append(el("p", "caption", "Enter a five-digit ZIP code.")); return; }
    out.append(el("p", "caption", "Looking it up…"));
    const m = await load();
    const me = m.get(z);
    out.replaceChildren();
    countEvent("zip-lookup", "Your races: ZIP lookup");  // counts uses only; the ZIP itself isn't sent
    if (!me) {
      out.append(el("p", "caption", "We couldn't find that ZIP code. Some ZIP codes cover only P.O. boxes or a single building; try the ZIP code where you live."));
      return;
    }
    // your races
    const st = me.cells[0].st;
    const yours = el("ul", "zip-races");
    const house = me.cells.map((c) => ({c, r: byId.get(houseId(c.st, c.d))})).filter((x) => x.r);
    for (const {c, r} of house) yours.append(line(r, house.length > 1 ? `About ${Math.round(c.share * 100)}% of the people in this ZIP code live in this district.` : null));
    for (const id of [`senate-${st.toLowerCase()}`, `senate-${st.toLowerCase()}-special`, `governor-${st.toLowerCase()}`]) {
      const r = byId.get(id);
      if (r) yours.append(line(r));
    }
    const h3 = el("h3", null, `Your races (ZIP ${z})`);
    out.append(h3, yours);
    if (house.length > 1) {
      const p = el("p", "caption");
      p.append("This ZIP code is split between House districts. Your sample ballot or ");
      const a = Object.assign(el("a", null, "your state's election office"), {href: "https://www.usa.gov/state-election-office"});
      p.append(a, " can tell you which one is yours.");
      out.append(p);
    }
    if (!byId.has(`senate-${st.toLowerCase()}`) && !byId.has(`senate-${st.toLowerCase()}-special`)) out.append(el("p", "caption", "There's no Senate race in your state this year."));
    // where a vote counts most nearby: every race with a sizable tipping-point chance within ~100 miles
    const near = new Map();
    for (const x of m.values()) {
      if (Math.abs(x.lat - me.lat) > 1.6 || Math.abs(x.lon - me.lon) > 2.4) continue;  // quick box first
      const dist = miles(me, x);
      if (dist > MILES) continue;
      for (const c of x.cells) {
        for (const id of [houseId(c.st, c.d), `senate-${c.st.toLowerCase()}`, `senate-${c.st.toLowerCase()}-special`]) {
          const r = byId.get(id);
          if (r && r.tipping_point >= 0.005 && (!near.has(id) || near.get(id).dist > dist)) near.set(id, {r, dist});
        }
      }
    }
    const best = [...near.values()].sort((a, b) => b.r.voter_power - a.r.voter_power).slice(0, 5);
    if (best.length) {
      out.append(el("h3", null, "Where a vote counts most near you"));
      const ul = el("ul", "zip-races");
      for (const {r, dist} of best) ul.append(line(r, dist < 5 ? "Includes your area." : `About ${Math.round(dist / 5) * 5} miles away.`));
      out.append(ul, el("p", "caption", `Races within about ${MILES} miles, ranked by how likely a single vote there is to decide control of the House or Senate. Useful if you're thinking about where to volunteer, whichever side you're on.`));
    }
  });
  return root;
}
