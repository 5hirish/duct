// The score card: 1200x630, the size X, LinkedIn and Slack crop to.
//
// Read at thumbnail size first. An X timeline shows a posted image at about
// half width, so every string here is at least 24px (12px on the timeline)
// and the score, the one thing the card is for, is the heaviest thing on it
// by a factor of four. Brand: warm neutrals in both themes, one orange, the
// serif for the number and its italic second beat (site/DESIGN.md), DM Sans
// for everything else (app/DESIGN.md).

import { FACES, measure, shape, wrap, fitSize, normalize } from './text.js';

export const WIDTH = 1200;
export const HEIGHT = 630;

// Contrast against `bg`, WCAG 2: ink 16.9 / 16.6, muted 6.7 / 7.8,
// brand 4.9 / 7.5 (light / dark). `mark` is the literal brand orange for the
// dash, the meter and the wordmark dot: decoration, never words.
export const THEMES = {
  light: { bg: '#faf6f2', ink: '#1a1511', muted: '#5e5650', brand: '#c14100', mark: '#ff5c00', line: '#e1ddd8', track: '#ebe6e0' },
  dark: { bg: '#1a1511', ink: '#f7f5f1', muted: '#b1a9a2', brand: '#f98942', mark: '#ff5c00', line: '#38312d', track: '#38312d' },
};

const PAD_X = 72;
const COL_SPLIT = 520; // left: the score; right: the fixes
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const COUNT_WORDS = ['Nothing to fix', 'One fix', 'Two fixes', 'Three fixes'];
const FOOTER = 'Checked with Duct · npx skills add 5hirish/duct';

export function formatDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  if (!m) return '';
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
}

function rect(x, y, w, h, r = 0) {
  if (!r) return [['M', x, y], ['L', x + w, y], ['L', x + w, y + h], ['L', x, y + h], ['Z']];
  r = Math.min(r, w / 2, h / 2);
  const k = 0.5523 * r;
  return [
    ['M', x + r, y], ['L', x + w - r, y], ['C', x + w - r + k, y, x + w, y + r - k, x + w, y + r],
    ['L', x + w, y + h - r], ['C', x + w, y + h - r + k, x + w - r + k, y + h, x + w - r, y + h],
    ['L', x + r, y + h], ['C', x + r - k, y + h, x, y + h - r + k, x, y + h - r],
    ['L', x, y + r], ['C', x, y + r - k, x + r - k, y, x + r, y], ['Z'],
  ];
}

function circle(cx, cy, r) {
  return rect(cx - r, cy - r, 2 * r, 2 * r, r);
}

// card: { host, score, band, fixes: [title], date }
export function layout(card, themeName = 'light') {
  const t = THEMES[themeName];
  if (!t) throw new Error(`unknown theme "${themeName}" (light or dark)`);
  const scene = [];
  const text = (s, face, size, x, y, fill, opts) => scene.push({ d: shape(s, face, size, x, y, opts), fill });
  const right = WIDTH - PAD_X;

  // Eyebrow: the site's .tag, an accent dash and small caps, with the date opposite.
  scene.push({ d: rect(PAD_X, 78, 28, 4, 2), fill: t.mark });
  text('LAUNCH CHECK', FACES.sansBold, 22, PAD_X + 42, 88, t.muted, { tracking: 2.4 });
  const date = formatDate(card.date);
  if (date) text(date, FACES.sans, 24, right - measure(date, FACES.sans, 24), 88, t.muted);

  // The host, as large as fits on one line.
  const host = normalize(card.host);
  const hostSize = fitSize(host, FACES.sansBold, 60, right - PAD_X, 30);
  text(host, FACES.sansBold, hostSize, PAD_X, 166, t.ink, { tracking: -0.5 });

  // The score: serif numerals, "/100" beside them, the band in the italic accent.
  const score = String(card.score);
  const numBaseline = 398;
  const outOf = measure('/100', FACES.sans, 34);
  // "100" is a third wider than "97": shrink it rather than cross the divider.
  let numSize = 232;
  const numWidth = (s) => measure(score, FACES.serif, s) - (s / 40) * (score.length - 1);
  while (numSize > 150 && numWidth(numSize) + 8 + outOf > COL_SPLIT - PAD_X - 40) numSize -= 4;
  text(score, FACES.serif, numSize, PAD_X - 6, numBaseline, t.ink, { tracking: -numSize / 40 });
  text('/100', FACES.sans, 34, PAD_X + numWidth(numSize) + 2, numBaseline, t.muted);

  // A meter under the number: what "out of 100" looks like at a glance.
  const meterW = COL_SPLIT - PAD_X - 40;
  scene.push({ d: rect(PAD_X, 428, meterW, 10, 5), fill: t.track });
  const filled = Math.max(10, Math.round(meterW * Math.max(0, Math.min(100, card.score)) / 100));
  scene.push({ d: rect(PAD_X, 428, filled, 10, 5), fill: t.mark });

  const bandSize = fitSize(card.band, FACES.serifItalic, 50, COL_SPLIT - PAD_X - 40, 34);
  text(card.band, FACES.serifItalic, bandSize, PAD_X, 500, t.brand);

  // The fixes.
  const fixes = (card.fixes ?? []).slice(0, 3);
  const colX = COL_SPLIT + 24;
  scene.push({ d: rect(COL_SPLIT - 16, 214, 1, 300), fill: t.line });
  text(COUNT_WORDS[fixes.length], FACES.sansBold, 24, colX, 236, t.muted);
  const textX = colX + 44;
  const textW = right - textX;
  const fixSize = 30, lineH = 38, gap = 22;
  // Two lines each when they fit; one each when three long titles would crowd.
  const wrapped = fixes.map((f) => wrap(f, FACES.sansBold, fixSize, textW, 2));
  const total = wrapped.reduce((n, l) => n + l.length * lineH, 0) + gap * Math.max(0, fixes.length - 1);
  const lines = total > 290 ? fixes.map((f) => wrap(f, FACES.sansBold, fixSize, textW, 1)) : wrapped;
  let y = 290;
  lines.forEach((ls, i) => {
    text(String(i + 1), FACES.serif, 38, colX, y + 2, t.brand);
    ls.forEach((l, j) => text(l, FACES.sansBold, fixSize, textX, y + j * lineH, t.ink, { tracking: -0.2 }));
    y += ls.length * lineH + gap;
  });
  if (!fixes.length) {
    for (const [i, l] of wrap('Every check that could run passed.', FACES.sans, 30, right - colX, 2).entries()) {
      text(l, FACES.sans, 30, colX, 290 + i * lineH, t.ink);
    }
  }

  // Footer: a hairline, the install line, and the wordmark (lowercase serif + orange dot).
  scene.push({ d: rect(PAD_X, 548, right - PAD_X, 1), fill: t.line });
  text(FOOTER, FACES.sans, 24, PAD_X, 594, t.muted);
  const markSize = 38;
  const markW = measure('duct', FACES.serif, markSize);
  const dotR = 5;
  const markX = right - markW - dotR * 2 - 3;
  text('duct', FACES.serif, markSize, markX, 594, t.ink);
  scene.push({ d: circle(markX + markW + 3 + dotR, 594 - dotR, dotR), fill: t.mark });

  return { width: WIDTH, height: HEIGHT, background: t.bg, scene };
}
