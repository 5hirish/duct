/**
 * What a person attaches to a message, in both directions.
 *
 * Outbound: the composer holds `{ name, mediaType, kind, size, data | text,
 * preview }` and `contentBlocks` turns that plus the typed text into the
 * content-block list the chat route accepts. Inbound: `describeContent`
 * reads that same list back into text plus attachment tiles — for the row
 * the reducer draws the moment the message is sent, and for a reopened
 * thread, where the stored USER row is the list as it went out. One parser
 * for both, so the live row and the replayed row cannot disagree.
 *
 * Three shapes travel:
 *   image  → an image block (the Messages API shape every adapter accepts)
 *   pdf    → a `file` block in LangChain's standard shape, which each
 *            provider adapter turns into its own document part
 *   text   → a text block wrapped in an <attachment> element, because a
 *            spreadsheet pasted from a clipboard is text to the model and a
 *            tile to the reader; the wrapper is what lets the reader's side
 *            find it again
 */

export const AttachmentKind = Object.freeze({
  IMAGE: "image",
  PDF: "pdf",
  TEXT: "text",
  FILE: "file",
});

// Base64 rides in the request body and then in every checkpoint of the
// thread; past this a single attachment is most of a conversation's storage.
export const ATTACH_MAX_BYTES = 8 * 1024 * 1024;

// A paste longer than this becomes a tile rather than a wall of text in the
// box: the reader keeps the message readable and the model still gets every
// character.
export const PASTE_ATTACH_LINES = 25;
export const PASTE_ATTACH_CHARS = 3000;

const TEXT_EXTENSIONS = new Set([
  "txt", "md", "markdown", "csv", "tsv", "json", "html", "htm", "xml", "yaml", "yml",
  "js", "jsx", "ts", "tsx", "py", "css", "sql", "log", "sh",
]);
const TEXT_MEDIA_TYPES = new Set([
  "application/json", "application/xml", "application/javascript", "application/x-yaml",
  "application/yaml", "application/sql", "image/svg+xml",
]);
const EXTENSION_MEDIA_TYPES = {
  txt: "text/plain", md: "text/markdown", markdown: "text/markdown", csv: "text/csv",
  tsv: "text/tab-separated-values", json: "application/json", html: "text/html", htm: "text/html",
  xml: "application/xml", yaml: "application/x-yaml", yml: "application/x-yaml", pdf: "application/pdf",
};

export function extensionOf(name = "") {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : "";
}

/** The media type to send when the browser gave none (it does for .md). */
export function mediaTypeFor(name = "", given = "") {
  return given || EXTENSION_MEDIA_TYPES[extensionOf(name)] || "";
}

export function attachmentKind(mediaType = "", name = "") {
  if (mediaType.startsWith("image/") && mediaType !== "image/svg+xml") return AttachmentKind.IMAGE;
  if (mediaType === "application/pdf" || extensionOf(name) === "pdf") return AttachmentKind.PDF;
  if (mediaType.startsWith("text/") || TEXT_MEDIA_TYPES.has(mediaType) || TEXT_EXTENSIONS.has(extensionOf(name))) {
    return AttachmentKind.TEXT;
  }
  return AttachmentKind.FILE;
}

/** The badge on a tile: "PDF", "CSV", "PNG" — the extension when the name
 *  has one, the media subtype otherwise, never blank. */
export function attachmentLabel(mediaType = "", name = "") {
  const ext = extensionOf(name);
  if (ext) return ext.toUpperCase();
  const sub = mediaType.split("/")[1] || "";
  return (sub.split("+")[0] || "FILE").toUpperCase();
}

export function isLargePaste(text = "") {
  return text.length > PASTE_ATTACH_CHARS || text.split("\n").length > PASTE_ATTACH_LINES;
}

/**
 * What a pasted block of text most likely is, from its shape: JSON that
 * parses, an HTML document, rows with a steady delimiter, Markdown
 * structure, else plain text. The type sets the tile's badge and the media
 * type the model is told — a CSV read as prose is a worse answer.
 */
export function sniffPaste(text = "") {
  const trimmed = text.trim();
  if (/^[[{]/.test(trimmed)) {
    try {
      JSON.parse(trimmed);
      return { ext: "json", mediaType: "application/json" };
    } catch {
      // Not JSON after all; fall through to the other shapes.
    }
  }
  if (/^<(!doctype\s+html|html|head|body)\b/i.test(trimmed)) return { ext: "html", mediaType: "text/html" };
  const delimited = delimitedRows(trimmed);
  if (delimited) return delimited;
  if (/^(#{1,6}\s|[-*]\s|\d+\.\s|```)/m.test(trimmed) && /\n/.test(trimmed)) {
    return { ext: "md", mediaType: "text/markdown" };
  }
  return { ext: "txt", mediaType: "text/plain" };
}

function delimitedRows(text) {
  const lines = text.split("\n").filter((l) => l.trim()).slice(0, 20);
  if (lines.length < 3) return null;
  for (const [delimiter, ext, mediaType] of [["\t", "tsv", "text/tab-separated-values"], [",", "csv", "text/csv"]]) {
    const counts = lines.map((l) => l.split(delimiter).length - 1);
    if (counts[0] > 0 && counts.every((c) => c === counts[0])) return { ext, mediaType };
  }
  return null;
}

/** A large paste as a tile. `n` numbers it among the message's pastes. */
export function pastedAttachment(text, n = 1) {
  const { ext, mediaType } = sniffPaste(text);
  return {
    name: `pasted-${n}.${ext}`,
    mediaType,
    kind: AttachmentKind.TEXT,
    size: text.length,
    text,
  };
}

// The wrapper a text attachment travels in. Quotes in a name become
// apostrophes so the element stays parseable; a filename is a label, not data.
function safeName(name) {
  return String(name || "attachment").replace(/"/g, "'");
}

function textBlock(att) {
  return {
    type: "text",
    text: `<attachment name="${safeName(att.name)}" type="${att.mediaType || "text/plain"}">\n${att.text || ""}\n</attachment>`,
  };
}

/**
 * The message as the chat route takes it: a plain string when there is
 * nothing attached (what every message was before attachments existed), else
 * the typed text first and one block per attachment.
 */
export function contentBlocks(text, attachments = []) {
  const trimmed = (text || "").trim();
  if (!attachments.length) return trimmed;
  const blocks = [];
  if (trimmed) blocks.push({ type: "text", text: trimmed });
  for (const att of attachments) {
    switch (att.kind) {
      case AttachmentKind.IMAGE:
        blocks.push({ type: "image", source: { type: "base64", media_type: att.mediaType, data: att.data } });
        break;
      case AttachmentKind.PDF:
        blocks.push({ type: "file", base64: att.data, mime_type: att.mediaType || "application/pdf", filename: att.name });
        break;
      default:
        blocks.push(textBlock(att));
    }
  }
  return blocks;
}

const ATTACHMENT_RE = /<attachment name="([^"]*)" type="([^"]*)">\n?([\s\S]*?)\n?<\/attachment>/g;

/**
 * A message's content, whichever shape it is in, as the text to show and
 * the tiles to draw beside it. An image gets a data-URI preview built from
 * its own bytes; a PDF and a text file get their name and badge.
 */
export function describeContent(content) {
  if (typeof content === "string") return unwrapText(content);
  if (!Array.isArray(content)) return { text: "", attachments: [] };
  const texts = [];
  const attachments = [];
  for (const block of content) {
    if (!block || typeof block !== "object") continue;
    if (block.type === "text") {
      const inner = unwrapText(block.text || "");
      if (inner.text) texts.push(inner.text);
      attachments.push(...inner.attachments);
    } else if (block.type === "image") {
      const mediaType = block.source?.media_type || block.mime_type || "image/png";
      const data = block.source?.data || block.base64 || "";
      attachments.push({
        name: block.filename || "image",
        mediaType,
        kind: AttachmentKind.IMAGE,
        preview: data ? `data:${mediaType};base64,${data}` : block.source?.url || block.url || "",
      });
    } else if (block.type === "file") {
      const mediaType = block.mime_type || "application/pdf";
      attachments.push({ name: block.filename || "document", mediaType, kind: attachmentKind(mediaType, block.filename) });
    }
  }
  return { text: texts.join("\n\n").trim(), attachments };
}

function unwrapText(text) {
  const attachments = [];
  const rest = text.replace(ATTACHMENT_RE, (_m, name, mediaType, body) => {
    attachments.push({ name, mediaType, kind: AttachmentKind.TEXT, size: body.length, text: body });
    return "";
  });
  return { text: rest.trim(), attachments };
}
