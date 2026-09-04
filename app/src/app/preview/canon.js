// The canon table in DESIGN.md, parsed.
//
// DESIGN.md is already the design system — it holds one canonical pattern per
// job, what to retire, and why. What it does not have is pictures. The
// catalogue mode of /preview supplies those, and it reads the rules FROM the
// doc rather than restating them.
//
// That direction is the whole point. This repo has been bitten twice by a
// second copy of a rule: the root AGENTS.md that still named deleted modules,
// and `.claude/rules/landing-pages.md` telling agents to write a canonical URL
// the site does not use. A catalogue that retyped "a card is rounded-xl border
// bg-card p-5" would be the third. Parse it, and the doc cannot be out of date
// with the screen — there is only one of it.
//
// Pure: takes markdown text, returns rows. The filesystem read happens in the
// route's server component, which is the only place that can do it.

const SECTION = "## Canon — one pattern per job";

/** "Empty state (whole surface)" -> "canon-empty-state-whole-surface" */
export function canonId(job) {
  return (
    "canon-" +
    job
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
  );
}

/**
 * Rows of `{ id, job, canonical, retire }` from DESIGN.md's canon table.
 *
 * Cells are returned as raw markdown; `CanonText` in the shell renders the
 * inline `code` and **bold** that the rules lean on. Splitting on "|" is safe
 * because no cell contains an escaped pipe — asserted below rather than
 * assumed, since a rule that silently loses its second half is worse than one
 * that fails loudly.
 */
export function parseCanon(markdown) {
  const start = markdown.indexOf(SECTION);
  if (start === -1) return [];
  // The table ends at the section's closing rule.
  const rest = markdown.slice(start + SECTION.length);
  const end = rest.indexOf("\n---");
  const body = end === -1 ? rest : rest.slice(0, end);

  const rows = [];
  for (const line of body.split("\n")) {
    const t = line.trim();
    if (!t.startsWith("|")) continue;
    if (/^\|[\s|:-]+\|$/.test(t)) continue; // the |---|---|---| separator
    const cells = t.slice(1, t.endsWith("|") ? -1 : undefined).split("|");
    if (cells.length < 3) continue;
    const [job, canonical, retire] = cells.map((c) => c.trim());
    if (!job || job === "Job") continue; // the header row
    rows.push({ id: canonId(job), job, canonical, retire });
  }
  return rows;
}
