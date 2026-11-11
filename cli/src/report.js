// The terminal summary: score first, then the area table, then the findings
// with their evidence, then what this run could not see.

import { AREAS } from './catalog.js';

const paint = (on) => (code, s) => on ? `\x1b[${code}m${s}\x1b[0m` : s;

export function formatSummary(result, { out, color = false } = {}) {
  const c = paint(color);
  const lines = [];
  const date = result.checkedAt.slice(0, 10);
  lines.push('');
  lines.push(`${c('1', result.host)}  ${c('1', `${result.score}/100`)}  ${result.band}   ${result.pagesRead} pages, ${date}`);
  if (result.action) lines.push(`The action: "${result.action.label}"${result.action.url ? ` -> ${result.action.url}` : ''}`);
  lines.push('');
  lines.push(`${'Area'.padEnd(22)}${'Score'.padStart(6)}${'FAIL'.padStart(6)}${'WARN'.padStart(6)}`);
  for (const a of AREAS) {
    const r = result.areas[a.key];
    lines.push(`${`${a.name} (${a.weight})`.padEnd(22)}${String(r.score).padStart(6)}${String(r.fail).padStart(6)}${String(r.warn).padStart(6)}`);
  }
  const bad = result.checks.filter((x) => x.status === 'FAIL' || x.status === 'WARN')
    .sort((a, b) => (a.status === b.status ? 0 : a.status === 'FAIL' ? -1 : 1));
  lines.push('');
  if (!bad.length) lines.push('No FAIL or WARN among the checks this run could make.');
  for (const x of bad) {
    const tag = x.status === 'FAIL' ? c('31;1', 'FAIL') : c('33;1', 'WARN');
    lines.push(`${tag} ${x.id.padEnd(4)} ${x.finding}`);
    for (const e of (x.evidence ?? []).slice(0, 4)) lines.push(`          ${c('2', e)}`);
    if ((x.evidence ?? []).length > 4) lines.push(`          ${c('2', `and ${x.evidence.length - 4} more`)}`);
  }
  if (result.fixes?.length) {
    lines.push('');
    lines.push('Fix first:');
    result.fixes.forEach((f, i) => lines.push(`  ${i + 1}. ${f.title} (${f.checkId}, impact ${f.impact}, effort ${f.effort})`));
  }
  const open = result.checks.filter((x) => x.status === 'UNVERIFIED').map((x) => x.id);
  if (open.length) {
    lines.push('');
    lines.push(`Not verified (cost nothing): ${open.join(' ')}`);
    lines.push('They need the repository or a reader. Your coding agent settles them: npx skills add 5hirish/duct');
  }
  if (out) {
    lines.push('');
    lines.push(`Saved ${out}. Make the card: npx getduct card ${out}`);
  }
  return lines.join('\n');
}
