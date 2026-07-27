// Renderer parity guard — asserts the JS preview renderer (src/lib/slideDoc.js)
// produces the SAME structure as the Python renderer (backend templates.py).
//
// Keep CASES in lockstep with backend/tests/test_content_render_contract.py.
// Run: `npm run check:parity`. If preview ≠ published render, the user edits one
// thing and ships another — this catches that drift.

import { renderSlideBody } from "../src/lib/slideDoc.js";

const CASES = [
  [{ slide_id: "s1", kind: "photo", caption_style: "hook", headline: "hi", subtext: "sub", image_prompt: "p" },
   ["slide-hook", "hook-headline", "hook-sub", "img-placeholder", "cap-bottom"]],
  [{ slide_id: "s2", kind: "photo", caption_style: "cap-pill", headline: "x", image_url: "/u/a.png", image_prompt: "q", image_prompt_used: "q" },
   ["slide-hook", "cap-pill", 'class="bg"']],
  [{ slide_id: "s3", kind: "text", headline: "stmt" },
   ["slide-body", "body-statement"]],
  [{ slide_id: "s4", kind: "collage", headline: "title", items: [{ label: "a", image_prompt: "x" }] },
   ["slide-collage", "collage-grid", "ctitle", "cell-label", "cell-ph"]],
  [{ slide_id: "s5", kind: "before-after", items: [{ marker: "dont", image_prompt: "d" }, { marker: "do", image_prompt: "o" }] },
   ["slide-ba", "ba-half", "ba-marker dont", "ba-marker do"]],
  [{ slide_id: "s6", kind: "editorial", headline: "Edit", subtext: "sub", image_prompt: "x" },
   ["slide-editorial", "ed-frame", 'class="et"', 'class="es"']],
];

let ok = true;
for (const [slide, must] of CASES) {
  const html = renderSlideBody(slide, 1);
  for (const token of must) {
    if (!html.includes(token)) {
      console.log(`FAIL ${slide.kind}: renderer missing ${JSON.stringify(token)}`);
      ok = false;
    }
  }
}
console.log(ok ? "slide-render parity OK" : "PARITY DRIFT — slideDoc.js diverged from templates.py");
process.exit(ok ? 0 : 1);
