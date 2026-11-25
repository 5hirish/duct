// A rendered page as a canvas board, shared by capture.mjs (the app) and
// capture-site.mjs (the marketing site): serialize() runs in the page and
// returns its body as board markup, boardDocument() wraps that markup in the
// Design Component page a board file is. Each caller keeps what is its own:
// how a page is opened, which stylesheet the boards link, where pictures go.

// Runs in the page: the body as board markup. Everything the canvas cannot
// hold goes (scripts, the dev overlay, comments), every image and link is
// marked for the rewrite in Node, and text that would read as a {{hole}} is
// broken with a zero-width space.
export function serialize({ routeToBoard, shots }) {
  const sheets = [...document.querySelectorAll('link[rel="stylesheet"]')].map((l) => l.href);
  const inline = [...document.querySelectorAll("style")].map((s) => s.textContent).filter((t) => t && t.length < 200000);
  // A pane scrolled to the answer stays there: a board has no scroll position.
  // A pane at its end (a transcript, almost always) is pinned to its end, so
  // it still shows the latest turn when the board is narrower and the
  // transcript taller; any other pane is lifted by what was scrolled past,
  // which holds only at the width it was captured at.
  document.querySelectorAll("body *").forEach((el) => {
    if (el.scrollTop <= 0 || !el.firstElementChild) return;
    const atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 4;
    el.setAttribute("data-cap-scroll", atEnd ? "end" : String(Math.round(el.scrollTop)));
  });
  const root = document.body.cloneNode(true);
  const addStyle = (el, css) => el.setAttribute("style", `${el.getAttribute("style") || ""}; ${css}`.replace(/^; /, ""));
  root.querySelectorAll("[data-cap-scroll]").forEach((el) => {
    const at = el.getAttribute("data-cap-scroll");
    // Pinned to its end only while it overflows: on a taller screen than the
    // one it was shot at (2560, 3840) the whole transcript fits, and the app
    // draws it from the top, so a plain flex-end left a hole above it. With
    // one child, column-reverse starts the pane at its end and overflows
    // upward, and the child's auto bottom margin takes any spare room, which
    // puts a transcript that fits at the top.
    if (at === "end" && el.children.length === 1) {
      addStyle(el, "display: flex; flex-direction: column-reverse");
      addStyle(el.firstElementChild, "margin-bottom: auto; flex-shrink: 0");
    } else if (at === "end") {
      addStyle(el, "display: flex; flex-direction: column; justify-content: flex-end");
    }
    else addStyle(el.firstElementChild, `margin-top: -${at}px`);
    el.removeAttribute("data-cap-scroll");
  });
  root.querySelectorAll("script, style, link, noscript, template, nextjs-portal, next-route-announcer, #__next-route-announcer__")
    .forEach((n) => n.remove());
  const comments = document.createTreeWalker(root, NodeFilter.SHOW_COMMENT);
  const dead = [];
  while (comments.nextNode()) dead.push(comments.currentNode);
  dead.forEach((n) => n.remove());

  // A chart is drawn by script at the width it was given (Recharts sets
  // pixel widths on its wrapper and its svg), so on a board it stayed 1440
  // wide while the page around it reflowed: at 1100 the bars ran out of
  // their cards. The app redraws it to the card's width at the same height;
  // a board cannot redraw, so the svg keeps its box's height and scales
  // inside it (its own viewBox, `meet`), and the page keeps the app's height.
  root.querySelectorAll("svg.recharts-surface").forEach((svg) => {
    const w = parseFloat(svg.getAttribute("width"));
    const h = parseFloat(svg.getAttribute("height"));
    if (!w || !h) return;
    if (!svg.getAttribute("viewBox")) svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.removeAttribute("width");
    svg.removeAttribute("height");
    addStyle(svg, "width: 100%; height: 100%; display: block");
    // Every box between the svg and its responsive container goes fluid,
    // the zero-width measuring div Recharts puts in between included.
    const responsive = svg.closest(".recharts-responsive-container");
    for (let box = svg.parentElement; box && box !== responsive; box = box.parentElement) {
      addStyle(box, `width: 100%; height: ${responsive ? "100%" : `${h}px`}`);
    }
  });

  root.querySelectorAll("[data-cap-shot]").forEach((el) => {
    // The attribute only says which frame this was; its picture's name is
    // capture()'s, and a frame whose screenshot failed is left out.
    const i = el.getAttribute("data-cap-shot");
    const name = Object.hasOwn(shots, i) ? shots[i] : null;
    if (!name) return el.remove();
    // The picture takes the frame's layout box, not its painted one: a
    // thumbnail is a full-size frame scaled down by a transform, and the
    // picture inherits that transform with the frame's class and style, so
    // sizing it to the painted box scaled it down twice.
    const live = document.querySelector(`[data-cap-shot="${CSS.escape(i)}"]`);
    const w = live?.offsetWidth ?? 0;
    const h = live?.offsetHeight ?? 0;
    const scaled = live && getComputedStyle(live).transform !== "none";
    const img = document.createElement("img");
    img.setAttribute("src", `img/${name}`);
    img.setAttribute("alt", el.getAttribute("title") || "");
    if (el.getAttribute("class")) img.setAttribute("class", el.getAttribute("class"));
    const own = el.getAttribute("style") ? `${el.getAttribute("style").replace(/;?\s*$/, "")}; ` : "";
    img.setAttribute("style", `${own}display: block; width: ${w}px; height: ${h}px;${scaled ? "" : " max-width: 100%;"} object-fit: cover; object-position: left top`);
    el.replaceWith(img);
  });

  // React builds a <p> around block content (a <details>, a <pre>) as the DOM
  // allows, but an HTML parser closes the <p> at the first block and the board
  // comes out restructured. A <div> renders the same under the app's reset.
  root.querySelectorAll("p").forEach((p) => {
    if (!p.querySelector("div, details, pre, ul, ol, table, section, figure, form, blockquote, hr, h1, h2, h3, h4, h5, h6")) return;
    const div = document.createElement("div");
    for (const a of p.attributes) div.setAttribute(a.name, a.value);
    div.append(...p.childNodes);
    p.replaceWith(div);
  });

  root.querySelectorAll("img").forEach((img) => {
    const src = img.getAttribute("src");
    if (!src || src.startsWith("img/") || src.startsWith("data:")) return;
    let url = new URL(src, location.href);
    // next/image's optimiser: the original is in its `url` parameter.
    if (url.pathname === "/_next/image" && url.searchParams.get("url")) url = new URL(url.searchParams.get("url"), location.href);
    img.setAttribute("src", `__IMG[${url.href}]__`);
    for (const a of ["srcset", "sizes", "loading", "decoding", "fetchpriority", "data-nimg"]) img.removeAttribute(a);
  });
  root.querySelectorAll("[style*='url(']").forEach((el) => {
    el.setAttribute("style", el.getAttribute("style").replace(/url\((['"]?)([^'")]+)\1\)/g, (m, q, u) =>
      u.startsWith("data:") ? m : `url("__IMG[${new URL(u, location.href).href}]__")`));
  });

  root.querySelectorAll("a[href]").forEach((a) => {
    const u = new URL(a.getAttribute("href"), location.href);
    if (u.origin !== location.origin) return;
    if (u.pathname === location.pathname && u.hash) return;
    a.setAttribute("href", routeToBoard[u.pathname] || "#");
  });
  root.querySelectorAll("form").forEach((f) => f.removeAttribute("action"));
  // An empty boolean attribute is false to React; say it out loud.
  for (const name of ["disabled", "checked", "selected", "readonly", "required", "hidden", "open", "multiple", "autofocus", "novalidate", "inert"]) {
    root.querySelectorAll(`[${name}]`).forEach((el) => {
      if (el.getAttribute(name) === "") el.setAttribute(name, name);
    });
  }
  root.querySelectorAll("*").forEach((el) => {
    for (const a of [...el.attributes]) if (/^on/i.test(a.name)) el.removeAttribute(a.name);
  });
  const texts = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (texts.nextNode()) {
    const t = texts.currentNode;
    if (t.data.includes("{{") || t.data.includes("}}")) t.data = t.data.replace(/\{\{/g, "{​{").replace(/\}\}/g, "}​}");
  }
  return {
    html: root.innerHTML,
    htmlClass: document.documentElement.className,
    bodyClass: document.body.className,
    height: document.documentElement.scrollHeight,
    sheets,
    inline,
  };
}

export function boardDocument({ title, rootClass, html, width, height, workspace, inline = "", stylesheet = "duct-app.css" }) {
  const props = JSON.stringify({ $preview: { width, height } });
  // A workspace fills its window and scrolls inside; a framed page grows with
  // its content, so the board's root takes the page's own height.
  const rootStyle = workspace ? "height: 100vh; overflow: hidden" : "min-height: 100vh";
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${escapeHtml(title)}</title>
<script src="./support.js"></script>
<link rel="stylesheet" href="${escapeHtml(stylesheet)}">
</head>
<body>
<x-dc>
<helmet>
<style>
body{margin:0}
${inline.replace(/<\/style/gi, "<\\/style")}
</style>
</helmet>
<div class="${escapeHtml(rootClass)}" style="${rootStyle}">
${html.trim()}
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='${props}'>
class Component extends DCLogic {
renderVals() { return {}; }
}
</script>
</body>
</html>
`;
}

export function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
