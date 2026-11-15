// /start after the URL: the root page read back (agents/audit/prefetch.py
// Prefetch.status, with draft from agents/audit/draft.py crawl_draft).
export function routes(story) {
  const { STORY } = story;
  const url = `https://${STORY.company.site}/`;
  const field = (value) => ({ value, provenance: "crawl" });
  const status = {
    crawl_id: "crawl-solo",
    state: "done",
    pages: 14,
    error: "",
    site: {
      url,
      title: `${STORY.company.name} · ${STORY.company.tagline}`,
      description: "Track income, set aside tax and see what you can spend, built for people who invoice.",
      favicon: "",
      http_status: 200,
      is_spa_suspected: false,
      blocked: false,
    },
    draft: {
      layer: "crawl",
      fields: {
        name: field(STORY.company.name),
        company_name: field(STORY.company.name),
        pitch: field(STORY.company.tagline),
        website_url: field(url),
        content_pillars: field(["Tax set-aside", "Irregular income", "Invoicing"]),
        active_channels: field(["tiktok", "instagram", "linkedin"]),
      },
    },
  };
  // Submitting the URL mints a guest first (lib/guest.js): an unsigned token
  // is enough, nothing on the mock checks it.
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
  const guest = `${b64({ alg: "none" })}.${b64({ sub: "guest-solo", uid: "guest-solo", guest: true, exp: 4102444800 })}.sig`;
  return {
    "POST /auth/guest": { token: guest, created: true },
    "POST /api/audit/prefetch": status,
    "GET /api/audit/prefetch/crawl-solo": status,
  };
}
