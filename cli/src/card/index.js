// Result JSON in, score card out (PNG or SVG), from one scene.

import { validate } from '../schema.js';
import { computeScore } from '../score.js';
import { layout } from './layout.js';
import { rasterize, encodePng } from './raster.js';
import { toSvg } from './svg.js';

// What the card shows, taken from a validated result. The score is always
// recomputed from the checks, so a card cannot show a number its own file
// does not add up to; `warnings` says when the file's number disagreed.
export function cardData(result) {
  const errors = validate(result);
  if (errors.length) {
    const e = new Error(`not a valid launch check result:\n  ${errors.slice(0, 12).join('\n  ')}`);
    e.code = 'INVALID';
    throw e;
  }
  const { score, band } = computeScore(result.checks);
  const warnings = [];
  if (result.score !== undefined && result.score !== score) {
    warnings.push(`the file says ${result.score}/100 but its checks add up to ${score}/100; the card shows ${score}. Update the file and the .md to match.`);
  }
  let host = result.host;
  if (!host) host = new URL(result.url).hostname;
  return {
    card: {
      host: host.replace(/^www\./, ''),
      score,
      band,
      date: result.checkedAt,
      fixes: (result.fixes ?? []).map((f) => f.title),
    },
    warnings,
  };
}

export function renderCard(result, { format = 'png', theme = 'light' } = {}) {
  const { card, warnings } = cardData(result);
  const { width, height, background, scene } = layout(card, theme);
  const output = format === 'svg'
    ? toSvg(scene, width, height, background, `Launch check: ${card.host}, ${card.score}/100, ${card.band}`)
    : encodePng(rasterize(scene, width, height, background), width, height);
  return { output, card, warnings };
}
