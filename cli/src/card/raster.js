// A scene of filled paths to RGB pixels, then to PNG. No dependency.
//
// The fill is the signed-area accumulation method from font-rs (Raph Levien,
// 2016): each edge adds its exact area coverage to a buffer and one running
// sum per pixel turns it into antialiased coverage. It is what makes text at
// 18px look like a browser drew it rather than a 2005 GD script, in about 80
// lines. Winding is non-zero by magnitude, which is what glyph outlines need.

import { deflateSync } from 'node:zlib';

const CURVE_TOLERANCE = 0.2; // px: flattening error, invisible at 1x

export function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

// Path commands (absolute, px) to closed polylines.
export function flatten(cmds) {
  const polys = [];
  let cur = null, x = 0, y = 0, sx = 0, sy = 0;
  const seg = (n) => Math.max(1, Math.min(64, Math.ceil(Math.sqrt(n / CURVE_TOLERANCE))));
  for (const c of cmds) {
    switch (c[0]) {
      case 'M':
        if (cur && cur.length > 2) polys.push(cur);
        x = sx = c[1]; y = sy = c[2]; cur = [x, y];
        break;
      case 'L':
        x = c[1]; y = c[2]; cur.push(x, y);
        break;
      case 'Q': {
        const [, cx, cy, ex, ey] = c;
        const n = seg(Math.hypot(cx - x, cy - y) + Math.hypot(ex - cx, ey - cy));
        for (let i = 1; i <= n; i++) {
          const t = i / n, u = 1 - t;
          cur.push(u * u * x + 2 * u * t * cx + t * t * ex, u * u * y + 2 * u * t * cy + t * t * ey);
        }
        x = ex; y = ey;
        break;
      }
      case 'C': {
        const [, c1x, c1y, c2x, c2y, ex, ey] = c;
        const n = seg(Math.hypot(c1x - x, c1y - y) + Math.hypot(c2x - c1x, c2y - c1y) + Math.hypot(ex - c2x, ey - c2y));
        for (let i = 1; i <= n; i++) {
          const t = i / n, u = 1 - t;
          cur.push(
            u * u * u * x + 3 * u * u * t * c1x + 3 * u * t * t * c2x + t * t * t * ex,
            u * u * u * y + 3 * u * u * t * c1y + 3 * u * t * t * c2y + t * t * t * ey);
        }
        x = ex; y = ey;
        break;
      }
      case 'Z':
        if (cur) { cur.push(sx, sy); if (cur.length > 2) polys.push(cur); }
        cur = null; x = sx; y = sy;
        break;
      default:
        throw new Error(`unknown path command ${c[0]}`);
    }
  }
  if (cur && cur.length > 2) polys.push(cur);
  return polys;
}

// Coverage for one shape, in a buffer covering only its bounding box.
function coverage(polys, W, H) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of polys) for (let i = 0; i < p.length; i += 2) {
    if (p[i] < x0) x0 = p[i]; if (p[i] > x1) x1 = p[i];
    if (p[i + 1] < y0) y0 = p[i + 1]; if (p[i + 1] > y1) y1 = p[i + 1];
  }
  const bx = Math.max(0, Math.floor(x0)), by = Math.max(0, Math.floor(y0));
  const bw = Math.min(W, Math.ceil(x1) + 1) - bx, bh = Math.min(H, Math.ceil(y1) + 1) - by;
  if (bw <= 0 || bh <= 0) return null;
  // Two spare columns: the last pixel's edge writes one to its right.
  const w = bw + 2;
  const acc = new Float32Array(w * bh + 2);
  const line = (ax, ay, bx2, by2) => {
    if (ay === by2) return;
    let dir = 1;
    if (ay > by2) { dir = -1; [ax, ay, bx2, by2] = [bx2, by2, ax, ay]; }
    // Clamp x into the buffer: everything left of it still counts as coverage.
    const dxdy = (bx2 - ax) / (by2 - ay);
    let x = ax;
    if (ay < 0) x -= ay * dxdy;
    for (let yy = Math.max(0, Math.floor(ay)); yy < Math.min(bh, Math.ceil(by2)); yy++) {
      const ls = yy * w;
      const dy = Math.min(yy + 1, by2) - Math.max(yy, ay);
      const xn = x + dxdy * dy;
      const d = dy * dir;
      let xa = Math.min(x, xn), xb = Math.max(x, xn);
      xa = Math.max(0, Math.min(w - 2, xa)); xb = Math.max(0, Math.min(w - 2, xb));
      const xaf = Math.floor(xa), xai = xaf, xbc = Math.ceil(xb), xbi = xbc;
      if (xbi <= xai + 1) {
        const xmf = 0.5 * (xa + xb) - xaf;
        acc[ls + xai] += d - d * xmf;
        acc[ls + xai + 1] += d * xmf;
      } else {
        const s = 1 / (xb - xa);
        const x0f = xa - xaf;
        const a0 = 0.5 * s * (1 - x0f) * (1 - x0f);
        const x1f = xb - xbc + 1;
        const am = 0.5 * s * x1f * x1f;
        acc[ls + xai] += d * a0;
        if (xbi === xai + 2) {
          acc[ls + xai + 1] += d * (1 - a0 - am);
        } else {
          const a1 = s * (1.5 - x0f);
          acc[ls + xai + 1] += d * (a1 - a0);
          for (let xi = xai + 2; xi < xbi - 1; xi++) acc[ls + xi] += d * s;
          const a2 = a1 + (xbi - xai - 3) * s;
          acc[ls + xbi - 1] += d * (1 - a2 - am);
        }
        acc[ls + xbi] += d * am;
      }
      x = xn;
    }
  };
  for (const p of polys) {
    for (let i = 0; i + 3 < p.length; i += 2) line(p[i] - bx, p[i + 1] - by, p[i + 2] - bx, p[i + 3] - by);
  }
  return { acc, bx, by, bw, bh, w };
}

export function rasterize(scene, W, H, background) {
  const px = new Float32Array(W * H * 3);
  const bg = hexToRgb(background);
  for (let i = 0; i < W * H; i++) { px[i * 3] = bg[0]; px[i * 3 + 1] = bg[1]; px[i * 3 + 2] = bg[2]; }
  for (const shape of scene) {
    const cov = coverage(flatten(shape.d), W, H);
    if (!cov) continue;
    const [r, g, b] = hexToRgb(shape.fill);
    const alpha = shape.opacity ?? 1;
    const { acc, bx, by, bw, bh, w } = cov;
    for (let yy = 0; yy < bh; yy++) {
      // Each row of a closed outline sums to zero, so the running sum restarts per row.
      let sum = 0;
      for (let xx = 0; xx < w; xx++) {
        sum += acc[yy * w + xx];
        if (xx >= bw) continue;
        const c = Math.min(1, Math.abs(sum)) * alpha;
        if (c < 1 / 512) continue;
        const o = ((by + yy) * W + bx + xx) * 3;
        px[o] += (r - px[o]) * c; px[o + 1] += (g - px[o + 1]) * c; px[o + 2] += (b - px[o + 2]) * c;
      }
    }
  }
  return px;
}

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 255] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, 'latin1'), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}

export function encodePng(px, W, H) {
  // Filter 1 (Sub) on every row: the card is mostly flat colour, which Sub
  // turns into runs of zeros that deflate to almost nothing.
  const raw = Buffer.alloc((W * 3 + 1) * H);
  for (let y = 0; y < H; y++) {
    const ro = y * (W * 3 + 1);
    raw[ro] = 1;
    for (let x = 0; x < W * 3; x++) {
      const v = Math.max(0, Math.min(255, Math.round(px[y * W * 3 + x])));
      const left = x >= 3 ? Math.max(0, Math.min(255, Math.round(px[y * W * 3 + x - 3]))) : 0;
      raw[ro + 1 + x] = (v - left) & 255;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(W, 0); ihdr.writeUInt32BE(H, 4);
  ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}
