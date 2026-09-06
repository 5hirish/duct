#!/usr/bin/env node
/**
 * Assemble the `latest.json` that `tauri-plugin-updater` polls.
 *
 * Tauri's bundler emits, per platform, an update archive and a detached
 * minisign `.sig` beside it — but never the manifest tying them together, since
 * only the release step knows the final download URLs. This walks the downloaded
 * CI artifacts, matches each archive to its signature, and writes the manifest.
 *
 * Usage:
 *   node build-updater-manifest.mjs --version 0.3.0 --artifacts artifacts \
 *     --repo owner/name --notes-file notes.md --out latest.json
 *
 * `--notes-file` is what the updater's "a new version is available" dialog
 * shows. Without it the manifest falls back to the version string, which tells
 * a user nothing about why they should accept the update.
 *
 * Platform keys are Tauri's own (`darwin-aarch64`, `windows-x86_64`, …). A
 * platform missing from the manifest simply gets no update offered, which is
 * the right failure mode: better than pointing an installed app at an archive
 * that isn't there.
 */

import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
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
const notesFile = arg("notes-file", "");
const out = arg("out", "latest.json");

const notes =
  (notesFile && readFileSync(notesFile, "utf8").trim()) || `Duct Desktop ${version}`;

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
 * Which Tauri platform keys an update archive serves.
 *
 * Keyed on the bundle extension rather than the artifact directory name, so it
 * keeps working if the CI job names change.
 *
 * macOS returns *two* keys from one archive: the build is universal2, so the
 * same tarball is the right answer for both arches. The updater matches on an
 * exact platform key and has no notion of a fat binary, so listing only
 * `darwin-aarch64` would leave every Intel install polling forever and never
 * being offered anything — silently, which is the worst version of that bug.
 * This was genuinely arm64-only while the bundle carried a frozen CPython tree
 * (universal2 meant ~600 MB); dropping the sidecar is what made it affordable.
 */
function platformsFor(file) {
  if (file.endsWith(".app.tar.gz")) return ["darwin-aarch64", "darwin-x86_64"];
  if (file.endsWith(".nsis.zip")) return ["windows-x86_64"];
  if (file.endsWith(".AppImage")) return ["linux-x86_64"];
  return [];
}

const files = walk(artifactsDir);
const platforms = {};

for (const file of files) {
  const keys = platformsFor(file);
  if (keys.length === 0) continue;

  const sigPath = `${file}.sig`;
  if (!files.includes(sigPath)) {
    // An unsigned archive means TAURI_SIGNING_PRIVATE_KEY was missing from the
    // build. Publishing it would hand installed apps an update they must reject.
    console.error(`skipping ${file}: no signature beside it`);
    continue;
  }

  const name = file.split("/").pop();
  const entry = {
    signature: readFileSync(sigPath, "utf8").trim(),
    url: `https://github.com/${repo}/releases/download/desktop-v${version}/${encodeURIComponent(name)}`,
  };
  for (const key of keys) platforms[key] = entry;
}

if (Object.keys(platforms).length === 0) {
  console.error("no signed update artifacts found — refusing to write an empty manifest");
  process.exit(1);
}

writeFileSync(
  out,
  `${JSON.stringify(
    {
      version,
      notes,
      pub_date: new Date().toISOString(),
      platforms,
    },
    null,
    2,
  )}\n`,
);

console.error(`wrote ${out} for: ${Object.keys(platforms).join(", ")}`);
