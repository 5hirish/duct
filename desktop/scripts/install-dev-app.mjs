#!/usr/bin/env node
// Put the dev build where macOS can find it.
//
// Nothing in `tauri.conf.json` decides where an app lives — Tauri produces a
// .app (and a .dmg for real distribution); *installing* it is the user dragging
// it to /Applications. So a dev bundle sitting in `target/debug/bundle/macos/`
// is invisible to Spotlight and Launchpad, and the only way to launch it is by
// path.
//
// /Applications, not ~/Applications: Spotlight indexes the former and — on at
// least some machines, this one included — not the latter, so a copy in the
// home folder shows up in Launchpad but never in a Cmd-Space search, which is
// the whole point. /Applications is group-writable by admin users, so this
// needs no sudo.
//
// `ditto`, not `cp -R`: it preserves the bundle's symlinks, resource forks and
// extended attributes. `cp -R` can flatten framework symlinks into copies and
// produce a bundle that no longer launches.
//
// Wired as `postbuild:dev`, so every dev build refreshes the installed copy
// instead of leaving a stale one to confuse you later. Never fatal: failing to
// install a convenience copy must not fail a build that otherwise succeeded.

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const APP_NAME = "Duct Dev.app";
const source = resolve(here, "..", "src-tauri", "target", "debug", "bundle", "macos", APP_NAME);
const target = join("/Applications", APP_NAME);

if (process.platform !== "darwin") {
  // Linux .desktop entries and the Windows Start menu are written by their
  // installers (deb/AppImage, NSIS), not by a dev build.
  process.exit(0);
}

if (!existsSync(source)) {
  console.warn(`No dev bundle at ${source} — skipping the /Applications install.`);
  process.exit(0);
}

try {
  execFileSync("ditto", [source, target], { stdio: "inherit" });
  console.log(`Installed ${APP_NAME} to /Applications — searchable in Spotlight.`);
} catch (err) {
  console.warn(
    `Could not install ${APP_NAME} to /Applications: ${err.message}\n` +
      "The build is fine — launch it from the bundle path, or copy it by hand.",
  );
}
