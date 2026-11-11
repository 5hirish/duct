// The same scene as an SVG: every glyph is already a path, so the file needs
// no font and looks the same in a browser, Figma or an image converter.

const n = (v) => Math.round(v * 100) / 100;

function pathData(cmds) {
  return cmds.map((c) => c[0] + c.slice(1).map(n).join(' ')).join('');
}

function escape(s) {
  return String(s).replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
}

export function toSvg(scene, width, height, background, title) {
  const body = scene.map((s) => `<path fill="${s.fill}"${s.opacity !== undefined ? ` fill-opacity="${s.opacity}"` : ''} d="${pathData(s.d)}"/>`).join('\n');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(title)}">\n` +
    `<title>${escape(title)}</title>\n<rect width="${width}" height="${height}" fill="${background}"/>\n${body}\n</svg>\n`;
}
