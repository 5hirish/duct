#!/usr/bin/env node
// getduct: the deterministic half of Duct's launch-check skill.

import { readFileSync, writeFileSync } from 'node:fs';
import { parseArgs } from 'node:util';
import { VERSION } from '../src/version.js';

const HELP = `getduct ${VERSION}: check a site before you launch it, and make a card to post.

Usage
  npx getduct check <url> [--pages 10] [--json] [--out duct-launch-check.json]
  npx getduct card <result.json> [--out duct-launch-check.png] [--svg] [--theme light|dark]
  npx getduct schema

Commands
  check   Read the homepage, robots.txt, the sitemap, llms.txt and up to
          --pages same-site pages. Run every live check of the launch
          checklist and score it out of 100. Prints a summary and writes
          the result to --out; with --json, prints the JSON instead.
  card    Draw a 1200x630 score card (PNG, or SVG with --svg) from a result.
  schema  Print the JSON Schema of a result.

What it cannot see (the code behind the site, whether the page's promises
hold) is UNVERIFIED and costs nothing. The launch-check skill adds those:
  npx skills add 5hirish/duct

https://github.com/5hirish/duct/tree/main/cli`;

function fail(message, code = 2) {
  process.stderr.write(`getduct: ${message}\n`);
  process.exit(code);
}

async function main(argv) {
  const [command, ...rest] = argv;
  if (!command || command === '-h' || command === '--help' || command === 'help') {
    process.stdout.write(`${HELP}\n`);
    return;
  }
  if (command === '-v' || command === '--version') {
    process.stdout.write(`${VERSION}\n`);
    return;
  }
  if (command === 'check') return runCheck(rest);
  if (command === 'card') return runCard(rest);
  if (command === 'schema') {
    process.stdout.write(readFileSync(new URL('../schema/launch-check.schema.json', import.meta.url), 'utf8'));
    return;
  }
  fail(`unknown command "${command}". Run npx getduct --help`);
}

function parse(args, options) {
  try {
    return parseArgs({ args, options: { help: { type: 'boolean', short: 'h' }, ...options }, allowPositionals: true });
  } catch (e) {
    fail(e.message);
  }
}

async function runCheck(args) {
  const { values, positionals } = parse(args, {
    pages: { type: 'string', default: '10' },
    json: { type: 'boolean', default: false },
    out: { type: 'string' },
  });
  if (values.help) return void process.stdout.write(`${HELP}\n`);
  if (positionals.length !== 1) fail('check takes one URL, for example: npx getduct check https://example.com');
  const pages = Number(values.pages);
  if (!Number.isInteger(pages) || pages < 1 || pages > 25) fail('--pages must be a whole number from 1 to 25');

  const { runCheck: run } = await import('../src/check/index.js');
  const { formatSummary } = await import('../src/report.js');
  const log = values.json ? () => {} : (m) => process.stderr.write(`${m}\n`);
  let result;
  try {
    result = await run(positionals[0], { pages, log });
  } catch (e) {
    fail(e.message, 1);
  }
  const json = `${JSON.stringify(result, null, 2)}\n`;
  // Human mode writes the file so `card` can follow; --json is for agents and
  // pipes, so it writes a file only when asked to.
  const out = values.out ?? (values.json ? null : 'duct-launch-check.json');
  if (out) writeFileSync(out, json);
  if (values.json) process.stdout.write(json);
  else process.stdout.write(`${formatSummary(result, { out, color: process.stdout.isTTY && !process.env.NO_COLOR })}\n`);
}

async function runCard(args) {
  const { values, positionals } = parse(args, {
    out: { type: 'string' },
    svg: { type: 'boolean', default: false },
    theme: { type: 'string', default: 'light' },
  });
  if (values.help) return void process.stdout.write(`${HELP}\n`);
  if (positionals.length !== 1) fail('card takes one result file, for example: npx getduct card duct-launch-check.json');
  let result;
  try {
    result = JSON.parse(readFileSync(positionals[0], 'utf8'));
  } catch (e) {
    fail(`could not read ${positionals[0]}: ${e.message}`);
  }
  const { renderCard } = await import('../src/card/index.js');
  const format = values.svg ? 'svg' : 'png';
  let rendered;
  try {
    rendered = renderCard(result, { format, theme: values.theme });
  } catch (e) {
    fail(e.message, e.code === 'INVALID' ? 1 : 2);
  }
  for (const w of rendered.warnings) process.stderr.write(`getduct: ${w}\n`);
  const out = values.out ?? `duct-launch-check.${format}`;
  writeFileSync(out, rendered.output);
  process.stdout.write(`${out}: ${rendered.card.host}, ${rendered.card.score}/100, ${rendered.card.band}\n`);
}

main(process.argv.slice(2)).catch((e) => fail(e.stack ?? String(e), 1));
