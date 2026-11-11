#!/usr/bin/env node
// Turn the card's OFL fonts into glyph outlines the renderer can draw.
//
//   node scripts/build-fonts.mjs <dir with @fontsource/dm-sans and @fontsource/gelasio unpacked>
//
// Why outlines and not a font file: the card is drawn by our own rasterizer
// (src/card/raster.js) so the package needs no native module and no WASM, and
// the same outlines become <path>s in the SVG, so it renders the same in every
// viewer with no font installed. The fonts are DM Sans (the app's sans) and
// Gelasio (an OFL serif built on Georgia's metrics, since Georgia itself
// cannot be redistributed). Both are SIL OFL 1.1; their licence texts are
// copied beside the output, which the OFL requires of a redistribution.
//
// Dev-only: not in the package's `files`, and it runs only when a face or the
// character set changes. Input is WOFF 1 (zlib), which node:zlib decodes.

import { readFileSync, writeFileSync, copyFileSync } from 'node:fs';
import { inflateSync } from 'node:zlib';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'card', 'fonts');

// Printable ASCII is everything the card's own strings use; Latin-1 and
// Latin Extended-A cover fix titles and hosts in most European languages.
const ASCII = range(0x20, 0x7e);
const LATIN = [...ASCII, ...range(0xa0, 0xff), ...range(0x100, 0x17f),
  0x2013, 0x2014, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022, 0x2026, 0x2192, 0x2212];

const FACES = [
  { name: 'sans-400', pkg: 'fontsource-dm-sans-5.3.0', file: 'dm-sans', weight: 400, style: 'normal', chars: LATIN },
  { name: 'sans-600', pkg: 'fontsource-dm-sans-5.3.0', file: 'dm-sans', weight: 600, style: 'normal', chars: LATIN },
  // The serif draws the score, the band and the fix numbers only.
  // Gelasio, like Georgia, defaults to old-style figures, whose 3, 5 and 9
  // drop below the baseline: a 93 would read as two sizes. `lnum` gives the
  // even-height lining figures a score needs.
  { name: 'serif-400', pkg: 'fontsource-gelasio-5.3.0', file: 'gelasio', weight: 400, style: 'normal', chars: ASCII, features: ['lnum'] },
  { name: 'serif-400-italic', pkg: 'fontsource-gelasio-5.3.0', file: 'gelasio', weight: 400, style: 'italic', chars: ASCII, features: ['lnum'] },
];

function range(a, b) { const r = []; for (let i = a; i <= b; i++) r.push(i); return r; }

function readWoff(buf) {
  if (buf.toString('latin1', 0, 4) !== 'wOFF') throw new Error('not a WOFF 1 file');
  const n = buf.readUInt16BE(12);
  const tables = {};
  for (let i = 0; i < n; i++) {
    const o = 44 + i * 20;
    const tag = buf.toString('latin1', o, o + 4);
    const off = buf.readUInt32BE(o + 4), comp = buf.readUInt32BE(o + 8), orig = buf.readUInt32BE(o + 12);
    const raw = buf.subarray(off, off + comp);
    tables[tag] = comp < orig ? inflateSync(raw) : raw;
  }
  return tables;
}

function parseCmap(t) {
  const map = new Map();
  const n = t.readUInt16BE(2);
  let best = null;
  for (let i = 0; i < n; i++) {
    const pid = t.readUInt16BE(4 + i * 8), eid = t.readUInt16BE(6 + i * 8), off = t.readUInt32BE(8 + i * 8);
    const fmt = t.readUInt16BE(off);
    if (fmt === 12) best = { fmt, off };
    else if (fmt === 4 && pid === 3 && eid === 1 && !best) best = { fmt, off };
    else if (fmt === 4 && !best) best = { fmt, off };
  }
  const { fmt, off } = best;
  if (fmt === 4) {
    const segX2 = t.readUInt16BE(off + 6);
    const ends = off + 14, starts = ends + segX2 + 2, deltas = starts + segX2, ranges = deltas + segX2;
    for (let s = 0; s < segX2 / 2; s++) {
      const end = t.readUInt16BE(ends + s * 2), start = t.readUInt16BE(starts + s * 2);
      const delta = t.readInt16BE(deltas + s * 2), ro = t.readUInt16BE(ranges + s * 2);
      for (let c = start; c <= end && c !== 0xffff; c++) {
        let g;
        if (ro === 0) g = (c + delta) & 0xffff;
        else {
          g = t.readUInt16BE(ranges + s * 2 + ro + (c - start) * 2);
          if (g) g = (g + delta) & 0xffff;
        }
        if (g) map.set(c, g);
      }
    }
  } else {
    const groups = t.readUInt32BE(off + 12);
    for (let i = 0; i < groups; i++) {
      const o = off + 16 + i * 12;
      const s = t.readUInt32BE(o), e = t.readUInt32BE(o + 4), g = t.readUInt32BE(o + 8);
      for (let c = s; c <= e; c++) map.set(c, g + c - s);
    }
  }
  return map;
}

function glyphReader(tables) {
  const head = tables.head, loca = tables.loca, glyf = tables.glyf;
  const longLoca = head.readInt16BE(50) === 1;
  const at = (g) => longLoca ? [loca.readUInt32BE(g * 4), loca.readUInt32BE(g * 4 + 4)]
    : [loca.readUInt16BE(g * 2) * 2, loca.readUInt16BE(g * 2 + 2) * 2];

  // Returns contours: arrays of {x, y, on}.
  function contours(g) {
    const [s, e] = at(g);
    if (e <= s) return [];
    const t = glyf.subarray(s, e);
    const nc = t.readInt16BE(0);
    if (nc >= 0) return simple(t, nc);
    return composite(t);
  }

  function simple(t, nc) {
    const ends = [];
    for (let i = 0; i < nc; i++) ends.push(t.readUInt16BE(10 + i * 2));
    const np = nc ? ends[nc - 1] + 1 : 0;
    let p = 10 + nc * 2;
    p += 2 + t.readUInt16BE(p);
    const flags = [];
    while (flags.length < np) {
      const f = t[p++];
      flags.push(f);
      if (f & 8) { let r = t[p++]; while (r-- > 0) flags.push(f); }
    }
    const xs = [], ys = [];
    let v = 0;
    for (const f of flags) {
      if (f & 2) { const d = t[p++]; v += f & 16 ? d : -d; }
      else if (!(f & 16)) { v += t.readInt16BE(p); p += 2; }
      xs.push(v);
    }
    v = 0;
    for (const f of flags) {
      if (f & 4) { const d = t[p++]; v += f & 32 ? d : -d; }
      else if (!(f & 32)) { v += t.readInt16BE(p); p += 2; }
      ys.push(v);
    }
    const out = [];
    let start = 0;
    for (const end of ends) {
      const c = [];
      for (let i = start; i <= end; i++) c.push({ x: xs[i], y: ys[i], on: !!(flags[i] & 1) });
      out.push(c);
      start = end + 1;
    }
    return out;
  }

  function composite(t) {
    const out = [];
    let p = 10, more = true;
    while (more) {
      const flags = t.readUInt16BE(p), gi = t.readUInt16BE(p + 2);
      p += 4;
      let dx, dy;
      if (flags & 1) { dx = t.readInt16BE(p); dy = t.readInt16BE(p + 2); p += 4; }
      else { dx = t.readInt8(p); dy = t.readInt8(p + 1); p += 2; }
      if (!(flags & 2)) throw new Error('point-matched components are not supported');
      let a = 1, b = 0, c = 0, d = 1;
      const f2 = (o) => t.readInt16BE(o) / 16384;
      if (flags & 8) { a = d = f2(p); p += 2; }
      else if (flags & 0x40) { a = f2(p); d = f2(p + 2); p += 4; }
      else if (flags & 0x80) { a = f2(p); b = f2(p + 2); c = f2(p + 4); d = f2(p + 6); p += 8; }
      for (const contour of contours(gi)) {
        out.push(contour.map((pt) => ({ x: a * pt.x + c * pt.y + dx, y: b * pt.x + d * pt.y + dy, on: pt.on })));
      }
      more = !!(flags & 0x20);
    }
    return out;
  }
  return contours;
}

// TrueType contours to a compact path: M, L, Q, Z in font units, y up.
function toPath(contours) {
  let d = '';
  const r = (n) => Math.round(n);
  for (const c of contours) {
    if (c.length < 2) continue;
    let startIdx = c.findIndex((p) => p.on);
    let pts;
    if (startIdx === -1) {
      // All off-curve: start at the midpoint of the first two.
      const m = { x: (c[0].x + c[1].x) / 2, y: (c[0].y + c[1].y) / 2, on: true };
      pts = [m, ...c.slice(1), c[0]];
    } else {
      pts = [...c.slice(startIdx), ...c.slice(0, startIdx)];
    }
    d += `M${r(pts[0].x)} ${r(pts[0].y)}`;
    let ctrl = null;
    for (let i = 1; i <= pts.length; i++) {
      const p = pts[i % pts.length];
      if (p.on) {
        d += ctrl ? `Q${r(ctrl.x)} ${r(ctrl.y)} ${r(p.x)} ${r(p.y)}` : `L${r(p.x)} ${r(p.y)}`;
        ctrl = null;
      } else if (ctrl) {
        const mx = (ctrl.x + p.x) / 2, my = (ctrl.y + p.y) / 2;
        d += `Q${r(ctrl.x)} ${r(ctrl.y)} ${r(mx)} ${r(my)}`;
        ctrl = p;
      } else {
        ctrl = p;
      }
    }
    d += 'Z';
  }
  return d;
}

function advances(tables) {
  const n = tables.hhea.readUInt16BE(34);
  const hmtx = tables.hmtx;
  return (g) => hmtx.readUInt16BE(Math.min(g, n - 1) * 4);
}

// GPOS pair kerning (lookup types 2 and 9 under the `kern` feature).
function gposKern(t) {
  if (!t) return () => 0;
  const featureList = t.readUInt16BE(6), lookupList = t.readUInt16BE(8);
  const lookups = new Set();
  const fc = t.readUInt16BE(featureList);
  for (let i = 0; i < fc; i++) {
    const o = featureList + 2 + i * 6;
    if (t.toString('latin1', o, o + 4) !== 'kern') continue;
    const f = featureList + t.readUInt16BE(o + 4);
    const n = t.readUInt16BE(f + 2);
    for (let j = 0; j < n; j++) lookups.add(t.readUInt16BE(f + 4 + j * 2));
  }
  const subtables = [];
  for (const li of [...lookups].sort((a, b) => a - b)) {
    const l = lookupList + t.readUInt16BE(lookupList + 2 + li * 2);
    const type = t.readUInt16BE(l), n = t.readUInt16BE(l + 4);
    for (let j = 0; j < n; j++) {
      let s = l + t.readUInt16BE(l + 6 + j * 2);
      let st = type;
      if (type === 9) { st = t.readUInt16BE(s + 2); s += t.readUInt32BE(s + 4); }
      if (st === 2) subtables.push({ lookup: li, off: s });
    }
  }
  const coverage = (o, g) => {
    const fmt = t.readUInt16BE(o), n = t.readUInt16BE(o + 2);
    if (fmt === 1) { for (let i = 0; i < n; i++) if (t.readUInt16BE(o + 4 + i * 2) === g) return i; return -1; }
    for (let i = 0; i < n; i++) {
      const r = o + 4 + i * 6, s = t.readUInt16BE(r), e = t.readUInt16BE(r + 2);
      if (g >= s && g <= e) return t.readUInt16BE(r + 4) + g - s;
    }
    return -1;
  };
  const classOf = (o, g) => {
    const fmt = t.readUInt16BE(o);
    if (fmt === 1) {
      const s = t.readUInt16BE(o + 2), n = t.readUInt16BE(o + 4);
      return g >= s && g < s + n ? t.readUInt16BE(o + 6 + (g - s) * 2) : 0;
    }
    const n = t.readUInt16BE(o + 2);
    for (let i = 0; i < n; i++) {
      const r = o + 4 + i * 6;
      if (g >= t.readUInt16BE(r) && g <= t.readUInt16BE(r + 2)) return t.readUInt16BE(r + 4);
    }
    return 0;
  };
  const vsize = (vf) => { let n = 0; for (let b = vf; b; b >>= 1) n += b & 1; return n * 2; };
  const xAdv = (o, vf) => {
    if (!(vf & 4)) return 0;
    let off = o;
    if (vf & 1) off += 2;
    if (vf & 2) off += 2;
    return t.readInt16BE(off);
  };
  return (g1, g2) => {
    const done = new Set();
    for (const { lookup, off } of subtables) {
      if (done.has(lookup)) continue;
      const fmt = t.readUInt16BE(off);
      const ci = coverage(off + t.readUInt16BE(off + 2), g1);
      if (ci < 0) continue;
      const vf1 = t.readUInt16BE(off + 4), vf2 = t.readUInt16BE(off + 6);
      const rec = vsize(vf1) + vsize(vf2);
      if (fmt === 1) {
        const ps = off + t.readUInt16BE(off + 10 + ci * 2);
        const n = t.readUInt16BE(ps);
        for (let i = 0; i < n; i++) {
          const r = ps + 2 + i * (2 + rec);
          if (t.readUInt16BE(r) === g2) return xAdv(r + 2, vf1);
        }
      } else if (fmt === 2) {
        const c1 = classOf(off + t.readUInt16BE(off + 8), g1);
        const c2 = classOf(off + t.readUInt16BE(off + 10), g2);
        const c2n = t.readUInt16BE(off + 14);
        return xAdv(off + 16 + (c1 * c2n + c2) * rec, vf1);
      }
    }
    return 0;
  };
}

// GSUB single substitutions (lookup type 1, or 7 wrapping it) for the given
// feature tags: glyph id in, substituted glyph id out.
function gsubSingle(t, tags) {
  const map = new Map();
  if (!t || !tags?.length) return map;
  const featureList = t.readUInt16BE(6), lookupList = t.readUInt16BE(8);
  const fc = t.readUInt16BE(featureList);
  const lookups = new Set();
  for (let i = 0; i < fc; i++) {
    const o = featureList + 2 + i * 6;
    if (!tags.includes(t.toString('latin1', o, o + 4))) continue;
    const f = featureList + t.readUInt16BE(o + 4);
    for (let j = 0; j < t.readUInt16BE(f + 2); j++) lookups.add(t.readUInt16BE(f + 4 + j * 2));
  }
  const covered = (o) => {
    const fmt = t.readUInt16BE(o), n = t.readUInt16BE(o + 2), out = [];
    if (fmt === 1) for (let i = 0; i < n; i++) out.push(t.readUInt16BE(o + 4 + i * 2));
    else for (let i = 0; i < n; i++) {
      const r = o + 4 + i * 6;
      for (let g = t.readUInt16BE(r); g <= t.readUInt16BE(r + 2); g++) out.push(g);
    }
    return out;
  };
  for (const li of lookups) {
    const l = lookupList + t.readUInt16BE(lookupList + 2 + li * 2);
    const type = t.readUInt16BE(l);
    for (let j = 0; j < t.readUInt16BE(l + 4); j++) {
      let s = l + t.readUInt16BE(l + 6 + j * 2);
      let st = type;
      if (type === 7) { st = t.readUInt16BE(s + 2); s += t.readUInt32BE(s + 4); }
      if (st !== 1) continue;
      const fmt = t.readUInt16BE(s);
      const glyphs = covered(s + t.readUInt16BE(s + 2));
      glyphs.forEach((g, i) => {
        if (map.has(g)) return;
        map.set(g, fmt === 1 ? (g + t.readInt16BE(s + 4)) & 0xffff : t.readUInt16BE(s + 6 + i * 2));
      });
    }
  }
  return map;
}

function build(src, face) {
  const files = ['latin', 'latin-ext'].map((sub) =>
    join(src, face.pkg, 'package', 'files', `${face.file}-${sub}-${face.weight}-${face.style}.woff`));
  const glyphs = {};
  let metrics = null;
  const kernPairs = {};
  for (const file of files) {
    const tables = readWoff(readFileSync(file));
    const upm = tables.head.readUInt16BE(18);
    const asc = tables.hhea.readInt16BE(4), desc = tables.hhea.readInt16BE(6);
    metrics ??= { unitsPerEm: upm, ascender: asc, descender: desc };
    const cmap = parseCmap(tables.cmap);
    const contours = glyphReader(tables);
    const adv = advances(tables);
    const kern = gposKern(tables.GPOS);
    const sub = gsubSingle(tables.GSUB, face.features);
    for (const cp of face.chars) {
      if (glyphs[cp] || !cmap.has(cp)) continue;
      const g = sub.get(cmap.get(cp)) ?? cmap.get(cp);
      glyphs[cp] = [adv(g), toPath(contours(g))];
    }
    // Kerning only between printable ASCII: the pairs that show at card sizes,
    // and few enough to store flat.
    for (const a of ASCII) for (const b of ASCII) {
      if (!cmap.has(a) || !cmap.has(b)) continue;
      const key = String.fromCodePoint(a) + String.fromCodePoint(b);
      if (key in kernPairs) continue;
      const v = kern(cmap.get(a), cmap.get(b));
      if (v) kernPairs[key] = v;
    }
  }
  return { ...metrics, glyphs, kern: kernPairs };
}

const src = process.argv[2];
if (!src) { console.error('usage: node scripts/build-fonts.mjs <unpacked fontsource dir>'); process.exit(2); }
for (const face of FACES) {
  const data = build(src, face);
  const body = `// Generated by scripts/build-fonts.mjs from @fontsource (${face.pkg}), ${face.weight} ${face.style}.\n` +
    `// SIL Open Font License 1.1: see OFL-${face.file}.txt beside this file. Do not edit by hand.\n` +
    `export default ${JSON.stringify(data)};\n`;
  writeFileSync(join(OUT, `${face.name}.js`), body);
  console.log(`${face.name}: ${Object.keys(data.glyphs).length} glyphs, ${Object.keys(data.kern).length} kern pairs, ${(body.length / 1024).toFixed(0)} KB`);
}
for (const pkg of new Set(FACES.map((f) => f.pkg))) {
  const file = FACES.find((f) => f.pkg === pkg).file;
  copyFileSync(join(src, pkg, 'package', 'LICENSE'), join(OUT, `OFL-${file}.txt`));
}
