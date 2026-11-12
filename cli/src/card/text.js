// Text as outlines: measure, wrap and shape strings into path commands.
//
// The card never depends on a font being installed: every glyph is an outline
// from src/card/fonts (DM Sans and Gelasio, both SIL OFL 1.1), so the PNG
// and the SVG come out the same on a CI runner, a Mac and a phone.

import sans400 from './fonts/sans-400.js';
import sans600 from './fonts/sans-600.js';
import serif400 from './fonts/serif-400.js';
import serif400i from './fonts/serif-400-italic.js';

export const FACES = { sans: sans400, sansBold: sans600, serif: serif400, serifItalic: serif400i };

const FALLBACK = '?'.codePointAt(0);
const parsed = new WeakMap();

function glyphCommands(face, cp) {
  let cache = parsed.get(face);
  if (!cache) { cache = new Map(); parsed.set(face, cache); }
  if (cache.has(cp)) return cache.get(cp);
  const g = face.glyphs[cp] ?? face.glyphs[FALLBACK];
  const cmds = [];
  const re = /([MLQZ])([^MLQZ]*)/g;
  let m;
  while ((m = re.exec(g[1]))) {
    const nums = m[2].trim() ? m[2].trim().split(/\s+/).map(Number) : [];
    cmds.push([m[1], ...nums]);
  }
  const out = { advance: g[0], cmds };
  cache.set(cp, out);
  return out;
}

// Fold what the fonts lack onto what they have, so a pasted title with smart
// punctuation or an odd space renders instead of turning into question marks.
export function normalize(text) {
  return String(text)
    .replace(/[  -​  　]/g, ' ')
    .replace(/[‐‑‒]/g, '-')
    .replace(/\s+/g, ' ')
    .trim();
}

export function measure(text, face, size) {
  const s = size / face.unitsPerEm;
  let w = 0, prev = null;
  for (const ch of text) {
    const cp = ch.codePointAt(0);
    if (prev) w += (face.kern[prev + ch] ?? 0) * s;
    w += glyphCommands(face, cp).advance * s;
    prev = ch;
  }
  return w;
}

// Path commands for one line, with its left edge at x and baseline at y.
export function shape(text, face, size, x, y, { tracking = 0 } = {}) {
  const s = size / face.unitsPerEm;
  const out = [];
  let pen = x, prev = null;
  for (const ch of text) {
    const cp = ch.codePointAt(0);
    if (prev) pen += (face.kern[prev + ch] ?? 0) * s;
    const g = glyphCommands(face, cp);
    for (const c of g.cmds) {
      if (c[0] === 'Z') { out.push(['Z']); continue; }
      const next = [c[0]];
      for (let i = 1; i < c.length; i += 2) next.push(pen + c[i] * s, y - c[i + 1] * s);
      out.push(next);
    }
    pen += g.advance * s + tracking;
    prev = ch;
  }
  return out;
}

// Greedy word wrap to at most `maxLines`; the last line ends in an ellipsis
// when the text does not fit. A single word wider than the line is cut.
export function wrap(text, face, size, maxWidth, maxLines) {
  const words = normalize(text).split(' ').filter(Boolean);
  const lines = [];
  let line = '';
  let idx = 0;
  while (idx < words.length && lines.length < maxLines) {
    const next = line ? `${line} ${words[idx]}` : words[idx];
    // A word wider than the whole line is taken anyway and cut below.
    if (!line || measure(next, face, size) <= maxWidth) { line = next; idx++; }
    else { lines.push(line); line = ''; }
  }
  if (line) lines.push(line);
  const ellipsize = (s, force) => {
    if (!force && measure(s, face, size) <= maxWidth) return s;
    let cut = s;
    // Back off a word at a time; only a single overlong word is cut mid-word.
    while (cut && measure(`${cut}…`, face, size) > maxWidth) {
      cut = cut.includes(' ') ? cut.slice(0, cut.lastIndexOf(' ')) : cut.slice(0, -1);
    }
    return `${cut.replace(/[\s,;:.–—-]+$/, '')}…`;
  };
  const truncated = idx < words.length;
  if (!truncated && lines.length === 2) return balance(words, face, size, maxWidth) ?? lines;
  return lines.map((l, i) => ellipsize(l, truncated && i === lines.length - 1));
}

// Two lines of similar length instead of a long line and a one-word widow.
function balance(words, face, size, maxWidth) {
  let best = null, bestW = Infinity;
  for (let k = 1; k < words.length; k++) {
    const a = words.slice(0, k).join(' '), b = words.slice(k).join(' ');
    const w = Math.max(measure(a, face, size), measure(b, face, size));
    if (w <= maxWidth && w < bestW) { best = [a, b]; bestW = w; }
  }
  return best;
}

// The largest size, at or below `size`, at which the text fits on one line.
export function fitSize(text, face, size, maxWidth, minSize) {
  let s = size;
  while (s > minSize && measure(text, face, s) > maxWidth) s -= 1;
  return s;
}
