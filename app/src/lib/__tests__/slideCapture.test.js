import { describe, expect, it } from "vitest";
import { FALLBACK_GROUND, forShadowRoot, groundColor, unsafeUrl } from "../slideCapture.js";

// The capture is what the agent looks at and what publishes. Both of these
// shipped broken on 2026-11-27 with every check green: the safe zone lost in
// the shadow root, and a fixed black painted over the slide's own ground.
describe("slide capture", () => {
  it("keeps the engine's variables inside the shadow root", () => {
    const css = ":root { --safe-left: 72px; } .slide { left: var(--safe-left); }";
    expect(forShadowRoot(css)).toBe(":host { --safe-left: 72px; } .slide { left: var(--safe-left); }");
  });

  it("paints the slide's own ground, and black only where it has none", () => {
    expect(groundColor("rgb(244, 239, 231)")).toBe("rgb(244, 239, 231)");
    expect(groundColor("rgba(0, 0, 0, 0)")).toBe(FALLBACK_GROUND);
    expect(groundColor("")).toBe(FALLBACK_GROUND);
  });

  it("drops a link that would run or open a document, and keeps a picture", () => {
    for (const bad of ["javascript:alert(1)", " JaVa\tScRiPt:x", "vbscript:msgbox", "data:text/html,<b>", "data:application/xhtml+xml,<x/>"]) {
      expect(unsafeUrl(bad)).toBe(true);
    }
    for (const ok of ["https://cdn.example/a.png", "#grain", "url(#g)", "data:image/png;base64,AAAA", "data:image/svg+xml;utf8,<svg/>", "50%"]) {
      expect(unsafeUrl(ok)).toBe(false);
    }
  });
});
