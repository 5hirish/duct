#!/usr/bin/env node
/**
 * Font sizes must land on Tailwind's scale.
 *
 * DESIGN.md: "The app is deliberately a two-size system... Do not invent
 * intermediate sizes... Hierarchy comes from weight and color, not a parade of
 * sizes." That rule was in the file and being broken in the file next to it —
 * `connector-tiles.css` alone had grown six sizes between 10px and 16px, and
 * one consequence was a section heading rendering SMALLER than the field label
 * inside it. Prose in a guide cannot catch that; a list of numbers can.
 *
 * A ratchet, not a big bang: files in CLEAN must stay clean, everything else is
 * reported as the known debt DESIGN.md already records. Clean a file, add it to
 * CLEAN, and it can never regress.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const STYLES = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "app", "styles");

/** Tailwind's type scale, in rem. Anything else is an invented size. */
const SCALE = new Set([
  "0.75rem", "0.875rem", "1rem", "1.125rem", "1.25rem", "1.5rem",
  "1.875rem", "2.25rem", "3rem", "3.75rem", "4.5rem", "6rem", "8rem",
]);

/** Files with zero off-scale sizes. Adding one here makes it permanent. */
const CLEAN = new Set([
  "base.css",
  "connector-tiles.css",
  "forms.css",
  "layout-grids.css",
  "mode-selector.css",
  "theme.css",
  "tokens.css",
  "typography.css",
]);

const DECL = /font-size:\s*([^;}]+)[;}]/g;

let failed = 0;
const debt = [];

for (const file of readdirSync(STYLES).filter((f) => f.endsWith(".css")).sort()) {
  const text = readFileSync(join(STYLES, file), "utf8");
  const bad = [];
  for (const m of text.matchAll(DECL)) {
    const value = m[1].trim();
    // Anything computed — var(), clamp(), calc(), inherit — is deliberate and
    // cannot be checked against a list.
    if (/^(inherit|unset|initial|revert)$/.test(value)) continue;
    if (/var\(|clamp\(|calc\(|min\(|max\(/.test(value)) continue;
    if (SCALE.has(value)) continue;
    bad.push({ value, line: text.slice(0, m.index).split("\n").length });
  }

  if (CLEAN.has(file)) {
    if (bad.length) {
      failed += bad.length;
      console.error(`✗ ${file} is on the clean list but has ${bad.length} off-scale size(s):`);
      for (const b of bad) console.error(`    line ${b.line}: font-size: ${b.value}`);
    } else {
      console.log(`✓ ${file}`);
    }
  } else if (bad.length) {
    debt.push(`${file} (${bad.length})`);
  } else {
    failed += 1;
    console.error(`✗ ${file} has no off-scale sizes — add it to CLEAN so it stays that way`);
  }
}

if (debt.length) {
  console.log(`\nknown debt, not yet enforced — see DESIGN.md "Known gaps": ${debt.join(", ")}`);
}

if (failed) {
  console.error(
    `\n${failed} problem(s). Use Tailwind's scale; carry hierarchy with weight and colour instead.`
  );
  process.exit(1);
}
console.log("\ntype scale OK");
