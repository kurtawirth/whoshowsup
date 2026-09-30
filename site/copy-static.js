// After "observable build": copy files that must live at a fixed address (not fingerprinted) into dist.
// share.png is the preview image for shared links (written daily by midterms_2026/share_card.py).
import {copyFileSync, existsSync} from "node:fs";
for (const f of ["share.png"]) if (existsSync(`src/${f}`)) copyFileSync(`src/${f}`, `dist/${f}`);
