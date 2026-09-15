#!/usr/bin/env node
/**
 * Token contrast guard.
 *
 * The 2026-09-06 review measured every token pair by hand and found three that
 * were defined, correct, and unreachable — a mapping was missing, so the class
 * was never generated and nobody could tell by reading the file. The fix was
 * three lines; the reason it survived six weeks is that nothing checked.
 *
 * So this is that check. It parses the real token files, does the WCAG maths on
 * the real oklch values, and fails the build when a pair the app actually paints
 * drops below its threshold — including the "is the utility even generated"
 * case, which is a grep over `@theme inline` rather than a colour calculation.
 *
 * Run: `npm run check:contrast` (part of `check:parity`).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const STYLES = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "app", "styles");

/** WCAG 2.2 1.4.3 / 1.4.11. Large text is 24px, or 18.66px bold. */
const TEXT = 4.5;
const LARGE_TEXT = 3;
const NON_TEXT = 3;

// --- colour -----------------------------------------------------------------

/** oklch(L C H [/ A]) → [r, g, b] in 0..1 sRGB, plus alpha. */
function parseOklch(value) {
  const m = /^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*(?:\/\s*([\d.]+)(%?)\s*)?\)$/.exec(value.trim());
  if (!m) return null;
  const [, L, C, H, A, pct] = m;
  const alpha = A === undefined ? 1 : pct ? Number(A) / 100 : Number(A);
  const h = (Number(H) * Math.PI) / 180;
  const [l, a, b] = [Number(L), Number(C) * Math.cos(h), Number(C) * Math.sin(h)];

  // Oklab → LMS → linear sRGB (Björn Ottosson's matrices).
  const l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s_ = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;

  const lin = [
    4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
    -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
    -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_,
  ];
  return { lin: lin.map((c) => Math.min(1, Math.max(0, c))), alpha };
}

function parseHex(value) {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(value.trim());
  if (!m) return null;
  const h = m[1].length === 3 ? [...m[1]].map((c) => c + c).join("") : m[1];
  const srgb = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
  return { lin: srgb.map(toLinear), alpha: 1 };
}

const toLinear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);

function parseColor(value) {
  return parseOklch(value) ?? parseHex(value);
}

/** Composite a translucent colour over an opaque one, in linear light. */
function over(fg, bg) {
  if (fg.alpha >= 1) return fg;
  return { lin: fg.lin.map((c, i) => c * fg.alpha + bg.lin[i] * (1 - fg.alpha)), alpha: 1 };
}

const luminance = ({ lin: [r, g, b] }) => 0.2126 * r + 0.7152 * g + 0.0722 * b;

function contrast(fg, bg) {
  const a = luminance(over(fg, bg));
  const b = luminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/** `bg-x/15` — a tint of `x` laid over the page, which is what the variants paint. */
const tint = (color, pct, base) => over({ ...color, alpha: pct / 100 }, base);

// --- token parsing ----------------------------------------------------------

const tokensCss = readFileSync(join(STYLES, "tokens.css"), "utf8");
const themeCss = readFileSync(join(STYLES, "theme.css"), "utf8");

/**
 * Custom properties declared inside one block, named by its opening selector.
 * Anchored to the start of a line: theme.css mentions `.dark` in its header
 * comment, and a bare `indexOf` happily parsed the comment's following brace —
 * which is `@theme inline`, so the dark theme silently came back as the light
 * one and every dark reading matched its light twin to two decimals.
 */
function block(css, selector) {
  const at = new RegExp(`^${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\{`, "m").exec(css);
  if (!at) throw new Error(`no ${selector} block`);
  const open = css.indexOf("{", at.index);
  let depth = 0;
  let end = open;
  for (; end < css.length; end += 1) {
    if (css[end] === "{") depth += 1;
    else if (css[end] === "}" && (depth -= 1) === 0) break;
  }
  const out = {};
  for (const [, name, value] of css.slice(open, end).matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    out[name] = value.trim();
  }
  return out;
}

const light = { ...block(tokensCss, ":root"), ...{} };
const dark = { ...light, ...block(themeCss, ".dark") };

function color(theme, name) {
  const raw = theme[name];
  if (!raw) throw new Error(`token ${name} is not defined`);
  const parsed = parseColor(raw);
  if (!parsed) throw new Error(`token ${name} is not a colour this script can read: ${raw}`);
  return parsed;
}

// --- the pairs the app actually paints ---------------------------------------

/**
 * Each entry is [label, foreground, background, threshold]. Backgrounds given
 * as `["token", tintPercent]` composite that token over `--background` first,
 * which is what `bg-destructive/10` does on screen.
 */
const PAIRS = [
  ["body text", "--foreground", "--background", TEXT],
  ["secondary text", "--muted-foreground", "--background", TEXT],
  ["card text", "--card-foreground", "--card", TEXT],
  ["default Button", "--primary-foreground", "--primary", TEXT],
  ["link / primary as text", "--primary", "--background", TEXT],
  ["solid destructive", "--destructive-foreground", "--destructive", TEXT],
  ["solid success", "--success-foreground", "--success", TEXT],
  ["solid warning", "--warning-foreground", "--warning", TEXT],
  ["solid info", "--info-foreground", "--info", TEXT],
  ["solid brand", "--brand-foreground", "--brand", TEXT],
  ["destructive as text", "--destructive", "--background", TEXT],
  ["success as text", "--success", "--background", TEXT],
  ["warning as text", "--warning", "--background", TEXT],
  ["info as text", "--info", "--background", TEXT],
  ["brand as text", "--brand", "--background", TEXT],
  ["sidebar text", "--sidebar-foreground", "--sidebar", TEXT],
  ["popover text", "--popover-foreground", "--popover", TEXT],
  ["secondary Button", "--secondary-foreground", "--secondary", TEXT],
  // The tinted variants: Button/Badge destructive|success|warning paint the
  // status colour at 10% (20% in dark) and set the text to the same hue.
  ["destructive Badge", "--destructive", ["--destructive", 10], LARGE_TEXT],
  ["success Badge", "--success", ["--success", 10], LARGE_TEXT],
  ["warning Badge", "--warning", ["--warning", 10], LARGE_TEXT],
  ["info Badge", "--info", ["--info", 10], LARGE_TEXT],
  // Boundaries. WCAG 1.4.11 wants 3:1 for the edge that identifies a control;
  // the shared `--border`/`--input` pair sat at 1.27:1 in light. `--border`
  // itself is deliberately absent from this list: it separates things already
  // distinguishable by position, which 1.4.11 does not cover, and holding a
  // card divider to 3:1 would box the whole app in.
  ["control boundary", "--control", "--background", NON_TEXT],
  ["control boundary on card", "--control", "--card", NON_TEXT],
  ["focus ring", "--ring", "--background", NON_TEXT],
  ["chart 1", "--chart-1", "--background", NON_TEXT],
  ["chart 2", "--chart-2", "--background", NON_TEXT],
  ["chart 3", "--chart-3", "--background", NON_TEXT],
  ["chart 4", "--chart-4", "--background", NON_TEXT],
  ["chart 5", "--chart-5", "--background", NON_TEXT],
];

/**
 * Utilities the app writes that only exist if `@theme inline` names them. This
 * is the C1 class of defect: the value is right, the class is never generated,
 * and the element silently inherits the page colour.
 */
const MUST_MAP = [
  "--color-destructive-foreground",
  "--color-success-foreground",
  "--color-warning-foreground",
  "--color-destructive",
  "--color-success",
  "--color-warning",
  "--color-border",
  "--color-input",
  "--color-control",
  "--color-ring",
  "--color-info",
  "--color-info-foreground",
  "--color-brand",
  "--color-brand-foreground",
];

// --- run --------------------------------------------------------------------

const themeInline = block(themeCss, "@theme inline");
const failures = [];
const rows = [];

for (const name of MUST_MAP) {
  if (!themeInline[name]) {
    failures.push(`${name} is not mapped in @theme inline, so its utility is never generated`);
  }
}

for (const [label, fgName, bgSpec, threshold] of PAIRS) {
  for (const [themeName, theme] of [["light", light], ["dark", dark]]) {
    const base = color(theme, "--background");
    const bg = Array.isArray(bgSpec) ? tint(color(theme, bgSpec[0]), bgSpec[1], base) : color(theme, bgSpec);
    const ratio = contrast(color(theme, fgName), bg);
    const ok = ratio >= threshold;
    rows.push(`${ok ? "  ok  " : " FAIL "} ${ratio.toFixed(2).padStart(5)} / ${threshold}  ${themeName.padEnd(5)} ${label}`);
    if (!ok) failures.push(`${label} (${themeName}) is ${ratio.toFixed(2)}:1, needs ${threshold}:1`);
  }
}

if (process.env.VERBOSE || failures.length) console.log(rows.join("\n"));

if (failures.length) {
  console.error(`\ncontrast: ${failures.length} failing pair(s)\n`);
  for (const f of failures) console.error(`  - ${f}`);
  console.error("\nTokens live in src/app/styles/tokens.css and theme.css.\n");
  process.exit(1);
}

console.log(`contrast: ${PAIRS.length * 2} token pairs pass, ${MUST_MAP.length} mappings present`);
