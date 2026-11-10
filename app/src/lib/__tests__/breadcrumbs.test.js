import { readdirSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";
import { HIDDEN_SEGMENTS, SEGMENT_HREFS, buildTrail } from "../breadcrumbs.js";

const i18n = { _: (descriptor) => descriptor?.message ?? String(descriptor) };
const APP = join(__dirname, "..", "..", "app", "(app)");

/** Every static route folder under the app shell that has no page of its own. */
function foldersWithoutPage(dir = APP) {
  const out = [];
  const entries = readdirSync(dir, { withFileTypes: true });
  const hasPage = entries.some((e) => e.isFile() && /^page\.(jsx?|tsx?)$/.test(e.name));
  if (dir !== APP && !hasPage) out.push("/" + relative(APP, dir).split(sep).join("/"));
  for (const e of entries) {
    if (e.isDirectory() && !e.name.startsWith("[") && !e.name.startsWith(".") && !e.name.startsWith("(")) {
      out.push(...foldersWithoutPage(join(dir, e.name)));
    }
  }
  return out;
}

describe("buildTrail", () => {
  it("never links a crumb to a folder that has no page", () => {
    const dead = foldersWithoutPage().filter(
      (path) => !SEGMENT_HREFS[path] && !HIDDEN_SEGMENTS.has(path.split("/").pop())
    );
    expect(dead).toEqual([]);
  });

  it("sends Posts above a post to the Posts tab", () => {
    const id = "a9997d11-0197-4a71-ad09-b1f8cb4afbaa";
    const trail = buildTrail(`/content/posts/${id}`, i18n);
    expect(trail.map((c) => [c.label, c.href])).toEqual([
      ["Content Studio", "/content"],
      ["Posts", "/content?tab=posts"],
      [`#${id.slice(0, 6)}`, `/content/posts/${id}`],
    ]);
  });

  it("puts a plan session under Plans, named for the plan it revises", () => {
    const fresh = buildTrail("/content/sessions/new", i18n);
    expect(fresh.map((c) => c.label)).toEqual(["Content Studio", "Plans", "New"]);
    expect(fresh[1].href).toBe("/content?tab=plans");
    const revising = buildTrail("/content/sessions/new", i18n, "November 2026 plan");
    expect(revising[2]).toMatchObject({ label: "November 2026 plan", isLast: true });
  });
});
