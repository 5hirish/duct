// What `GET /api/user/mcp/registry` answers, in the shapes it takes: the
// shape of backend/service/mcp/registry.py's `Listing`, best first. Modelled
// on the registry's real answers for "stripe" and "figma" on 2026-11-03; the
// vendors' own servers are real addresses, the rest invented. The /preview
// scenes draw them and the unit tests hold `arrangeRegistry` to them.

function listing(fields) {
  return {
    name: "",
    title: "",
    description: "",
    url: "",
    host: new URL(fields.url).hostname,
    website: "",
    auth: "",
    key_hint: "",
    runs_host: false,
    official: false,
    ...fields,
  };
}

export const STRIPE_LISTINGS = [
  listing({
    name: "com.stripe/mcp",
    title: "Stripe",
    description: "Payments, customers, subscriptions and refunds in your Stripe account.",
    url: "https://mcp.stripe.com",
    website: "https://docs.stripe.com/mcp",
    runs_host: true,
    official: true,
  }),
  listing({
    name: "app.vercel.stripecheckup/stripecheckup",
    title: "Stripecheckup",
    description: "Audit a Stripe account's checkout setup and flag misconfigured prices.",
    url: "https://stripecheckup.vercel.app/api/mcp",
    runs_host: true,
  }),
  listing({
    name: "com.ledgerline/stripe-reports",
    title: "Stripe Reports",
    description: "Monthly revenue, churn and refunds from Stripe, as tables.",
    url: "https://mcp.ledgerline.io/mcp",
    website: "https://ledgerline.io/keys",
    auth: "key",
    key_hint: "Your Ledgerline API key, from Settings → API.",
    runs_host: true,
  }),
  listing({
    name: "com.insightfulpipe/stripe",
    title: "Stripe MCP by InsightfulPipe",
    description: "Stripe data through InsightfulPipe's gateway.",
    url: "https://stripe.insightfulmcp.com/",
  }),
  listing({
    name: "io.github.mcp-dir/stripe-mcp",
    title: "Stripe",
    description: "Stripe tools through a shared gateway.",
    url: "https://api.mcp.ai/p_stripe",
  }),
];

export const FIGMA_LISTINGS = [
  listing({
    name: "com.figma.mcp/mcp",
    title: "Figma",
    description: "Read frames, components and variables from your Figma files.",
    url: "https://mcp.figma.com/mcp",
    runs_host: true,
    official: true,
  }),
  listing({
    name: "io.github.sadri-dridi/figma-url-shape",
    title: "Figma URL Shape",
    description: "Check that a Figma link points at a file, a frame or a prototype.",
    url: "https://agent-observatory-sensor.nolimit-observatory.workers.dev/s/figma-url-shape/mcp",
  }),
];

/** Only servers nobody can vouch for: the section leads with the button. */
export const GATEWAY_ONLY_LISTINGS = STRIPE_LISTINGS.filter((l) => !l.runs_host);
