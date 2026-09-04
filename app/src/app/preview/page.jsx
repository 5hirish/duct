import { readFile } from "node:fs/promises";
import path from "node:path";

import { notFound } from "next/navigation";

import { parseCanon } from "./canon";

// Never ships. `next build` runs with NODE_ENV=production, so the guard is
// statically true there and the route 404s.
//
// The import is dynamic and sits *after* the guard on purpose: a static one at
// the top of the file pulls the shell, every scene, and every component a
// scene imports into the build whether or not the route can be reached. The
// route 404ing is not the same as the code not being there.
export const metadata = { robots: { index: false, follow: false } };

/**
 * The canon rules, read from DESIGN.md at request time.
 *
 * A server component is the only place that can reach the file, which is the
 * reason the catalogue's rule text is passed down as a prop rather than
 * imported. Request time rather than build time is deliberate: editing
 * DESIGN.md and refreshing shows the new rule, so the doc can be revised with
 * the rendered result in front of you.
 *
 * Failure is non-fatal. The catalogue still renders its examples with the
 * rules missing, because a harness that 500s when a doc moves is a harness
 * nobody trusts.
 */
async function loadCanon() {
  try {
    return parseCanon(await readFile(path.join(process.cwd(), "DESIGN.md"), "utf8"));
  } catch {
    return [];
  }
}

export default async function PreviewPage() {
  if (process.env.NODE_ENV === "production") notFound();
  const { default: PreviewShell } = await import("./PreviewShell");
  return <PreviewShell canon={await loadCanon()} />;
}
