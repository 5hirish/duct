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
 * Which Tauri platform key an update archive belongs to.
 *
 * Keyed on the bundle extension rather than the artifact directory name, so it
 * keeps working if the CI job names change. macOS is arm64-only for now: the
 * sidecar is a frozen CPython tree, and a universal2 build roughly doubles its
 * native libraries (~600 MB) — see the size notes in `backend/duct_sidecar.spec`.
 * Intel Macs therefore get no update offered rather than a broken one.
 */
function platformFor(file) {
  if (file.endsWith(".app.tar.gz")) return "darwin-aarch64";
  if (file.endsWith(".nsis.zip")) return "windows-x86_64";
  if (file.endsWith(".AppImage")) return "linux-x86_64";
  return null;
}

const files = walk(artifactsDir);
const platforms = {};

for (const file of files) {
  const platform = platformFor(file);
  if (!platform) continue;

  const sigPath = `${file}.sig`;
  if (!files.includes(sigPath)) {
    // An unsigned archive means TAURI_SIGNING_PRIVATE_KEY was missing from the
    // build. Publishing it would hand installed apps an update they must reject.
    console.error(`skipping ${file}: no signature beside it`);
    continue;
  }

  const name = file.split("/").pop();
  platforms[platform] = {
    signature: readFileSync(sigPath, "utf8").trim(),
    url: `https://github.com/${repo}/releases/download/desktop-v${version}/${encodeURIComponent(name)}`,
  };
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
