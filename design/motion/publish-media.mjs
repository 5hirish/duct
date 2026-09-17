// Moves a finished render into the site. Renders are committed, and a 2-3 MB
// video is a real cost to the repository, so this is a deliberate step after
// looking at the output, never part of `render:film`.
import { copyFileSync, mkdirSync, statSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const media = join(here, "..", "..", "site", "assets", "media");
mkdirSync(media, { recursive: true });

// A phone shows the film about 340px wide, so the site plays a 720px cut
// there (index.html swaps the source under 860px). Encoded here from the
// full render with ffmpeg, which the film pipeline already needs.
const PHONE = [
  ["demo-phone.mp4", ["-c:v", "libx264", "-preset", "slow", "-crf", "28", "-profile:v", "main", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "64k"]],
  ["demo-phone.webm", ["-c:v", "libvpx-vp9", "-crf", "40", "-b:v", "0", "-row-mt", "1", "-deadline", "good", "-cpu-used", "2", "-c:a", "libopus", "-b:a", "48k"]],
];
for (const [name, codec] of PHONE) {
  execFileSync("ffmpeg", ["-v", "error", "-y", "-i", join(here, "out", "demo.mp4"), "-vf", "scale=720:-2", ...codec, join(here, "out", name)], { stdio: "inherit" });
}

// The plan budgeted a silent film; the sound adds ~0.3 MB to each, so the
// webm line moved from 2 to 2.5 MB rather than crushing the picture. The
// phone cuts came in around 0.6 MB; the budget leaves room, not slack.
const LIMIT_BYTES = { "demo.mp4": 3_000_000, "demo.webm": 2_500_000, "demo-phone.mp4": 800_000, "demo-phone.webm": 800_000, "demo-poster.webp": 80_000 };
for (const [name, limit] of Object.entries(LIMIT_BYTES)) {
  const from = join(here, "out", name);
  const size = statSync(from).size;
  if (size > limit) throw new Error(`${name} is ${(size / 1e6).toFixed(2)} MB, over the ${(limit / 1e6).toFixed(1)} MB budget the plan set`);
  copyFileSync(from, join(media, name));
  console.log(`${name} → site/assets/media (${(size / 1e6).toFixed(2)} MB)`);
}
