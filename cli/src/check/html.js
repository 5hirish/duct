// Read what a launch check needs out of an HTML page.
//
// A tokenizer, not a regex over the page: minified HTML leaves attributes
// unquoted (`<meta name=description content=...>`), and a pattern that
// expects quotes reports the tag missing when it is there. That exact trap
// is in the skill's step 2.

const RAW_TEXT = new Set(['script', 'style', 'textarea', 'title', 'noscript', 'template']);
const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);
const HIDDEN = new Set(['script', 'style', 'noscript', 'template', 'svg', 'head', 'title']);
const BLOCK = new Set(['p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section', 'article', 'header', 'footer', 'nav', 'main', 'br', 'tr', 'td', 'th', 'ul', 'ol', 'dd', 'dt', 'blockquote', 'figcaption', 'pre', 'button', 'a']);

const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', middot: '·', mdash: '—', ndash: '–', hellip: '…', rsquo: '’', lsquo: '‘', rdquo: '”', ldquo: '“', copy: '©', reg: '®', trade: '™', rarr: '→', larr: '←', times: '×', bull: '•' };

export function decodeEntities(s) {
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => {
    if (e[0] === '#') {
      const cp = e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      try { return String.fromCodePoint(cp); } catch { return m; }
    }
    return ENTITIES[e.toLowerCase()] ?? m;
  });
}

const ATTR = /([^\s=/>"']+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;

function parseAttrs(s) {
  const attrs = {};
  let m;
  ATTR.lastIndex = 0;
  while ((m = ATTR.exec(s))) {
    const name = m[1].toLowerCase();
    if (name in attrs) continue;
    attrs[name] = decodeEntities(m[2] ?? m[3] ?? m[4] ?? '');
  }
  return attrs;
}

export function tokenize(html) {
  const tokens = [];
  let i = 0;
  const n = html.length;
  while (i < n) {
    const lt = html.indexOf('<', i);
    if (lt === -1) { tokens.push({ type: 'text', text: html.slice(i) }); break; }
    if (lt > i) tokens.push({ type: 'text', text: html.slice(i, lt) });
    if (html.startsWith('<!--', lt)) {
      const end = html.indexOf('-->', lt + 4);
      i = end === -1 ? n : end + 3;
      continue;
    }
    if (html[lt + 1] === '!' || html[lt + 1] === '?') {
      const end = html.indexOf('>', lt);
      i = end === -1 ? n : end + 1;
      continue;
    }
    const m = /^<(\/?)([a-zA-Z][a-zA-Z0-9:-]*)/.exec(html.slice(lt, lt + 64));
    if (!m) { tokens.push({ type: 'text', text: '<' }); i = lt + 1; continue; }
    // Find the tag's end, skipping '>' inside quoted attribute values.
    let j = lt + m[0].length, quote = null;
    while (j < n) {
      const c = html[j];
      if (quote) { if (c === quote) quote = null; }
      else if (c === '"' || c === "'") {
        // Only a quote right after `=` opens a value; a stray one does not.
        if (/=\s*$/.test(html.slice(Math.max(lt, j - 8), j))) quote = c;
      } else if (c === '>') break;
      j++;
    }
    const name = m[2].toLowerCase();
    const inner = html.slice(lt + m[0].length, j);
    i = j + 1;
    if (m[1]) { tokens.push({ type: 'end', name }); continue; }
    // `<a href=/>` is href="/", not a self-closing <a>: an unquoted value
    // takes the slash. Only a slash after a space, a quote or the name closes.
    const closing = /(^|\s|["'])\/\s*$/.test(inner);
    const selfClosing = closing || VOID.has(name);
    tokens.push({ type: 'start', name, attrs: parseAttrs(closing ? inner.replace(/\/\s*$/, '') : inner), selfClosing });
    if (RAW_TEXT.has(name) && !selfClosing) {
      const close = html.toLowerCase().indexOf(`</${name}`, i);
      const end = close === -1 ? n : close;
      tokens.push({ type: 'text', text: html.slice(i, end), raw: name });
      i = end;
    }
  }
  return tokens;
}

const clean = (s) => decodeEntities(s).replace(/\s+/g, ' ').trim();

export function parseHtml(html) {
  const tokens = tokenize(html);
  const page = {
    title: null, titles: 0, lang: null, refresh: null, metas: [], h1LogoOnly: [], links: [], h1: [], jsonLd: [], scripts: [], inlineScripts: [],
    anchors: [], buttons: [], text: '', mainText: '', firstParagraph: null,
  };
  const open = { nav: 0, header: 0, footer: 0, main: 0, hidden: 0 };
  let h1Buf = null, aBuf = null, btnBuf = null, pBuf = null, sawH1 = false, h1Text = false;
  const textParts = [], outsideNavParts = [], insideMainParts = [];
  // A block boundary or a <br> is a word boundary, even inside an H1 or a link.
  const breakText = () => {
    for (const parts of [textParts, outsideNavParts, insideMainParts, h1Buf, aBuf?.text, btnBuf?.text, pBuf]) parts?.push(' ');
  };

  for (const tok of tokens) {
    if (tok.type === 'start') {
      const { name, attrs } = tok;
      if (name === 'html' && attrs.lang) page.lang = attrs.lang;
      if (name === 'meta') {
        page.metas.push(attrs);
        if ((attrs['http-equiv'] ?? '').toLowerCase() === 'refresh' && /url\s*=/i.test(attrs.content ?? '')) page.refresh = attrs.content;
      }
      if (name === 'link') page.links.push(attrs);
      if (name === 'script') {
        if (attrs.src) page.scripts.push(attrs);
        else if (/ld\+json/i.test(attrs.type ?? '')) page.jsonLd.push(null); // body follows as text
      }
      if (tok.selfClosing && name !== 'img' && name !== 'br') continue;
      if (name in open && name !== 'hidden') open[name]++;
      if (HIDDEN.has(name) && !tok.selfClosing) open.hidden++;
      if (BLOCK.has(name)) breakText();
      if (name === 'h1') { h1Buf = []; h1Text = false; }
      if (name === 'img' && attrs.alt) {
        h1Buf?.push(` ${attrs.alt} `);
        aBuf?.text.push(` ${attrs.alt} `);
      }
      if (name === 'a' && !aBuf) {
        aBuf = { href: attrs.href ?? null, cls: attrs.class ?? '', role: attrs.role ?? '', hreflang: attrs.hreflang ?? null, text: [], afterH1: sawH1,
          inNav: open.nav > 0, inHeader: open.header > 0, inFooter: open.footer > 0, inMain: open.main > 0, attrs };
      }
      if (name === 'button') btnBuf = { cls: attrs.class ?? '', text: [], afterH1: sawH1, type: attrs.type ?? '' };
      if (name === 'p' && sawH1 && !page.firstParagraph && !open.nav && !open.footer) pBuf = [];
      continue;
    }
    if (tok.type === 'end') {
      const { name } = tok;
      if (name in open && name !== 'hidden' && open[name] > 0) open[name]--;
      if (HIDDEN.has(name) && open.hidden > 0) open.hidden--;
      if (BLOCK.has(name)) breakText();
      if (name === 'h1' && h1Buf) {
        page.h1.push(clean(h1Buf.join('')));
        // Only an image inside: the logo, which says nothing about the page.
        page.h1LogoOnly.push(!h1Text);
        h1Buf = null; sawH1 = true;
      }
      if (name === 'a' && aBuf) { page.anchors.push({ ...aBuf, text: clean(aBuf.text.join('')) }); aBuf = null; }
      if (name === 'button' && btnBuf) { page.buttons.push({ ...btnBuf, text: clean(btnBuf.text.join('')) }); btnBuf = null; }
      if (name === 'p' && pBuf) {
        const t = clean(pBuf.join(''));
        if (t.length >= 20) page.firstParagraph = t;
        pBuf = null;
      }
      continue;
    }
    // Text.
    if (tok.raw === 'title') {
      page.titles++;
      if (page.title === null) page.title = clean(tok.text);
      continue;
    }
    if (tok.raw === 'script') {
      const last = page.jsonLd.length - 1;
      if (last >= 0 && page.jsonLd[last] === null) page.jsonLd[last] = tok.text;
      else if (tok.text.trim()) page.inlineScripts.push(tok.text);
      continue;
    }
    if (tok.raw) continue;
    if (open.hidden) continue;
    textParts.push(tok.text);
    if (!open.nav && !open.header && !open.footer) outsideNavParts.push(tok.text);
    if (open.main) insideMainParts.push(tok.text);
    if (h1Buf && tok.text.trim()) h1Text = true;
    h1Buf?.push(tok.text);
    aBuf?.text.push(tok.text);
    btnBuf?.text.push(tok.text);
    pBuf?.push(tok.text);
  }
  page.jsonLd = page.jsonLd.filter((s) => s !== null);
  page.text = clean(textParts.join(''));
  // "Main content" is <main> when the page has one; otherwise everything
  // outside the navigation, header and footer.
  const inside = clean(insideMainParts.join(''));
  page.mainText = inside || clean(outsideNavParts.join(''));
  page.hasNav = page.anchors.some((a) => a.inNav || a.inHeader);
  return page;
}

export function meta(page, key) {
  key = key.toLowerCase();
  const m = page.metas.find((a) => (a.name ?? a.property ?? '').toLowerCase() === key
    || (a.property ?? '').toLowerCase() === key);
  return m ? (m.content ?? '').trim() : null;
}

export function linkRel(page, rel) {
  const l = page.links.find((a) => (a.rel ?? '').toLowerCase().split(/\s+/).includes(rel));
  return l ? (l.href ?? '').trim() : null;
}

// Every @type in the page's JSON-LD, and whether it carries reviews.
export function jsonLdSummary(page) {
  const types = new Set();
  const reviews = [];
  const walk = (node, path) => {
    if (Array.isArray(node)) { node.forEach((n) => walk(n, path)); return; }
    if (!node || typeof node !== 'object') return;
    for (const t of [].concat(node['@type'] ?? [])) types.add(String(t));
    const typeList = [].concat(node['@type'] ?? []).map(String);
    if (typeList.includes('Review') || typeList.includes('AggregateRating')) reviews.push(node);
    for (const [k, v] of Object.entries(node)) {
      if (k === 'review' || k === 'aggregateRating') {
        for (const r of [].concat(v)) if (r && typeof r === 'object') reviews.push(r);
      }
      if (v && typeof v === 'object') walk(v, `${path}.${k}`);
    }
  };
  let invalid = 0;
  for (const block of page.jsonLd) {
    try { walk(JSON.parse(block), ''); } catch { invalid++; }
  }
  return { types: [...types], reviews: [...new Set(reviews)], invalid };
}
