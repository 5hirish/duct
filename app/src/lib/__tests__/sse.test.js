import { describe, expect, it } from "vitest";
import { consumeSseStream, parseSseDataFrame } from "../sse";

function streamOf(chunks) {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
}

describe("parseSseDataFrame", () => {
  it("strips one optional space after the colon and joins data lines", () => {
    expect(parseSseDataFrame('data: {"a":\ndata:1}')).toEqual({ a: 1 });
  });
  it("ignores comments and non-data lines", () => {
    expect(parseSseDataFrame(": ping")).toBeNull();
    expect(parseSseDataFrame("event: x\ndata: {}")).toEqual({});
  });
  it("returns null for a frame that is not JSON", () => {
    expect(parseSseDataFrame("data: nope")).toBeNull();
  });
});

describe("consumeSseStream", () => {
  it("delivers frames split across chunks, in order, skipping pings", async () => {
    const got = [];
    await consumeSseStream(
      streamOf(['data: {"event":"a"}\n\n: ping\n\ndata: {"ev', 'ent":"b"}\n\n']),
      (e) => got.push(e.event),
    );
    expect(got).toEqual(["a", "b"]);
  });

  it("treats an abort as a normal exit", async () => {
    const ctrl = new AbortController();
    ctrl.abort();
    await expect(consumeSseStream(streamOf(['data: {"event":"a"}\n\n']), () => {}, ctrl.signal)).resolves.toBeUndefined();
  });
});
