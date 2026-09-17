// Copies the connector marks and post covers the film references into
// public/, which is gitignored. They stay canonical in site/ and scripts/shots/
// so the film cannot drift from the page and the README; a copy on disk is
// what Remotion's staticFile() needs.
import { copyFileSync, mkdirSync, readdirSync } from "node:fs";
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
// The sound lives in audio/ (tracked) and is copied the same way, so public/
// stays a build output and nothing in it needs committing.
mkdirSync(join(out, "sfx"), { recursive: true });
const sfx = readdirSync(join(here, "audio/sfx")).filter((f) => f.endsWith(".wav"));
for (const f of sfx) copyFileSync(join(here, "audio/sfx", f), join(out, "sfx", f));
copyFileSync(join(here, "audio/music/music.mp3"), join(out, "music.mp3"));
console.log(`synced ${ICONS.length} marks, ${COVERS.length} covers, ${sfx.length} sounds and the music bed into public/`);
