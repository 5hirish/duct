// Copies the connector marks and post covers the film references into
// public/, which is gitignored. They stay canonical in site/ and scripts/shots/
// so the film cannot drift from the page and the README; a copy on disk is
// what Remotion's staticFile() needs.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");
const out = join(here, "public");
mkdirSync(out, { recursive: true });

const ICONS = ["google-ads", "googleanalytics", "stripe", "clarity", "googlesearchconsole"];
const COVERS = ["post-september", "post-invoice", "post-tax-jar"];

for (const name of ICONS) copyFileSync(join(repo, "site/assets/icons", `${name}.svg`), join(out, `${name}.svg`));
for (const name of COVERS) copyFileSync(join(repo, "scripts/shots/assets", `${name}.jpg`), join(out, `${name}.jpg`));
console.log(`synced ${ICONS.length} marks and ${COVERS.length} covers into public/`);
