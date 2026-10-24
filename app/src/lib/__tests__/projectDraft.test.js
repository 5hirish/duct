// The three rules that make a drafted project safe to merge, pinned:
// a value the user set is never overwritten, a filled field gives way only to
// an equal or higher rank (site, then the user's documents, then a model's
// guess), and a filled field with no recorded provenance belongs to the user.
// Everything else is plumbing.

import { describe, expect, it } from "vitest";
import {
  mergeDraft,
  markConfirmed,
  PROVENANCE_CRAWL,
  PROVENANCE_DOCUMENT,
  PROVENANCE_INFERRED,
  PROVENANCE_USER,
} from "../projectDraft";
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

  // The user's own files rank between the site and a model's guess: they fill
  // what the site left empty, beat the classifier, and never rename what the
  // site already names, because a deck goes stale and a homepage does not.
  it("ranks the user's documents below the site and above a guess", () => {
    const fromSite = mergeDraft(empty, crawl);
    const documents = {
      layer: "documents",
      fields: {
        name: { value: "Acme Old Name", provenance: PROVENANCE_DOCUMENT },
        industry: { value: "Marketing & Advertising", provenance: PROVENANCE_DOCUMENT },
      },
    };
    const withDocs = mergeDraft(fromSite, documents);
    expect(withDocs.name).toBe("Acme");
    expect(withDocs.provenance.name).toBe(PROVENANCE_CRAWL);
    expect(withDocs.company.industry).toBe("Marketing & Advertising");
    expect(withDocs.provenance.industry).toBe(PROVENANCE_DOCUMENT);

    const guess = { fields: { industry: { value: "SaaS & Software", provenance: PROVENANCE_INFERRED } } };
    expect(mergeDraft(withDocs, guess).company.industry).toBe("Marketing & Advertising");
    // A later read of the same files may correct an earlier one.
    const reread = { fields: { industry: { value: "Education", provenance: PROVENANCE_DOCUMENT } } };
    expect(mergeDraft(withDocs, reread).company.industry).toBe("Education");
  });

  it("gives a provenance it does not know the least trust", () => {
    const fromSite = mergeDraft(empty, crawl);
    const unknown = { fields: { pitch: { value: "From somewhere new", provenance: "telepathy" } } };
    expect(mergeDraft(fromSite, unknown).company.pitch).toBe("Weeknight dinners, planned.");
  });

  it("ignores fields it has no home for", () => {
    const out = mergeDraft(empty, { fields: { secret_sauce: { value: "x", provenance: PROVENANCE_CRAWL } } });
    expect(out.secret_sauce).toBeUndefined();
  });

  it("fills over the settings page's empty persona row", () => {
    // The page seeds one row to type into and saves it with the project; with
    // no recorded provenance, rule 3 used to read it as the user's persona.
    const seeded = { ...empty, audience: { personas: [{ name: "", description: "", priority: "primary" }] } };
    const personas = [{ name: "Working parent", description: "", priority: "primary" }];
    const out = mergeDraft(seeded, { fields: { personas: { value: personas, provenance: PROVENANCE_INFERRED } } });
    expect(out.audience.personas).toEqual(personas);
  });
});
