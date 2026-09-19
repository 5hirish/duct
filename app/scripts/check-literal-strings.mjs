#!/usr/bin/env node
/**
 * Every user-facing string goes through Lingui, or the check fails.
 *
 * The catalogue can only translate what it can see. A `<p>Saved</p>` written
 * beside a `<Trans>Saved</Trans>` renders in English for a Spanish user with
 * no warning from anything — the build is green, the tests pass, the page is
 * simply half-translated. This is the one mechanical rule that keeps the
 * catalogue complete as the copy keeps moving, so it runs in `check:i18n`.
 *
 * What it flags: JSX text with a word in it outside `<Trans>`, and string
 * literals in the attributes a person reads (placeholder, title, alt,
 * aria-label, aria-description). What it lets through: single tokens that are
 * names rather than copy (Duct, GA4, GitHub), punctuation, and the files in
 * EXEMPT — dev tooling and fixtures that never reach a user.
 *
 * Deliberately a parser walk and not a regex: JSX text spans lines, and a
 * regex that catches `>Save<` misses `>\n  Save changes\n<`.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "@babel/parser";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(ROOT, "src");

/** Never rendered to a user, or rendered only to us. */
const EXEMPT = [
  "src/app/preview/",       // the component harness, dev only
  "src/lib/__fixtures__/",  // recorded streams and the mock story
  "src/i18n/",              // the plumbing itself
  "src/locales/",
  "src/components/ui/",     // shadcn primitives take their copy as children
  "src/instrumentation",    // Sentry
];

/** Attributes whose value a person reads. */
const COPY_ATTRIBUTES = new Set([
  "placeholder", "title", "alt", "aria-label", "aria-description",
  "aria-placeholder", "aria-roledescription", "aria-valuetext",
]);

/**
 * Tokens that are names, not copy: a translator would leave them alone and a
 * catalogue entry for them is noise. Matched only against a *whole* text
 * node, so "Connect GA4" is still flagged and "GA4" alone is not.
 */
const NAMES = new Set([
  "Duct", "duct", "GA4", "GSC", "GTM", "GitHub", "Google", "Stripe", "Mixpanel",
  "Clarity", "GrowthBook", "PostHog", "TikTok", "YouTube", "ChatGPT", "Claude",
  "Codex", "OpenAI", "Anthropic", "Gemini", "Ollama", "MIT", "OK", "URL", "API",
  "JSON", "CSV", "SEO", "ROAS", "CPA", "CPC", "CPM", "CTR", "LTV", "CAC", "MRR",
  "macOS", "Windows", "Linux", "iOS", "Android", "Safari", "Chrome", "Firefox",
  "X", "v", "•", "·", "—", "–", "→", "←", "↑", "↓", "…", "%", "/", "|", "&",
]);

const LETTERS = /\p{L}{2,}/u;

function walkFiles(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walkFiles(full, out);
    else if (/\.(jsx|js)$/.test(name) && !/\.test\.js$/.test(name)) out.push(full);
  }
  return out;
}

function isName(text) {
  const t = text.trim();
  if (!LETTERS.test(t)) return true;
  if (NAMES.has(t)) return true;
  // One token with no spaces and no lowercase run of 4+ is a code or a
  // version ("v0.7.0", "GA4"), not a sentence.
  if (!/\s/.test(t) && !/\p{Ll}{4,}/u.test(t)) return true;
  return false;
}

function check(file) {
  const source = readFileSync(file, "utf8");
  let ast;
  try {
    ast = parse(source, { sourceType: "module", plugins: ["jsx"], errorRecovery: true });
  } catch (err) {
    return [{ line: err.loc?.line ?? 0, text: `parse error: ${err.message}` }];
  }
  const findings = [];

  function visit(node, insideTrans, inAttribute = false) {
    if (!node || typeof node.type !== "string") return;
    let inside = insideTrans;
    // An attribute's own container (className={`…`}) is not a child string;
    // the attributes a person reads are handled by name above.
    if (node.type === "JSXAttribute") {
      visit(node.value, inside, true);
      return;
    }
    if (node.type === "JSXElement") {
      const name = node.openingElement?.name;
      const tag = name?.type === "JSXIdentifier" ? name.name : "";
      if (tag === "Trans" || tag === "Plural" || tag === "Select") inside = true;
      for (const attr of node.openingElement.attributes || []) {
        if (attr.type !== "JSXAttribute" || !attr.name) continue;
        const attrName = attr.name.name;
        if (!COPY_ATTRIBUTES.has(attrName)) continue;
        const v = attr.value;
        if (v?.type === "StringLiteral" && !isName(v.value)) {
          findings.push({ line: v.loc.start.line, text: `${attrName}="${v.value}"` });
        }
        // {`template`} and {"string"} inside an attribute count the same
        if (v?.type === "JSXExpressionContainer") {
          const e = v.expression;
          if (e?.type === "StringLiteral" && !isName(e.value)) {
            findings.push({ line: e.loc.start.line, text: `${attrName}={"${e.value}"}` });
          }
          if (e?.type === "TemplateLiteral" && e.quasis.some((q) => !isName(q.value.cooked || ""))) {
            findings.push({ line: e.loc.start.line, text: `${attrName}={\`…\`}` });
          }
        }
      }
    }
    if (node.type === "JSXText" && !inside && !isName(node.value)) {
      findings.push({ line: node.loc.start.line, text: JSON.stringify(node.value.trim().slice(0, 60)) });
    }
    // A bare string or template as a JSX child: <p>{"Saved"}</p>, {`v${x} of ${y}`}
    if (node.type === "JSXExpressionContainer" && !inside && !inAttribute) {
      const e = node.expression;
      if (e?.type === "StringLiteral" && !isName(e.value)) {
        findings.push({ line: e.loc.start.line, text: JSON.stringify(e.value.slice(0, 60)) });
      }
      if (e?.type === "TemplateLiteral" && e.quasis.some((q) => !isName(q.value.cooked || ""))) {
        findings.push({ line: e.loc.start.line, text: "`" + e.quasis.map((q) => q.value.cooked).join("${…}").slice(0, 60) + "`" });
      }
    }
    for (const key of Object.keys(node)) {
      if (key === "loc" || key === "start" || key === "end" || key === "leadingComments" || key === "trailingComments") continue;
      const child = node[key];
      if (Array.isArray(child)) child.forEach((c) => visit(c, inside, inAttribute));
      else if (child && typeof child.type === "string") visit(child, inside, inAttribute);
    }
  }
  visit(ast.program, false);
  return findings;
}

const targets = process.argv.slice(2).map((p) => join(ROOT, p));
const files = (targets.length ? targets : [SRC]).flatMap((t) => (statSync(t).isDirectory() ? walkFiles(t) : [t]));
let total = 0;
for (const file of files) {
  const rel = relative(ROOT, file);
  if (EXEMPT.some((prefix) => rel.startsWith(prefix))) continue;
  const findings = check(file);
  if (!findings.length) continue;
  total += findings.length;
  console.log(rel);
  for (const f of findings) console.log(`  ${f.line}: ${f.text}`);
}
if (total) {
  console.error(`\n${total} untranslated string${total === 1 ? "" : "s"}. Wrap copy in <Trans> or t\`…\` (see app/AGENTS.md, "Interface language").`);
  process.exit(1);
}
console.log(`i18n: no untranslated strings in ${files.length} files`);
