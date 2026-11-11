// Sitemaps (sitemaps.org protocol): a urlset of <loc>s, or an index of
// further sitemaps. A single file may hold 50,000 URLs and 50 MB uncompressed.

export const SITEMAP_MAX_URLS = 50000;
export const SITEMAP_MAX_BYTES = 50 * 1024 * 1024;

const decode = (s) => s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").trim();

export function parseSitemap(xml) {
  const isIndex = /<sitemapindex[\s>]/i.test(xml);
  const entries = [];
  const block = isIndex ? /<sitemap[\s>]([\s\S]*?)<\/sitemap>/gi : /<url[\s>]([\s\S]*?)<\/url>/gi;
  let m;
  while ((m = block.exec(xml))) {
    const loc = /<loc>\s*(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?\s*<\/loc>/i.exec(m[1]);
    if (!loc) continue;
    const lastmod = /<lastmod>([\s\S]*?)<\/lastmod>/i.exec(m[1]);
    entries.push({ loc: decode(loc[1]), lastmod: lastmod ? lastmod[1].trim() : null });
  }
  return { isIndex, entries };
}

// Up to n entries spread evenly over the list, so a sample of a large
// sitemap is not just its first section.
export function spread(list, n) {
  if (list.length <= n) return list.slice();
  const out = [];
  for (let i = 0; i < n; i++) out.push(list[Math.floor((i * list.length) / n)]);
  return out;
}
