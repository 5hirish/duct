"use client";

/**
 * Rasterize a self-contained slide document to a base64 PNG at 1080×1920.
 *
 * The HTML comes from GET /api/content/slide-doc with its images already inlined
 * as base64 (origin-clean, so the canvas isn't CORS-tainted). We render it in an
 * offscreen same-origin iframe, wait for fonts + images, and capture the .slide
 * element. Used by the render_slide bridge so the agent can SEE the composed
 * slide; the same PNG can back publishing.
 *
 * Returns the base64 payload (no `data:` prefix), or "" on failure — the caller
 * POSTs "" so the agent's render_slide tool fails fast instead of hanging.
 */
export async function captureSlideDocToPng(html) {
  if (typeof document === "undefined") return "";
  const iframe = document.createElement("iframe");
  iframe.setAttribute("sandbox", "allow-same-origin");
  iframe.setAttribute("aria-hidden", "true");
  Object.assign(iframe.style, {
    position: "fixed",
    left: "-100000px",
    top: "0",
    width: "1080px",
    height: "1920px",
    border: "0",
    background: "#000",
    pointerEvents: "none",
    opacity: "0",
  });
  document.body.appendChild(iframe);
  let host = null;
  let fonts = [];
  try {
    await new Promise((resolve) => {
      let done = false;
      const finish = () => { if (!done) { done = true; resolve(); } };
      iframe.addEventListener("load", finish, { once: true });
      iframe.srcdoc = html;
      setTimeout(finish, 2500); // safety net if load never fires
    });
    const idoc = iframe.contentDocument;
    if (!idoc) return "";
    try { await idoc.fonts?.ready; } catch { /* fonts optional */ }
    await waitForImages(idoc, 5000);
    const source = idoc.querySelector(".slide") || idoc.body;
    // Captured from this document, not the iframe's. The library draws the
    // node through an <img> it creates in the node's own document, and in a
    // frame sandboxed without scripts WebKit never fires that image's load:
    // every capture in the desktop app (WKWebView) sat out the library's 30 s
    // timeout and the agent's render_slide gave up first (2026-11-27).
    // Chromium never showed it. The iframe still parses the doc and loads its
    // fonts; only an inert copy of the slide and its styles comes across.
    host = document.createElement("div");
    // A shadow root inherits from this page, not from the doc's <body>, so
    // the host starts from nothing and takes the doc body's own type: the
    // render backs publishing, and the app's font is not the slide's.
    host.style.all = "initial";
    const base = idoc.defaultView.getComputedStyle(idoc.body);
    for (const prop of ["fontFamily", "fontSize", "fontWeight", "lineHeight", "letterSpacing", "color"]) {
      host.style[prop] = base[prop];
    }
    Object.assign(host.style, { position: "fixed", left: "-100000px", top: "0", pointerEvents: "none" });
    host.setAttribute("aria-hidden", "true");
    document.body.appendChild(host);
    const root = host.attachShadow({ mode: "open" });
    for (const style of idoc.querySelectorAll('style, link[rel="stylesheet"]')) {
      const copy = inert(document.importNode(style, true));
      // In a shadow tree `:root` matches nothing, so the engine's variables
      // (the safe zone, the zoom) were lost and every caption drew at the
      // edge, in what the agent looked at and what published (2026-11-27).
      if (copy.tagName === "STYLE") copy.textContent = forShadowRoot(copy.textContent);
      root.appendChild(copy);
    }
    fonts = await adoptFonts(idoc);
    const target = root.appendChild(inert(document.importNode(source, true)));
    target.getBoundingClientRect(); // lay out, so the faces it uses start loading
    try { await Promise.race([document.fonts.ready, new Promise((res) => setTimeout(res, 4000))]); } catch { /* fonts optional */ }
    // Imported here, not at the top: this runs only when the agent asks to
    // see a slide, and a static import put the library in every content
    // workspace's first load. Inside the try, so a failed chunk load is a
    // failed capture ("") like any other.
    const { domToPng } = await import("modern-screenshot");
    // The library paints this colour onto the slide itself, not behind it, so
    // a fixed black hid every slide's own ground: the editorial matte came out
    // black under its dark title. Black only where the slide sets none.
    const dataUrl = await domToPng(target, {
      width: 1080,
      height: 1920,
      backgroundColor: groundColor(getComputedStyle(target).backgroundColor),
      scale: 1,
    });
    return (dataUrl || "").split(",")[1] || "";
  } catch {
    return "";
  } finally {
    iframe.remove();
    host?.remove();
    for (const link of fonts) link.remove();
  }
}

export function forShadowRoot(cssText) {
  return String(cssText).replace(/:root\b/g, ":host");
}

// Behind a slide that sets no ground of its own: TikTok's own frame.
export const FALLBACK_GROUND = "#000";

export function groundColor(own) {
  return own && own !== "rgba(0, 0, 0, 0)" && own !== "transparent" ? own : FALLBACK_GROUND;
}

// The slide's font stylesheets, lent to this document for the capture. An
// @font-face inside a shadow root is ignored, so a family the app does not
// load itself (any design slide's display face, the templates' Playfair)
// drew in a fallback, and the library embeds only faces it finds in this
// document's sheets. Only Google Fonts, the one host the engine links.
async function adoptFonts(idoc) {
  const links = [];
  for (const source of idoc.querySelectorAll('link[rel="stylesheet"]')) {
    const href = source.getAttribute("href") || "";
    if (!href.startsWith("https://fonts.googleapis.com/")) continue;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.crossOrigin = "anonymous";
    link.href = href;
    links.push(link);
  }
  await Promise.all(links.map((link) => new Promise((res) => {
    link.addEventListener("load", res, { once: true });
    link.addEventListener("error", res, { once: true });
    setTimeout(res, 3000);
    document.head.appendChild(link);
  })));
  return links;
}

// The copy runs in this document, which allows scripts, so it is made inert
// first. The doc is Duct's own template, but its words and image urls come
// from the agent, and no slide needs a script, a frame or a handler to draw.
function inert(node) {
  const nodes = node.querySelectorAll ? [node, ...node.querySelectorAll("*")] : [node];
  for (const el of nodes) {
    if (!el.tagName) continue;
    // SVG animation can set an attribute (an href, a handler) after this pass.
    if (/^(SCRIPT|IFRAME|OBJECT|EMBED|FRAME|BASE|META|ANIMATE|SET|ANIMATETRANSFORM|ANIMATEMOTION|FOREIGNOBJECT)$/i.test(el.tagName)) {
      el.remove();
      continue;
    }
    for (const attr of [...el.attributes]) {
      const value = attr.value.trim().toLowerCase();
      if (attr.name.startsWith("on") || value.startsWith("javascript:")) el.removeAttribute(attr.name);
    }
  }
  return node;
}

function waitForImages(doc, timeoutMs) {
  const imgs = Array.from(doc.images || []);
  if (!imgs.length) return Promise.resolve();
  const all = Promise.all(
    imgs.map((img) =>
      img.complete
        ? Promise.resolve()
        : new Promise((res) => {
            img.addEventListener("load", res, { once: true });
            img.addEventListener("error", res, { once: true });
          }),
    ),
  );
  return Promise.race([all, new Promise((res) => setTimeout(res, timeoutMs))]);
}
