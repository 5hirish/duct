/**
 * Streaming markdown, split into what is settled and what is still arriving.
 *
 * Re-parsing a whole reply on every token is what makes a streamed table
 * reflow its columns and a list renumber as it grows. The fix OpenCode uses:
 * everything up to the last block boundary is *settled* — parsed once and
 * kept — and only the tail is re-rendered per delta, after being healed so an
 * unfinished construct does not render as its literal characters.
 *
 * Pure functions, no React: the component memoises on the settled text.
 */

const FENCE = /^ {0,3}(`{3,}|~{3,})/;
const TABLE_ROW = /^\s*\|/;

/**
 * Split `text` at the last block boundary — a blank line outside a code
 * fence. Returns `{ settled, tail }`; `settled` ends with its own newlines so
 * the two concatenate back to `text`. The tail is never empty when the text
 * is not: a trailing blank line belongs to the tail.
 */
export function splitSettled(text) {
  const source = String(text || "");
  if (!source) return { settled: "", tail: "" };
  const lines = source.split("\n");
  // A boundary is only useful with something live after it: the tail is what
  // keeps rendering, so trailing blank lines stay in it.
  let lastContent = lines.length - 1;
  while (lastContent > 0 && lines[lastContent].trim() === "") lastContent -= 1;
  let fence = null;          // the marker that opened the fence we are inside
  let boundary = -1;         // index of the blank line that ends the settled part
  for (let i = 0; i < lastContent; i++) {
    const line = lines[i];
    const m = line.match(FENCE);
    if (m) {
      if (!fence) fence = m[1];
      else if (m[1][0] === fence[0] && m[1].length >= fence.length) fence = null;
      continue;
    }
    if (!fence && line.trim() === "" && i > 0) boundary = i;
  }
  if (boundary < 0) return { settled: "", tail: source };
  const settled = lines.slice(0, boundary + 1).join("\n") + "\n";
  return { settled, tail: source.slice(settled.length) };
}

function countUnescaped(text, token) {
  let n = 0;
  for (let i = text.indexOf(token); i !== -1; i = text.indexOf(token, i + token.length)) {
    if (text[i - 1] !== "\\") n += 1;
  }
  return n;
}

/**
 * Close what the tail has opened so it renders as prose, not as markup that
 * has not finished: an open fence, unbalanced bold, italic or inline code,
 * and a link whose target has not arrived. A table's partial last row is
 * dropped, because a half row is a column count the table does not have.
 */
export function healTail(tail) {
  let text = String(tail || "");
  if (!text) return text;

  // An open fence: close it. Everything inside is code, so no other healing.
  const lines = text.split("\n");
  let fence = null;
  for (const line of lines) {
    const m = line.match(FENCE);
    if (!m) continue;
    if (!fence) fence = m[1];
    else if (m[1][0] === fence[0] && m[1].length >= fence.length) fence = null;
  }
  if (fence) return text + (text.endsWith("\n") ? "" : "\n") + fence;

  // A table being streamed: keep only its complete rows. A row is complete
  // when it closes with a pipe and has as many cells as the header.
  if (lines.length > 1 && TABLE_ROW.test(lines[0])) {
    const last = lines[lines.length - 1];
    const cells = (row) => row.split(/(?<!\\)\|/).slice(1, -1).length;
    if (last.trim() !== "" && (!/\|\s*$/.test(last) || cells(last) < cells(lines[0]))) {
      text = lines.slice(0, -1).join("\n") + "\n";
    }
  }

  // A link whose `](url)` has not arrived yet: show its text.
  text = text.replace(/\[([^\]\n]*)$/, "$1").replace(/\[([^\]\n]+)\]\([^)\n]*$/, "$1");

  // Inline code, then bold, then italic — outer constructs first.
  if (countUnescaped(text, "`") % 2 === 1) text += "`";
  if (countUnescaped(text, "**") % 2 === 1) text += "**";
  const singles = countUnescaped(text, "*") - countUnescaped(text, "**") * 2;
  if (singles % 2 === 1) text += "*";
  return text;
}
