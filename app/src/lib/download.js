"use client";

// Handing the browser a file to save. The anchor dance was written out four
// times — the artifact download, the derived export, the audit report, and now
// the brief in the thread pane — and two of the four forgot to put the anchor
// in the document, which some browsers require and which is the kind of bug
// that only shows up on someone else's machine.

/** Save a blob under `filename`, then release the object URL. */
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Save text the app already holds, without a round trip for bytes it has. */
export function saveText(text, filename, type = "text/plain") {
  saveBlob(new Blob([text], { type }), filename);
}
