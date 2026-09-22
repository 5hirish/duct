import { describe, expect, it } from "vitest";
import {
  AttachmentKind,
  attachmentKind,
  attachmentLabel,
  contentBlocks,
  describeContent,
  isLargePaste,
  mediaTypeFor,
  pastedAttachment,
  sniffPaste,
} from "../attachments";

describe("what a paste is", () => {
  it("names the shape from the text, not the clipboard's claim", () => {
    expect(sniffPaste('{"a": 1, "b": [2, 3]}')).toEqual({ ext: "json", mediaType: "application/json" });
    expect(sniffPaste("<!DOCTYPE html><html><body>hi</body></html>")).toEqual({ ext: "html", mediaType: "text/html" });
    expect(sniffPaste("date,sessions,cpa\n2026-09-01,120,4.2\n2026-09-02,131,3.9")).toEqual({ ext: "csv", mediaType: "text/csv" });
    expect(sniffPaste("# Plan\n\n- ship\n- measure")).toEqual({ ext: "md", mediaType: "text/markdown" });
    expect(sniffPaste("just a long note about the launch")).toEqual({ ext: "txt", mediaType: "text/plain" });
  });

  it("does not call a sentence with two commas a spreadsheet", () => {
    // Prose has commas; a table has the same number on every line.
    expect(sniffPaste("first, second\nthird\nfourth, fifth, sixth").ext).toBe("txt");
    expect(sniffPaste("{not json").ext).toBe("txt");
  });

  it("becomes a tile only past the size a box reads well at", () => {
    expect(isLargePaste("a short line")).toBe(false);
    expect(isLargePaste("x".repeat(3001))).toBe(true);
    expect(isLargePaste(Array(27).fill("row").join("\n"))).toBe(true);
    expect(pastedAttachment("a,b\n1,2\n3,4", 2)).toMatchObject({ name: "pasted-2.csv", kind: AttachmentKind.TEXT, mediaType: "text/csv" });
  });
});

describe("what a file is", () => {
  it("classifies by media type first and extension second", () => {
    expect(attachmentKind("image/png", "shot.png")).toBe(AttachmentKind.IMAGE);
    expect(attachmentKind("application/pdf", "deck.pdf")).toBe(AttachmentKind.PDF);
    expect(attachmentKind("", "notes.md")).toBe(AttachmentKind.TEXT); // browsers give .md no type
    expect(attachmentKind("application/zip", "bundle.zip")).toBe(AttachmentKind.FILE);
    expect(mediaTypeFor("notes.md", "")).toBe("text/markdown");
    expect(mediaTypeFor("x.bin", "application/octet-stream")).toBe("application/octet-stream");
  });

  it("puts a badge on every tile", () => {
    expect(attachmentLabel("application/pdf", "TIE.pdf")).toBe("PDF");
    expect(attachmentLabel("image/png", "")).toBe("PNG");
    expect(attachmentLabel("image/svg+xml", "")).toBe("SVG");
    expect(attachmentLabel("", "")).toBe("FILE");
  });
});

describe("the message on the wire and back", () => {
  const image = { name: "shot.png", mediaType: "image/png", kind: AttachmentKind.IMAGE, data: "AAAA" };
  const pdf = { name: "deck.pdf", mediaType: "application/pdf", kind: AttachmentKind.PDF, data: "BBBB" };
  const csv = { name: "pasted-1.csv", mediaType: "text/csv", kind: AttachmentKind.TEXT, text: "a,b\n1,2\n3,4" };

  it("is a plain string when nothing is attached — what every message was before", () => {
    expect(contentBlocks("  hello  ", [])).toBe("hello");
    expect(describeContent("hello")).toEqual({ text: "hello", attachments: [] });
  });

  it("round-trips: the tiles a reopened thread draws are the tiles the composer had", () => {
    const blocks = contentBlocks("look at these", [image, pdf, csv]);
    expect(blocks.map((b) => b.type)).toEqual(["text", "image", "file", "text"]);
    const back = describeContent(blocks);
    expect(back.text).toBe("look at these");
    expect(back.attachments).toEqual([
      { name: "image", mediaType: "image/png", kind: AttachmentKind.IMAGE, preview: "data:image/png;base64,AAAA" },
      { name: "deck.pdf", mediaType: "application/pdf", kind: AttachmentKind.PDF },
      { name: "pasted-1.csv", mediaType: "text/csv", kind: AttachmentKind.TEXT, size: 11, text: "a,b\n1,2\n3,4" },
    ]);
  });

  it("keeps the model's copy of a text attachment whole and the reader's copy out of the prose", () => {
    const [block] = contentBlocks("", [csv]);
    expect(block.text).toContain("a,b\n1,2\n3,4");
    // The route may glue context onto the text block; the wrapper still parses.
    const glued = [{ type: "text", text: `<working_report/>\n\nsee attached ${block.text}` }];
    const back = describeContent(glued);
    expect(back.text).toBe("<working_report/>\n\nsee attached");
    expect(back.attachments).toHaveLength(1);
  });

  it("does not choke on a stored row with a bare image block", () => {
    expect(describeContent([{ type: "image" }, { type: "text", text: "and this?" }])).toEqual({
      text: "and this?",
      attachments: [{ name: "image", mediaType: "image/png", kind: AttachmentKind.IMAGE, preview: "" }],
    });
    expect(describeContent(null)).toEqual({ text: "", attachments: [] });
  });
});
