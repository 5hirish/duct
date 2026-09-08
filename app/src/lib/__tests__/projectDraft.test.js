// The three rules that make a drafted project safe to merge, pinned:
// a value the user set is never overwritten, what the site says (crawl) beats
// what a model guessed (inferred), and a filled field with no recorded
// provenance belongs to the user. Everything else is plumbing.

import { describe, expect, it } from "vitest";
import { mergeDraft, markConfirmed, PROVENANCE_CRAWL, PROVENANCE_INFERRED, PROVENANCE_USER } from "../projectDraft";
import { UNTITLED_PROJECT } from "../projects";

const empty = { id: "p1", name: "", company: { name: "", pitch: "" }, audience: { personas: [] }, provenance: {} };

const crawl = {
  layer: "crawl",
  fields: {
    name: { value: "Acme", provenance: PROVENANCE_CRAWL },
    company_name: { value: "Acme", provenance: PROVENANCE_CRAWL },
    pitch: { value: "Weeknight dinners, planned.", provenance: PROVENANCE_CRAWL },
    favicon: { value: "", provenance: PROVENANCE_CRAWL },
  },
};

describe("mergeDraft", () => {
  it("lands each field on its path and records where it came from", () => {
    const out = mergeDraft(empty, crawl);
    expect(out.name).toBe("Acme");
    expect(out.company.name).toBe("Acme");
    expect(out.company.pitch).toBe("Weeknight dinners, planned.");
    expect(out.provenance.pitch).toBe(PROVENANCE_CRAWL);
    expect("favicon" in out.provenance).toBe(false); // empty values are not written
  });

  it("never overwrites what the user set", () => {
    const typed = markConfirmed({ ...empty, company: { name: "What I typed", pitch: "" } }, "company_name");
    const out = mergeDraft(typed, crawl);
    expect(out.company.name).toBe("What I typed");
    expect(out.provenance.company_name).toBe(PROVENANCE_USER);
    expect(out.company.pitch).toBe("Weeknight dinners, planned.");
  });

  it("lets the crawl beat a later inference, but fills gaps from it", () => {
    const first = mergeDraft(empty, crawl);
    const inferred = {
      layer: "inferred",
      fields: {
        pitch: { value: "A model's guess", provenance: PROVENANCE_INFERRED },
        industry: { value: "SaaS & Software", provenance: PROVENANCE_INFERRED },
      },
    };
    const out = mergeDraft(first, inferred);
    expect(out.company.pitch).toBe("Weeknight dinners, planned.");
    expect(out.company.industry).toBe("SaaS & Software");
    expect(out.provenance.industry).toBe(PROVENANCE_INFERRED);
  });

  // The regression this rule exists for. Every project made before drafts
  // existed has an empty provenance map, so without rule 3 the first crawl to
  // reach one replaced its name, pitch and industry with facts about whatever
  // site was being audited — and `/start` used to hand the draft to whichever
  // project happened to be active.
  it("leaves a pre-draft project's fields alone", () => {
    const legacy = {
      id: "p2",
      name: "Acme (mine)",
      company: { name: "Acme Corporation", pitch: "What I wrote myself" },
      audience: { personas: [] },
      // No provenance key at all — the shape every older project is in.
    };
    const out = mergeDraft(legacy, crawl);
    expect(out.name).toBe("Acme (mine)");
    expect(out.company.name).toBe("Acme Corporation");
    expect(out.company.pitch).toBe("What I wrote myself");
  });

  it("still fills the gaps in a pre-draft project", () => {
    const legacy = { id: "p3", name: "Mine", company: { name: "", pitch: "" }, audience: { personas: [] } };
    const out = mergeDraft(legacy, crawl);
    expect(out.name).toBe("Mine");
    expect(out.company.pitch).toBe("Weeknight dinners, planned.");
  });

  // The placeholder is not content: a project the store just made carries it,
  // and treating it as typed would leave every new project called "Untitled".
  it("writes over the placeholder name", () => {
    const fresh = { id: "p4", name: UNTITLED_PROJECT, company: { name: "", pitch: "" }, audience: { personas: [] } };
    expect(mergeDraft(fresh, crawl).name).toBe("Acme");
  });

  it("ignores fields it has no home for", () => {
    const out = mergeDraft(empty, { fields: { secret_sauce: { value: "x", provenance: PROVENANCE_CRAWL } } });
    expect(out.secret_sauce).toBeUndefined();
  });
});
