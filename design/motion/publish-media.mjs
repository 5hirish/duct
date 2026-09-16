// Moves a finished render into the site. Renders are committed, and a 2-3 MB
// video is a real cost to the repository, so this is a deliberate step after
// looking at the output, never part of `render:film`.
import { copyFileSync, mkdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const media = join(here, "..", "..", "site", "assets", "media");
mkdirSync(media, { recursive: true });

// The plan budgeted a silent film; the sound adds ~0.3 MB to each, so the
// webm line moved from 2 to 2.5 MB rather than crushing the picture.
const LIMIT_BYTES = { "demo.mp4": 3_000_000, "demo.webm": 2_500_000, "demo-poster.webp": 80_000 };
for (const [name, limit] of Object.entries(LIMIT_BYTES)) {
  const from = join(here, "out", name);
  const size = statSync(from).size;
  if (size > limit) throw new Error(`${name} is ${(size / 1e6).toFixed(2)} MB, over the ${(limit / 1e6).toFixed(1)} MB budget the plan set`);
  copyFileSync(from, join(media, name));
  console.log(`${name} → site/assets/media (${(size / 1e6).toFixed(2)} MB)`);
}
