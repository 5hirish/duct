#!/usr/bin/env node
/**
 * Refreeze the sidecar when it is older than the backend it would ship.
 *
 * `bundle.resources` copies backend/dist/duct-sidecar into the .app verbatim at
 * build time, and PyInstaller is not incremental — so a backend change followed
 * by a plain `npm run build` silently ships the previous freeze. The failure
 * surfaces much later as a running app whose Python is weeks old, which reads
 * as an app bug rather than a stale artifact.
 *
 * Since the sidecar became optional — the official build ships without one and
 * talks to the hosted API — the two failure modes are graded differently:
 *
 *   no freeze at all  → a note, exit 0. That is the official build's normal
 *                       state, and on `dev` it just means the local backend
 *                       path is not being exercised today. `--force` freezes
 *                       anyway, which is how the first one gets made.
 *   a STALE freeze    → run PyInstaller here, in the same command, and only
 *                       fail if that fails. This used to exit 1 with the
 *                       refreeze command to paste, which is the same three
 *                       minutes plus a context switch: nobody who hits this
 *                       wants the old Python, they want the build they asked
 *                       for. Refusing also made the freeze easy to skip by
 *                       rebuilding the shell alone, which is the failure the
 *                       check exists to prevent.
 *
 * Only the build paths that actually ship a sidecar run this — see the
 * `pre*` hooks in package.json.
 *
 * Set DUCT_SKIP_SIDECAR_CHECK=1 to bundle a known-stale freeze deliberately.
 */

import { spawnSync } from "node:child_process";
import { readdirSync, statSync, existsSync, renameSync, rmSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const BACKEND = join(HERE, "..", "..", "backend");
const DIST = join(BACKEND, "dist");

/** Matches the COLLECT name in duct_sidecar.spec and SIDECAR_* in sidecar.rs. */
const SIDECAR_DIR = "duct-sidecar";
const SIDECAR_BIN = process.platform === "win32" ? "duct-sidecar.exe" : "duct-sidecar";

const FROZEN_DIR = join(DIST, SIDECAR_DIR);
const FROZEN = join(FROZEN_DIR, SIDECAR_BIN);
/** PyInstaller's output lands here first, so the live directory is never its to delete. */
const STAGING = join(DIST, ".staging");
/** The freeze a swap displaces, kept until nothing is running from it. */
const SUPERSEDED_PREFIX = ".superseded-";

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

const REFREEZE = `cd backend && poetry run pyinstaller duct_sidecar.spec --noconfirm`;

/** Whether any process still holds this binary open. Best effort: no lsof, no answer. */
function inUse(binary) {
  if (!existsSync(binary)) return false;
  const { status, error } = spawnSync("lsof", ["-t", "--", binary], { stdio: "ignore" });
  return error ? false : status === 0;
}

/** Drop every superseded freeze nothing is running from. ~480 MB each. */
function sweepSuperseded() {
  let entries;
  try {
    entries = readdirSync(DIST, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (!entry.isDirectory() || !entry.name.startsWith(SUPERSEDED_PREFIX)) continue;
    const dir = join(DIST, entry.name);
    if (inUse(join(dir, SIDECAR_BIN))) continue;
    rmSync(dir, { recursive: true, force: true });
  }
}

/**
 * Freeze into a staging directory, then swap it in.
 *
 * A dev build ships no sidecar of its own — `tauri.dev.conf.json` sets no
 * `bundle.resources` — so `sidecar.rs` resolves this directory at *runtime*,
 * which means a running app is executing these exact files. PyInstaller starts
 * by deleting its output directory, so freezing in place pulls the binary and
 * every dylib out from under that process. What the user sees is "Duct's local
 * backend stopped responding", which reads as an app bug and is not one; it
 * cost an afternoon on 2026-09-17. A rename leaves the running process intact,
 * because its open handles follow the directory it is holding.
 */
function refreeze() {
  sweepSuperseded();
  rmSync(STAGING, { recursive: true, force: true });

  // Default --workpath on purpose: PyInstaller's analysis cache lives in
  // backend/build, and redirecting it turns every refreeze into a cold one.
  const { status, signal, error } = spawnSync(
    "poetry",
    ["run", "pyinstaller", "duct_sidecar.spec", "--noconfirm", "--distpath", STAGING],
    { cwd: BACKEND, stdio: "inherit" },
  );
  if (status !== 0) {
    // A failed spawn and a Ctrl-C both leave `status` null, so neither can be
    // reported as an exit code.
    const why = error ? error.message : signal ? `killed by ${signal}` : `exit ${status}`;
    console.error(
      `\nRefreezing the sidecar failed (${why}).\n\n` +
        `The freeze in backend/dist is untouched, so a running app keeps working.\n` +
        `Fix it there and rerun, or set DUCT_SKIP_SIDECAR_CHECK=1 to bundle the\n` +
        `stale freeze deliberately:\n\n  ${REFREEZE}\n`,
    );
    return false;
  }

  if (existsSync(FROZEN_DIR)) {
    renameSync(FROZEN_DIR, join(DIST, `${SUPERSEDED_PREFIX}${Date.now()}`));
  }
  renameSync(join(STAGING, SIDECAR_DIR), FROZEN_DIR);
  rmSync(STAGING, { recursive: true, force: true });
  sweepSuperseded();
  return true;
}

const force = process.argv.includes("--force");

if (process.env.DUCT_SKIP_SIDECAR_CHECK === "1" && !force) {
  console.log("sidecar freshness check skipped (DUCT_SKIP_SIDECAR_CHECK=1)");
  process.exit(0);
}

if (!existsSync(FROZEN) && !force) {
  console.log(
    `No frozen sidecar at backend/dist/duct-sidecar — this build talks to the hosted API.\n` +
      `To exercise the local backend instead:\n\n  npm --prefix desktop run sidecar\n`,
  );
  process.exit(0);
}

const frozenAt = existsSync(FROZEN) ? statSync(FROZEN).mtimeMs : 0;
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

const stale = newest.path && newest.mtime > frozenAt;

if (stale && frozenAt) {
  const hours = (newest.mtime - frozenAt) / 3_600_000;
  const plural = (n, unit) => `${n} ${unit}${n === 1 ? "" : "s"}`;
  const age = hours >= 48 ? plural(Math.round(hours / 24), "day") : plural(Math.max(1, Math.round(hours)), "hour");
  // Local time, so it lines up with what `stat` and Finder show.
  const when = (ms) => new Date(ms).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  console.log(
    `\nThe frozen sidecar is ${age} older than the backend it would ship.\n\n` +
      `  frozen:  backend/dist/duct-sidecar/duct-sidecar  (${when(frozenAt)})\n` +
      `  newer:   backend/${relative(BACKEND, newest.path)}  (${when(newest.mtime)})\n\n` +
      `Refreezing before the bundle copies it — around three minutes.\n`,
  );
}

if (stale || force) {
  process.exit(refreeze() ? 0 : 1);
}

console.log("sidecar freeze is newer than the backend — ok");
