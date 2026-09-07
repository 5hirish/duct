#!/usr/bin/env node
/**
 * Assemble the `downloads.json` the website's /download page reads.
 *
 * The installers carry their version in the filename (`Duct_0.4.0_aarch64.dmg`),
 * so a static page cannot link to them directly — every release would change
 * the href. GitHub does serve one stable URL per release *asset name* though:
 *
 *   https://github.com/<repo>/releases/latest/download/downloads.json
 *
 * always resolves to the newest release. So the page fetches this one fixed
 * file and reads the real installer URLs out of it. That is the same trick
 * `latest.json` already plays for the updater, and it keeps the site deploy and
 * the desktop release completely decoupled: shipping a new version needs no
 * site change at all.
 *
 * Sibling of `build-updater-manifest.mjs`, deliberately not merged into it.
 * That file describes *update archives* for a machine; this one describes
 * *installers* for a person. They select different files out of the same
 * directory and are read by different consumers.
 *
 * Usage:
 *   node build-downloads-manifest.mjs --version 0.4.0 --artifacts artifacts \
 *     --repo owner/name --out downloads.json
 */

import { readdirSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

function arg(name, fallback = null) {
  const i = process.argv.indexOf(`--${name}`);
  if (i === -1 || i === process.argv.length - 1) {
    if (fallback !== null) return fallback;
    throw new Error(`missing required --${name}`);
  }
  return process.argv[i + 1];
}

const version = arg("version");
const artifactsDir = arg("artifacts");
const repo = arg("repo");
const out = arg("out", "downloads.json");

/** Every file under the artifacts tree, recursively. */
function walk(dir) {
  const found = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) found.push(...walk(path));
    else found.push(path);
  }
  return found;
}

/**
 * Which download slot a file fills, or null if it is not something a person
 * installs.
 *
 * Order matters against the updater's own artifacts, which sit in the same
 * tree: `.nsis.zip` and `.app.tar.gz` are update archives, not installers, and
 * handing one to a user gets them a file their OS will not open. Matching on
 * the installer extensions positively — rather than excluding the archives —
 * means a new updater artifact type cannot leak in here by default.
 */
function slotFor(file) {
  if (file.endsWith(".dmg")) return "macos";
  if (file.endsWith("-setup.exe")) return "windows";
  if (file.endsWith(".AppImage")) return "linux-appimage";
  if (file.endsWith(".deb")) return "linux-deb";
  return null;
}

const platforms = {};

for (const file of walk(artifactsDir)) {
  const slot = slotFor(file);
  if (!slot) continue;

  const filename = file.split("/").pop();
  platforms[slot] = {
    filename,
    size: statSync(file).size,
    url: `https://github.com/${repo}/releases/download/desktop-v${version}/${encodeURIComponent(filename)}`,
  };
}

if (Object.keys(platforms).length === 0) {
  // The page falls back to the releases listing when a slot is missing, so an
  // empty manifest would publish a download page that silently offers nothing.
  console.error("no installers found — refusing to write an empty downloads.json");
  process.exit(1);
}

writeFileSync(
  out,
  `${JSON.stringify(
    {
      version,
      published: new Date().toISOString(),
      release_url: `https://github.com/${repo}/releases/tag/desktop-v${version}`,
      platforms,
    },
    null,
    2,
  )}\n`,
);

console.error(`wrote ${out} for: ${Object.keys(platforms).join(", ")}`);
