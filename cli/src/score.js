// The score arithmetic, fixed by the skill (SKILL.md, "Step 4: score"):
// each area starts at 100, -25 per FAIL, -10 per WARN, floor 0; UNVERIFIED
// costs nothing; overall = sum(area x weight) / 100, rounded.

import { AREAS, BANDS, CHECKS, PENALTY, FOUND_BY } from './catalog.js';

export function bandFor(score) {
  return BANDS.find((b) => score >= b.min).name;
}

export function computeScore(checks) {
  const areas = {};
  let total = 0;
  for (const area of AREAS) {
    const mine = checks.filter((c) => c.id[0] === area.prefix);
    const fail = mine.filter((c) => c.status === 'FAIL').length;
    const warn = mine.filter((c) => c.status === 'WARN').length;
    const score = Math.max(0, 100 - fail * PENALTY.FAIL - warn * PENALTY.WARN);
    areas[area.key] = { name: area.name, weight: area.weight, score, fail, warn };
    total += score * area.weight;
  }
  const score = Math.round(total / 100);
  return { score, band: bandFor(score), areas };
}

// Default ranking for a CLI-only run: impact / effort, then impact, then a
// finding the repository settled ahead of one only the page showed.
export function rankFixes(checks, limit = 3) {
  const order = (f) => FOUND_BY.indexOf(f) === 0 ? 1 : 0; // live site last
  return checks
    .filter((c) => c.status === 'FAIL' || c.status === 'WARN')
    .map((c) => {
      const cat = CHECKS[c.id];
      const k = c.status === 'FAIL' ? 0 : 1;
      return {
        title: c.fix ?? cat.fix,
        checkId: c.id,
        impact: c.impact ?? cat.impact[k],
        effort: c.effort ?? cat.effort[k],
        foundBy: c.foundBy ?? 'live site',
        evidence: (c.evidence ?? [])[0] ?? '',
      };
    })
    .sort((a, b) => (b.impact / b.effort - a.impact / a.effort)
      || (b.impact - a.impact)
      || (order(a.foundBy) - order(b.foundBy)))
    .slice(0, limit);
}
