// Client-side slide renderer — a JS mirror of backend agents/content/templates.py.
//
// The backend renders the authoritative `slides_html` on every save, but for a
// LIVE preview while the user edits captions/styles we render each slide here
// from the structured `slides` data. We reuse the CSS that the backend already
// inlined into `slides_html` (base engine + every caption style + layout +
// placeholder CSS — all static, content-independent), so the preview matches
// what the server will produce on commit. Keep this in sync with templates.py.

function escAttr(s) {
  return String(s || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#x27;");
}

// Escape caption copy but honour intentional line breaks (\n or <br>).
function escCap(s) {
  let t = String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  t = t.replace(/\n/g, "<br>");
  t = t.replace(/&lt;br\s*\/?&gt;/gi, "<br>");
  return t;
}

function pad(n) {
  return String(n).padStart(2, "0");
}

function captionInner(style, headline, subtext) {
  const H = escCap(headline);
  const S = escCap(subtext);
  if (style === "hook") {
    return `<span class="hook-headline">${H}</span>${subtext ? `<span class="hook-sub">${S}</span>` : ""}`;
  }
  if (style === "cap-pill") {
    return `<span class="cap-pill-wrap"><span class="cap-pill">${H}</span></span>${subtext ? `<span class="cap-pill-sub"><span>${S}</span></span>` : ""}`;
  }
  const k = ["cap-stroke", "cap-raw", "cap-whisper"].includes(style) ? style : "cap-stroke";
  return `<span class="${k}">${H}</span>${subtext ? `<span class="${k}-sub">${S}</span>` : ""}`;
}

function isStale(prompt, used) {
  return (prompt || "").trim() !== (used || "").trim();
}

function fullImageLayer(slide) {
  const alt = escAttr(slide.image_prompt || slide.headline || slide.slide_id);
  if (slide.image_url) {
    let o = `<img class="bg" src="${escAttr(slide.image_url)}" alt="${alt}">`;
    if (isStale(slide.image_prompt, slide.image_prompt_used)) {
      o += `<div class="img-stale-flag">image outdated — regenerate to match the new prompt</div>`;
    }
    return o;
  }
  let badge = `image · ${escAttr(slide.aspect_ratio || "9:16")}`;
  if (slide.role) badge += ` · ${escAttr(slide.role)}`;
  // Clamp the prompt to a few lines (CSS in buildSlideDoc) so a long prompt
  // can't overflow the frame and collide with the caption; full text on hover.
  const prompt = (slide.image_prompt || "").trim()
    ? `<div class="img-ph-prompt" title="${escAttr(slide.image_prompt)}">${escCap(slide.image_prompt)}</div>`
    : `<div class="img-ph-prompt is-empty">no image prompt yet</div>`;
  return `<div class="img-placeholder"><div class="img-placeholder-inner"><div class="img-ph-badge">${badge}</div>${prompt}</div></div>`;
}

function cellImgOrPh(it) {
  if (it.image_url) {
    let o = `<img class="cell-img" src="${escAttr(it.image_url)}" alt="${escAttr(it.image_prompt)}">`;
    if (isStale(it.image_prompt, it.image_prompt_used)) o += `<div class="cell-stale-flag">outdated</div>`;
    return o;
  }
  if ((it.image_prompt || "").trim()) {
    return `<div class="cell-ph"><div class="cell-ph-text" title="${escAttr(it.image_prompt)}">${escCap(it.image_prompt)}</div></div>`;
  }
  return `<div class="cell-ph"><div class="cell-ph-text is-empty">no prompt yet</div></div>`;
}

function renderPhoto(slide, n) {
  let cap = "";
  if (slide.headline || slide.subtext) {
    cap = `<div class="cap-bottom">${captionInner(slide.caption_style || "cap-stroke", slide.headline, slide.subtext)}</div>`;
  }
  return `<div class="slide slide-hook" id="slide-${pad(n)}">${fullImageLayer(slide)}<div class="grad"></div>${cap}</div>`;
}

function renderText(slide, n) {
  let body = `<span class="body-statement">${escCap(slide.headline)}</span>`;
  if (slide.subtext) body += `<span class="body-sub">${escCap(slide.subtext)}</span>`;
  return `<div class="slide slide-body" id="slide-${pad(n)}"><div class="body-content">${body}</div></div>`;
}

function renderCollage(slide, n) {
  const title = slide.headline
    ? `<div class="collage-title"><span class="ctitle">${escCap(slide.headline)}</span></div>` : "";
  const cells = (slide.items || []).slice(0, 4).map((it) => {
    const label = it.label ? `<div class="cell-label">${escCap(it.label)}</div>` : "";
    return `<div class="cell">${cellImgOrPh(it)}${label}</div>`;
  }).join("");
  return `<div class="slide slide-collage" id="slide-${pad(n)}">${title}<div class="collage-grid">${cells}</div></div>`;
}

const BA_DEFAULT = ["dont", "do"];

function renderBeforeAfter(slide, n) {
  const halves = (slide.items || []).slice(0, 2).map((it, i) => {
    const marker = it.marker || BA_DEFAULT[i] || "";
    let mk = "";
    if (marker === "dont") mk = `<div class="ba-marker dont">✕ DON'T</div>`;
    else if (marker === "do") mk = `<div class="ba-marker do">✓ DO</div>`;
    const label = it.label ? `<div class="cell-label">${escCap(it.label)}</div>` : "";
    return `<div class="ba-half cell">${cellImgOrPh(it)}${mk}${label}</div>`;
  }).join("");
  return `<div class="slide slide-ba" id="slide-${pad(n)}">${halves}</div>`;
}

function renderEditorial(slide, n) {
  const frame = `<div class="ed-frame cell">${cellImgOrPh(slide)}</div>`;
  let title = "";
  if (slide.headline || slide.subtext) {
    const t = slide.headline ? `<span class="et">${escCap(slide.headline)}</span>` : "";
    const s = slide.subtext ? `<span class="es">${escCap(slide.subtext)}</span>` : "";
    title = `<div class="ed-title">${t}${s}</div>`;
  }
  return `<div class="slide slide-editorial" id="slide-${pad(n)}">${frame}${title}</div>`;
}

export function renderSlideBody(slide, n) {
  if (!slide) return "";
  if (slide.kind === "text") return renderText(slide, n);
  if (slide.kind === "collage" && (slide.items || []).length) return renderCollage(slide, n);
  if (slide.kind === "before-after" && (slide.items || []).length) return renderBeforeAfter(slide, n);
  if (slide.kind === "editorial") return renderEditorial(slide, n);
  return renderPhoto(slide, n);
}

// Pull the <link rel=stylesheet> font tags + the single <style> block out of a
// backend-rendered slides_html doc. That CSS is static (content-independent),
// so we reuse it verbatim as the <head> for live per-slide previews.
export function extractStyleHead(slidesHtml) {
  if (!slidesHtml) return "";
  const styles = (String(slidesHtml).match(/<style[\s\S]*?<\/style>/gi) || []).join("\n");
  const links = (String(slidesHtml).match(/<link[^>]*>/gi) || []).join("\n");
  return `${links}\n${styles}`;
}

// Build a single-slide document scaled by `zoom` (1 css px = 1080/W of canvas).
export function buildSlideDoc(slide, n, headHtml, zoom) {
  return (
    `<!doctype html><html><head><meta charset="utf-8">${headHtml}` +
    `<style>:root{--zoom:${zoom}} html,body{margin:0;padding:0;background:#000} ` +
    `body{display:block !important;align-items:initial;gap:0} ` +
    // Truncate long image-prompt placeholders to a few lines with an ellipsis so
    // they stay inside the frame; the full prompt shows on hover (title attr).
    `.img-ph-prompt{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:7;line-clamp:7;overflow:hidden} ` +
    `.cell-ph-text{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:4;line-clamp:4;overflow:hidden}</style>` +
    `</head><body>${renderSlideBody(slide, n)}</body></html>`
  );
}
