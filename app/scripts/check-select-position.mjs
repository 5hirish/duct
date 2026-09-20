// An icon-only Select must position itself with `popper`.
//
// Radix has two positioning modes. The default, `item-aligned`, places the
// menu by aligning the selected item over the trigger's `<SelectValue>` — so
// it measures that node, and `position()` returns early when there isn't one.
// Nothing throws and nothing logs: the menu opens with its wrapper left at the
// static offset of a fixed element, which lands off the bottom-left corner of
// the viewport. It is open, it is focusable, and no option can be clicked.
//
// On 2026-09-20 that was the language switcher in the `/start` header. The
// trigger renders a globe and no `<SelectValue>`, so clicking it appeared to
// do nothing at all. Every other valueless trigger in the tree — the four
// composer dials — already passed `position="popper"`, which is what makes
// this worth a check rather than a comment: the rule was known and one call
// site missed it, silently, in a way no test and no console message caught.
//
// A trigger that renders `<SelectValue>` is unaffected and not examined.
//
// Run: node scripts/check-select-position.mjs

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SRC_DIR = fileURLToPath(new URL("../src/", import.meta.url));
const EXTENSIONS = [".jsx", ".tsx"];

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (EXTENSIONS.some((ext) => entry.endsWith(ext))) out.push(path);
  }
  return out;
}

const TRIGGER = /<SelectTrigger\b[\s\S]*?<\/SelectTrigger>/g;

let checked = 0;
let failed = 0;

for (const file of walk(SRC_DIR)) {
  const source = readFileSync(file, "utf8");
  if (!source.includes("<SelectTrigger")) continue;

  for (const match of source.matchAll(TRIGGER)) {
    // A value node is present, so item-aligned has what it needs to measure —
    // but only if it is rendered unconditionally. `{compact ? null :
    // <SelectValue />}` is exactly the shape that caused this bug, and a
    // plain substring test reads it as safe, so drop any conditional
    // expression before deciding.
    const unconditional = match[0].replace(/\{[^{}]*<SelectValue[\s\S]*?\}/g, (expr) =>
      /\?|&&|\|\||null/.test(expr) ? "" : expr
    );
    if (unconditional.includes("<SelectValue")) continue;
    checked++;

    const line = source.slice(0, match.index).split("\n").length;
    const where = `${relative(SRC_DIR, file)}:${line}`;

    // The content belongs to the same <Select>, so it is the next one after
    // this trigger closes.
    const after = source.slice(match.index + match[0].length);
    const content = after.match(/<SelectContent\b[^>]*>/);
    if (!content) {
      failed++;
      console.log(`✗ ${where} — valueless trigger with no <SelectContent> after it`);
      continue;
    }
    if (content[0].includes('"popper"')) {
      console.log(`✓ ${where} — icon-only trigger, popper positioning`);
    } else {
      failed++;
      console.log(
        `✗ ${where} — icon-only trigger (no <SelectValue>) whose <SelectContent> does not set position="popper".\n` +
          `    item-aligned needs a value node to measure and silently leaves the menu off-screen.`
      );
    }
  }
}

console.log(
  failed
    ? `\n${failed} of ${checked} icon-only Select(s) would open off-screen`
    : `\n${checked} icon-only Select(s), all positioned with popper`
);
process.exit(failed ? 1 : 0);
