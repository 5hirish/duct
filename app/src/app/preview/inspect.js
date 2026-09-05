// Inspection helpers, exposed on `window.__preview` inside every scene frame.
//
// These exist because the same twenty lines of measurement code were being
// retyped into `page.evaluate` for every check — rects, computed styles,
// contrast ratios — and retyped slightly differently each time. A harness that
// answers "is this aligned" in one call is cheaper and, more importantly,
// answers it the same way twice.
//
// Read-only. Nothing here mutates the page except `overlay`, which toggles a
// class.

import { OVERLAYS } from "./lenses";

/**
 * sRGB + alpha for any CSS colour, via a 1px canvas.
 *
 * The canvas is the only thing that reliably converts the `lab()`/`oklch()`
 * `getComputedStyle` hands back for modern tokens, which no contrast formula
 * eats. It is cleared rather than pre-filled with white so ALPHA SURVIVES —
 * this used to paint over white and return an opaque colour, which quietly
 * turned every translucent surface into a light one. In dark mode that invented
 * a pale backdrop under `bg-destructive/10` and reported the tinted destructive
 * button at 2.34:1 when it is nothing of the sort. A checker that fails a
 * correct component is worse than no checker: it costs a real investigation
 * every time.
 */
function rgba(css) {
  const cv = document.createElement("canvas");
  cv.width = cv.height = 1;
  const ctx = cv.getContext("2d", { willReadFrequently: true });
  ctx.clearRect(0, 0, 1, 1);
  ctx.fillStyle = css;
  ctx.fillRect(0, 0, 1, 1);
  const d = ctx.getImageData(0, 0, 1, 1).data;
  return [d[0], d[1], d[2], d[3] / 255];
}

/** `src` composited over `dst`, both opaque sRGB triples out. */
function over([r, g, b, a], dst) {
  return [r * a + dst[0] * (1 - a), g * a + dst[1] * (1 - a), b * a + dst[2] * (1 - a)];
}

/** What is actually behind this text: every translucent layer composited down
 *  to the first opaque one. */
function srgb(css, behind = [255, 255, 255]) {
  return over(rgba(css), behind);
}

function luminance([r, g, b]) {
  const f = [r, g, b].map((v) => {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
}

const round = (n) => Math.round(n * 100) / 100;

/**
 * WCAG contrast between any two CSS colours.
 *
 * Exported because the token sheet asks the same question about a palette that
 * `api.contrast` asks about rendered text, and a second implementation of a
 * formula is a second set of rounding decisions. One ratio, computed one way.
 */
export function contrastRatio(fgCss, bgCss) {
  // `bgCss` is a CSS string from the token sheet, or an already-composited
  // triple from `paintedBackground`. Text gets composited over it too: a
  // `text-foreground/70` is not the colour it names.
  const bg = typeof bgCss === "string" ? srgb(bgCss) : bgCss;
  const fgL = luminance(srgb(fgCss, bg));
  const bgL = luminance(bg);
  const [hi, lo] = fgL > bgL ? [fgL, bgL] : [bgL, fgL];
  return round((hi + 0.05) / (lo + 0.05));
}

function rect(el) {
  const b = el.getBoundingClientRect();
  return {
    x: round(b.x), y: round(b.y),
    w: round(b.width), h: round(b.height),
    right: round(b.right), bottom: round(b.bottom),
    cx: round(b.x + b.width / 2), cy: round(b.y + b.height / 2),
  };
}

/**
 * The colour actually behind this element, as an opaque sRGB triple.
 *
 * Not "the nearest ancestor with a background" — that answer is wrong the
 * moment the background is translucent, which in this codebase is the common
 * case: every tinted status surface is a `/10` or `/15` of a token. The layers
 * are collected up to the first opaque one and composited back down, so a
 * `bg-destructive/10` on a dark card reports the dark result it actually is.
 */
function paintedBackground(el) {
  const layers = [];
  let node = el;
  while (node) {
    const c = rgba(getComputedStyle(node).backgroundColor);
    if (c[3] > 0) layers.push(c);
    if (c[3] >= 1) break;
    node = node.parentElement;
  }
  // Nothing opaque anywhere up the tree: the canvas the browser paints on is
  // white in a light scheme and near-black in a dark one.
  const dark = getComputedStyle(document.documentElement).colorScheme === "dark";
  let base = dark ? [0, 0, 0] : [255, 255, 255];
  for (let i = layers.length - 1; i >= 0; i--) base = over(layers[i], base);
  return base;
}

export function install() {
  const all = (sel) => [...document.querySelectorAll(sel)];

  const api = {
    /** Every element matching `sel`, with box, type and colour. */
    measure(sel) {
      return all(sel).map((el) => {
        const cs = getComputedStyle(el);
        return {
          text: (el.textContent || "").trim().slice(0, 40),
          ...rect(el),
          fontPx: round(parseFloat(cs.fontSize)),
          weight: cs.fontWeight,
          lineHeight: cs.lineHeight,
          color: cs.color,
          display: cs.display,
        };
      });
    },

    /** Named computed properties, for asserting a rule rather than eyeballing. */
    styles(sel, props = ["fontSize", "fontWeight", "color", "backgroundColor"]) {
      return all(sel).map((el) => {
        const cs = getComputedStyle(el);
        return Object.fromEntries(props.map((p) => [p, cs[p]]));
      });
    },

    /** WCAG contrast of an element's text against what is actually behind it. */
    contrast(sel) {
      return all(sel).map((el) => {
        const cs = getComputedStyle(el);
        const ratio = contrastRatio(cs.color, paintedBackground(el));
        const px = parseFloat(cs.fontSize);
        const large = px >= 24 || (px >= 18.66 && Number(cs.fontWeight) >= 700);
        return {
          text: (el.textContent || "").trim().slice(0, 32),
          ratio,
          fontPx: round(px),
          needs: large ? 3 : 4.5,
          passesAA: ratio >= (large ? 3 : 4.5),
        };
      });
    },

    /** Do these all share a left rail / a vertical centre? The alignment
     *  question, answered exactly rather than by squinting. */
    aligned(sel, axis = "left") {
      const boxes = all(sel).map(rect);
      const key = { left: "x", right: "right", top: "y", centreY: "cy", centreX: "cx" }[axis] || "x";
      const values = boxes.map((b) => Math.round(b[key]));
      return { axis, values, aligned: new Set(values).size <= 1, count: boxes.length };
    },

    /** Interactive targets below the 24×24 floor (WCAG 2.5.8). */
    smallTargets(root = "body") {
      const sel = "button, a[href], input, select, textarea, [role=button], [tabindex]:not([tabindex='-1'])";
      return all(`${root} :is(${sel})`)
        .map((el) => ({ el, r: rect(el) }))
        .filter(({ r }) => r.w > 0 && r.h > 0 && (r.w < 24 || r.h < 24))
        .map(({ el, r }) => ({
          tag: el.tagName.toLowerCase(),
          label: el.getAttribute("aria-label") || (el.textContent || "").trim().slice(0, 24),
          w: r.w, h: r.h,
        }));
    },

    /** Controls with no accessible name, and images with no alt. */
    unnamed(root = "body") {
      const out = [];
      for (const el of all(`${root} button, ${root} a[href], ${root} input, ${root} select`)) {
        const name =
          el.getAttribute("aria-label") ||
          el.getAttribute("title") ||
          (el.labels && el.labels.length ? el.labels[0].textContent : "") ||
          (el.textContent || "").trim();
        if (!name.trim()) out.push({ tag: el.tagName.toLowerCase(), cls: el.className });
      }
      for (const img of all(`${root} img`)) {
        if (img.getAttribute("alt") === null) out.push({ tag: "img", src: img.src.slice(0, 60) });
      }
      return out;
    },

    /** Anything wider than the viewport — the usual cause of a stray scrollbar. */
    overflowing() {
      const limit = document.documentElement.clientWidth;
      return all("body *")
        .map((el) => ({ el, r: el.getBoundingClientRect() }))
        .filter(({ r }) => r.width > limit + 1 || r.right > limit + 1)
        .slice(0, 12)
        .map(({ el, r }) => ({
          tag: el.tagName.toLowerCase(),
          cls: typeof el.className === "string" ? el.className.slice(0, 60) : "",
          w: round(r.width),
          right: round(r.right),
        }));
    },

    /** How many distinct type sizes are on screen. DESIGN.md wants very few. */
    typeScale(root = "body") {
      const seen = new Map();
      for (const el of all(`${root} *`)) {
        if (!el.childNodes.length) continue;
        const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
        if (!hasText) continue;
        const cs = getComputedStyle(el);
        const key = `${round(parseFloat(cs.fontSize))}px/${cs.fontWeight}`;
        seen.set(key, (seen.get(key) || 0) + 1);
      }
      return {
        distinct: seen.size,
        sizes: [...new Set([...seen.keys()].map((k) => parseFloat(k)))].sort((a, b) => b - a),
        combos: Object.fromEntries([...seen.entries()].sort((a, b) => b[1] - a[1])),
      };
    },

    /** Toggle a debug overlay — see `OVERLAYS` in lenses.jsx for the ids. */
    overlay(mode = "outline") {
      const root = document.documentElement;
      root.classList.remove(...OVERLAYS.map((o) => `preview-${o.id}`));
      if (mode !== "off") root.classList.add(`preview-${mode}`);
      return mode;
    },

    /**
     * The design tokens as this document actually resolves them.
     *
     * Reading them from computed style rather than parsing tokens.css is the
     * point: it reports the value after the cascade, so the dark variant and
     * any local override show up as what they are. Names come from the
     * stylesheet, so a token added there appears here without an edit.
     */
    tokens(prefix = "--") {
      const cs = getComputedStyle(document.documentElement);
      const names = new Set();
      for (const sheet of document.styleSheets) {
        let rules;
        try {
          rules = sheet.cssRules;
        } catch {
          continue; // cross-origin sheet; nothing to read
        }
        for (const rule of rules || []) {
          if (!rule.style) continue;
          for (const prop of rule.style) if (prop.startsWith(prefix)) names.add(prop);
        }
      }
      return Object.fromEntries(
        [...names].sort().map((n) => [n, cs.getPropertyValue(n).trim()]),
      );
    },
  };

  window.__preview = Object.assign(window.__preview || {}, api);
  return api;
}
