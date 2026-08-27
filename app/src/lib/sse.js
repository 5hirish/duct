// Server-sent-events reader shared by every streaming endpoint (audit,
// content, insights). Three copies of this had grown up independently and
// disagreed on the small things — whether `data:` needed the trailing space,
// whether blank frames were skipped, whether an abort was an error.
//
// Frames are separated by a blank line; a frame's payload is the concatenation
// of its `data:` lines, with one optional space after the colon stripped
// (the SSE spec's rule, which is why a JSON body survives it intact).

/** Parse one SSE frame into its JSON payload, or null if it carries none. */
export function parseSseDataFrame(frame) {
  const dataLines = frame
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => (line.startsWith("data: ") ? line.slice(6) : line.slice(5)));
  if (!dataLines.length) return null;
  try {
    return JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }
}

/**
 * Read `body` (a ReadableStream) to completion, invoking `onEvent` per JSON
 * frame. Returns when the server closes the stream or `signal` aborts —
 * an abort is a normal exit, not a throw; anything else propagates.
 */
export async function consumeSseStream(body, onEvent, signal) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      if (signal?.aborted) break;
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        if (!frame.trim()) continue;
        const event = parseSseDataFrame(frame);
        if (event) onEvent(event);
      }
    }
  } catch (err) {
    if (!signal?.aborted) throw err;
  } finally {
    reader.releaseLock();
  }
}
