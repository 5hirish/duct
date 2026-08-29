#!/usr/bin/env node
/**
 * Refuse to bundle a sidecar older than the backend it was frozen from.
 *
 * `bundle.resources` copies backend/dist/duct-sidecar into the .app verbatim at
 * build time, and PyInstaller is not incremental — so a backend change followed
 * by a plain `npm run build` silently ships the previous freeze. The failure
 * surfaces much later as a running app whose Python is weeks old, which reads
 * as an app bug rather than a stale artifact.
 *
 * CI refreezes on every run (see .github/workflows/desktop-release.yml), so
 * this passes trivially there — it also guards against those steps being
 * reordered.
 *
 * Set DUCT_SKIP_SIDECAR_CHECK=1 to bundle a known-stale freeze deliberately.
 */

import { readdirSync, statSync, existsSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const BACKEND = join(HERE, "..", "..", "backend");
const FROZEN = join(BACKEND, "dist", "duct-sidecar", "duct-sidecar");

/** Directories that never reach the freeze, or that the freeze itself writes. */
const SKIP_DIRS = new Set([
  ".venv", "dist", "build", "__pycache__", ".pytest_cache", ".ruff_cache", "data", "tests",
]);
/** Non-.py inputs the spec pulls in, or that change what gets frozen. */
const EXTRA_FILES = ["duct_sidecar.spec", "pyproject.toml", "poetry.lock", "alembic.ini"];

function newestUnder(dir, acc = { path: null, mtime: 0 }) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return acc;
  }
  for (const entry of entries) {
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      newestUnder(join(dir, entry.name), acc);
    } else if (entry.name.endsWith(".py")) {
      const { mtimeMs } = statSync(join(dir, entry.name));
      if (mtimeMs > acc.mtime) {
        acc.mtime = mtimeMs;
        acc.path = join(dir, entry.name);
      }
    }
  }
  return acc;
}

const REFREEZE = "cd backend && poetry run pyinstaller duct_sidecar.spec --noconfirm";

if (process.env.DUCT_SKIP_SIDECAR_CHECK === "1") {
  console.log("sidecar freshness check skipped (DUCT_SKIP_SIDECAR_CHECK=1)");
  process.exit(0);
}

if (!existsSync(FROZEN)) {
  console.error(
    `\nNo frozen sidecar at backend/dist/duct-sidecar.\n` +
      `The bundle copies that directory verbatim, so the build would fail or ship a broken app.\n\n  ${REFREEZE}\n`,
  );
  process.exit(1);
}

const frozenAt = statSync(FROZEN).mtimeMs;
const newest = newestUnder(BACKEND);
for (const name of EXTRA_FILES) {
  const path = join(BACKEND, name);
  if (!existsSync(path)) continue;
  const { mtimeMs } = statSync(path);
  if (mtimeMs > newest.mtime) {
    newest.mtime = mtimeMs;
    newest.path = path;
  }
}

if (newest.path && newest.mtime > frozenAt) {
  const hours = (newest.mtime - frozenAt) / 3_600_000;
  const plural = (n, unit) => `${n} ${unit}${n === 1 ? "" : "s"}`;
  const age = hours >= 48 ? plural(Math.round(hours / 24), "day") : plural(Math.max(1, Math.round(hours)), "hour");
  // Local time, so it lines up with what `stat` and Finder show.
  const when = (ms) => new Date(ms).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  console.error(
    `\nThe frozen sidecar is ${age} older than the backend it would ship.\n\n` +
      `  frozen:  backend/dist/duct-sidecar/duct-sidecar  (${when(frozenAt)})\n` +
      `  newer:   backend/${relative(BACKEND, newest.path)}  (${when(newest.mtime)})\n\n` +
      `Refreeze first — the app copies the directory at build time, so rebuilding\n` +
      `the shell alone re-copies the same stale Python:\n\n  ${REFREEZE}\n`,
  );
  process.exit(1);
}

console.log("sidecar freeze is newer than the backend — ok");
