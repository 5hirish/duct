/**
 * The streaming half of the brief contract — mirror of backend
 * `agents/insights/brief.py`.
 *
 * The backend parses the finished payload and sends the session a structured
 * ARTIFACT_VERSION. But the tag *streams*, and that is the point: the reader
 * watches the brief being written. While it streams there is no parsed version
 * yet, only raw characters — including the front-matter fence the agent opens
 * with. This strips that fence so the pane shows the document rather than its
 * envelope, and pulls the title out of it so the pane can be labelled before
 * the brief is finished.
 *
 * Both functions take partial text and must never throw: they run on every
 * chunk, on a fence that may be half-arrived.
 */

// A *leading* fence only. `---` is ordinary markdown for a section break, and
// eating one of those would delete the top of the brief.
const FENCE = /^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/;
// The fence is still arriving: an opener with no closer yet.
const PARTIAL_FENCE = /^\s*---[ \t]*\r?\n(?![\s\S]*\r?\n---)/;

export function stripFrontMatter(text) {
  const source = text || "";
  if (FENCE.test(source)) return source.replace(FENCE, "");
  // Hold the whole thing back rather than flash raw `title:` lines that are
  // about to become a parsed header.
  if (PARTIAL_FENCE.test(source)) return "";
  return source;
}

export function frontMatterTitle(text) {
  const match = FENCE.exec(text || "");
  if (!match) return "";
  for (const line of match[1].split(/\r?\n/)) {
    const kv = /^\s*title\s*:\s*(.+?)\s*$/i.exec(line);
    if (kv) return kv[1].replace(/^["']|["']$/g, "");
  }
  return "";
}

/** html when the bytes are a document or a tag, markdown otherwise. Mirrors
 *  `sniff_format` — the content decides, never a declaration. */
const HTML_OPENERS = ["<!doctype", "<html", "<head", "<body", "<div", "<section", "<article", "<style"];

export function sniffFormat(body) {
  const head = (body || "").trimStart().slice(0, 200).toLowerCase();
  return HTML_OPENERS.some((opener) => head.startsWith(opener)) ? "html" : "markdown";
}
