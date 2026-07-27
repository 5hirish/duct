"use client";

import { domToPng } from "modern-screenshot";

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
    const target = idoc.querySelector(".slide") || idoc.body;
    const dataUrl = await domToPng(target, {
      width: 1080,
      height: 1920,
      backgroundColor: "#000",
      scale: 1,
    });
    return (dataUrl || "").split(",")[1] || "";
  } catch {
    return "";
  } finally {
    iframe.remove();
  }
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
