#!/usr/bin/env node
/**
 * Build the body of a desktop GitHub release.
 *
 *   node .github/scripts/release-notes.mjs --version 0.4.0 --artifacts artifacts
 *
 * Prints Markdown on stdout. Three parts, in the order a reader needs them:
 *
 *   1. What changed — the CHANGELOG.md section for this version, verbatim.
 *   2. How to install — per platform, including the macOS Gatekeeper step,
 *      which is the single most common "the download is broken" report.
 *   3. What is in the release — the assets, with SHA-256 sums.
 *
 * The release page is also a public, indexed page, so it is worth more than
 * "Automated build from <sha>." — which is what this replaced.
 *
 * A missing CHANGELOG section is not fatal. A release that cannot be cut is a
 * worse outcome than a release with thin notes, so it degrades to a pointer at
 * the compare view and carries on.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { createHash } from "node:crypto";
import { join, basename } from "node:path";

const args = new Map();
for (let i = 2; i < process.argv.length; i += 2) {
  args.set(process.argv[i].replace(/^--/, ""), process.argv[i + 1]);
}

const version = args.get("version");
const artifactsDir = args.get("artifacts") || "artifacts";
const repo = args.get("repo") || "5hirish/duct";
const changelogPath = args.get("changelog") || "CHANGELOG.md";

if (!version) {
  console.error("usage: release-notes.mjs --version X.Y.Z [--artifacts DIR] [--repo OWNER/NAME]");
  process.exit(1);
}

/** The body of the `## [version]` section, up to the next `## ` heading. */
function changelogSection(v) {
  let text;
  try {
    text = readFileSync(changelogPath, "utf8");
  } catch {
    return null;
  }
  // Tolerates "## [0.4.0]", "## 0.4.0", and any trailing date or note.
  const start = new RegExp(`^## \\[?${v.replace(/\./g, "\\.")}\\]?.*$`, "m");
  const from = text.search(start);
  if (from === -1) return null;
  const rest = text.slice(from);
  const nextHeading = rest.slice(1).search(/^## /m);
  const body = nextHeading === -1 ? rest : rest.slice(0, nextHeading + 1);
  // Drop the heading line itself (the release title already carries the
  // version), then the trailing link-reference definitions. The last section in
  // the file has no `## ` after it, so it otherwise swallows the
  // `[0.4.0]: https://...` block at the bottom of CHANGELOG.md.
  const lines = body.split("\n").slice(1);
  while (lines.length && /^(\s*$|\[[^\]]+\]:\s)/.test(lines[lines.length - 1])) {
    lines.pop();
  }
  return lines.join("\n").trim() || null;
}

function walk(dir) {
  const out = [];
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const entry of entries) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) out.push(...walk(path));
    else out.push(path);
  }
  return out;
}

function human(bytes) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

/** Installer bundles only — signatures and update archives are noise here. */
function isInstaller(file) {
  return /\.(dmg|AppImage|deb|rpm|msi|exe)$/.test(file);
}

const parts = [];

// --- 1. What changed -------------------------------------------------------
const section = changelogSection(version);
parts.push("## What changed\n");
parts.push(
  section ||
    `See the [full commit list](https://github.com/${repo}/commits/desktop-v${version}) — ` +
      `this version has no \`CHANGELOG.md\` section yet.`,
);

// --- 2. How to install -----------------------------------------------------
parts.push(`
## Install

Duct Desktop runs the backend locally as a sidecar. No account is required and
no data leaves your machine — you bring your own model API key, stored in the
OS keychain.

**macOS** (Apple silicon) — download the \`.dmg\`, then drag Duct to
Applications. On first launch macOS may say the app cannot be verified; open it
once with right-click → Open, or clear the quarantine flag:

\`\`\`bash
xattr -dr com.apple.quarantine /Applications/Duct.app
\`\`\`

**Windows** — download and run the \`.exe\` installer. SmartScreen may warn on a
new signing identity; choose *More info* → *Run anyway*.

**Linux** — download the \`.AppImage\`, then:

\`\`\`bash
chmod +x Duct_${version}_amd64.AppImage && ./Duct_${version}_amd64.AppImage
\`\`\`

Existing installs update themselves — the app polls \`latest.json\` in this
release and verifies the signature before applying anything.`);

// --- 3. What is in the release --------------------------------------------
const installers = walk(artifactsDir).filter(isInstaller).sort();
if (installers.length) {
  parts.push(`
## Downloads

| File | Size | SHA-256 |
|---|---|---|`);
  for (const file of installers) {
    const buf = readFileSync(file);
    const sha = createHash("sha256").update(buf).digest("hex");
    parts.push(`| \`${basename(file)}\` | ${human(buf.length)} | \`${sha}\` |`);
  }
}

parts.push(`
---

Duct is open source under the [MIT licence](https://github.com/${repo}/blob/main/LICENSE).
Found a bug? [Open an issue](https://github.com/${repo}/issues/new/choose).
Found a vulnerability? [Report it privately](https://github.com/${repo}/security/advisories/new).`);

process.stdout.write(parts.join("\n") + "\n");
