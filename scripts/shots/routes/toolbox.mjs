// The Toolbox and Settings › Connect your AI agent, answered from the story.
//
// Home already says "5 sources connected" (the data-sources route in
// scripts/shots/fixtures.mjs), so the Toolbox has to hold the same five:
// a stored credential row per source, and a project binding per source,
// because the inventory only reports `bound` for a bound row
// (service/connector_access.py list_data_sources). On top of them, two MCP
// servers Maya added from presets: Linear, working, and Notion, whose
// sign-in expired two days before the brief, so one tile says "Needs
// attention" and the Connected tab carries its dot.
//
// Shapes are the backend's, field for field:
//   connectors     routes/user_connectors.py ConnectorOut / _to_out
//   bindings       routes/project_connectors.py _serialize
//   github app     routes/user_connectors.py github_app_status
//   mcp presets    service/mcp/presets.py PRESETS (as_dict)
//   mcp servers    service/mcp/store.py list_servers
//   mcp tokens     routes/mcp_tokens.py TokenOut / _out
// Timestamps follow each route: the dict routes hand back isoformat()
// ("+00:00"), the pydantic datetime fields serialize as "Z".

// Ids are UUIDs on the wire. Fixed ones, so a binding can point at its row and
// a re-run of the shots gets the same page.
const uuid = (n) => `5010c0de-0000-4000-8000-${String(n).padStart(12, "0")}`;
const at = (iso) => `${iso}+00:00`;

// service/connector_scopes.py SCOPE_CATALOG, for the scopes these rows hold.
const SCOPES = {
  adwords: {
    scope: "https://www.googleapis.com/auth/adwords",
    label: "Google Ads",
    why: "Reads campaign, ad group, search term and geo performance. Also the permission behind proposed changes — pausing a campaign, adding a negative keyword — which never apply without your approval.",
    access: "write",
    required: true,
  },
  gsc: {
    scope: "https://www.googleapis.com/auth/webmasters.readonly",
    label: "Search Console",
    why: "Reads queries, pages, clicks, impressions and average position. Read-only: Duct cannot change anything in Search Console.",
    access: "read",
    required: true,
  },
  ga4: {
    scope: "https://www.googleapis.com/auth/analytics.readonly",
    label: "Analytics",
    why: "Reads sessions, landing pages, conversions and channel data, so organic numbers can be checked against what visitors actually did.",
    access: "read",
    required: true,
  },
  ga4Edit: {
    scope: "https://www.googleapis.com/auth/analytics.edit",
    label: "Analytics key events",
    why: "Only used to mark a GA4 event as a key event when you approve that change. Decline it and every report still works — Duct will just hand you the change to make yourself.",
    access: "write",
    required: false,
  },
};

// Everything granted: scope_status "complete" is what turns an OAuth card
// green (connections/page.jsx toneFor/statusOf read `scope_status`).
function oauthRow({ id, type, name, scopes, noun = ["account", "accounts"], settings = {}, created }) {
  return {
    id,
    connector_type: type,
    // store_oauth_grant writes the Google row account-agnostic; the project's
    // binding names the property or customer it reads.
    account_id: "",
    account_name: name,
    last_validated_at: at(created),
    created_at: at(created),
    updated_at: at(created),
    granted_scopes: scopes.map((s) => s.scope),
    missing_scopes: [],
    scope_status: "complete",
    scopes: scopes.map((s) => ({ ...s, granted: true })),
    storage: "cloud",
    residency: "server",
    entity_noun: noun[0],
    entity_noun_plural: noun[1],
    settings,
  };
}

// A pasted key: no scopes exist, so "n/a" (SCOPE_NA), and the card counts it
// connected from the row alone (ManualConnectorCard: serverRowList.length).
function keyRow({ id, type, accountId, name, created }) {
  return {
    id,
    connector_type: type,
    account_id: accountId,
    account_name: name,
    last_validated_at: at(created),
    created_at: at(created),
    updated_at: at(created),
    granted_scopes: [],
    missing_scopes: [],
    scope_status: "n/a",
    scopes: [],
    storage: "cloud",
    residency: "server",
    entity_noun: "account",
    entity_noun_plural: "accounts",
    settings: {},
  };
}

const MCP_PRESETS = [
  { id: "openseo", label: "OpenSEO", url: "https://app.openseo.so/mcp", home: "https://openseo.so", publisher: "OpenSEO", key_url: "https://app.openseo.so/settings", trust_read_only: true },
  { id: "notion", label: "Notion", url: "https://mcp.notion.com/mcp", home: "https://www.notion.so", publisher: "Notion", key_url: "", trust_read_only: true },
  { id: "linear", label: "Linear", url: "https://mcp.linear.app/mcp", home: "https://linear.app", publisher: "Linear", key_url: "", trust_read_only: true },
  { id: "posthog", label: "PostHog", url: "https://mcp.posthog.com/mcp", home: "https://posthog.com", publisher: "PostHog", key_url: "https://app.posthog.com/settings/user-api-keys", trust_read_only: true },
  { id: "railway", label: "Railway", url: "https://mcp.railway.com", home: "https://railway.com", publisher: "Railway", key_url: "", trust_read_only: false },
  { id: "cloudflare", label: "Cloudflare", url: "https://mcp.cloudflare.com/mcp", home: "https://www.cloudflare.com", publisher: "Cloudflare", key_url: "", trust_read_only: false },
];

export function routes(story) {
  const { STORY } = story;
  const projectId = STORY.project.id;

  // The five Home counts, named as the data-sources route names them, since
  // that route reads account_name off these same rows.
  const native = {
    google_ads: oauthRow({ id: uuid(101), type: "google_ads", name: STORY.ads.accountName, scopes: [SCOPES.adwords], created: "2026-08-18T09:12:00" }),
    ga4: oauthRow({ id: uuid(102), type: "ga4", name: "Solo web + app", scopes: [SCOPES.ga4, SCOPES.ga4Edit], noun: ["property", "properties"], created: "2026-08-18T09:15:00" }),
    gsc: oauthRow({ id: uuid(103), type: "gsc", name: STORY.company.site, scopes: [SCOPES.gsc], noun: ["property", "properties"], created: "2026-08-18T09:17:00" }),
    stripe: keyRow({ id: uuid(104), type: "stripe", accountId: "acct_1Pq7SoloEU2026", name: "Solo", created: "2026-08-19T14:02:00" }),
    clarity: keyRow({ id: uuid(105), type: "clarity", accountId: "q4xm7slo2b", name: "Solo Android", created: "2026-09-04T11:30:00" }),
  };

  // What the project reads inside each account. The ids match the story's
  // change sets (STORY.ads.accountId, "ga4-solo"), so the Executions page and
  // a source's dialog name the same account.
  const entity = {
    google_ads: [STORY.ads.accountId, STORY.ads.accountName],
    ga4: ["ga4-solo", "Solo web + app"],
    gsc: [`sc-domain:${STORY.company.site}`, STORY.company.site],
    stripe: ["acct_1Pq7SoloEU2026", "Solo"],
    clarity: ["q4xm7slo2b", "Solo Android"],
  };
  const bindings = Object.entries(native)
    .sort(([a], [b]) => a.localeCompare(b)) // order_by(connector_type)
    .map(([type, row], i) => ({
      id: uuid(201 + i),
      connector_type: type,
      connector_credential_id: row.id,
      account_id: row.account_id,
      account_name: row.account_name,
      entity_id: entity[type][0],
      entity_name: entity[type][1],
      created_at: row.created_at,
      updated_at: row.updated_at,
    }));

  // Oldest first, as list_servers sorts them. Notion's grant was refused on
  // the 12th: needs_reauth with the reason the client recorded, which the
  // tile reads as "Needs attention · Sign-in expired" (PROBLEM_SHORT).
  const servers = [
    {
      id: uuid(301),
      key: "notion",
      url: "https://mcp.notion.com/mcp",
      name: "Notion",
      preset: "notion",
      auth: "oauth",
      status: "needs_reauth",
      problem: "signed_out",
      problem_at: at("2026-09-12T16:05:00"),
      last_validated_at: at("2026-08-27T10:40:00"),
      created_at: at("2026-08-27T10:40:00"),
    },
    {
      id: uuid(302),
      key: "linear",
      url: "https://mcp.linear.app/mcp",
      name: "Linear",
      preset: "linear",
      auth: "oauth",
      status: "connected",
      problem: "",
      problem_at: null,
      last_validated_at: at("2026-09-03T08:55:00"),
      created_at: at("2026-09-03T08:55:00"),
    },
  ];

  // A server lives in connector_credentials as type "mcp" (store.save_server:
  // url in account_id, name in account_name), and list_connectors leaves only
  // provider keys out, so the real listing carries these rows too. The
  // Toolbox's native cards ignore the type; the order is the route's,
  // connector_type then account_name.
  const mcpRows = servers.map((s) => ({
    ...keyRow({ id: s.id, type: "mcp", accountId: s.url, name: s.name, created: s.created_at.slice(0, 19) }),
    last_validated_at: s.last_validated_at,
  }));
  const connectors = [...Object.values(native), ...mcpRows].sort(
    (a, b) => a.connector_type.localeCompare(b.connector_type) || a.account_name.localeCompare(b.account_name),
  );

  return {
    "GET /api/user/connectors": connectors,
    // The hosted app has the GitHub App, so the GitHub card offers one click.
    "GET /api/user/connectors/github/app": {
      available: true,
      manage_url: "https://github.com/apps/getduct/installations/select_target",
    },
    [`GET /api/user/projects/${projectId}/connectors`]: bindings,
    "GET /api/user/mcp/presets": { presets: MCP_PRESETS },
    "GET /api/user/mcp/servers": { servers },
    // Claude Code signed in through the browser: its client_name carries our
    // own server name, which agentDisplayName strips. expires_at is the
    // refresh window, 90 days from its last refresh. One pasted token beside
    // it, so both lists on the page have a row.
    "GET /api/user/mcp-tokens": [
      {
        id: uuid(401),
        kind: "agent",
        name: "Claude Code (duct)",
        hint: "",
        created_at: "2026-09-01T14:22:00Z",
        expires_at: "2026-12-13T08:10:00Z",
        last_used_at: "2026-09-14T06:41:00Z",
      },
      {
        id: uuid(402),
        kind: "token",
        name: "GitHub Actions weekly report",
        hint: "R4qe",
        created_at: "2026-08-25T16:03:00Z",
        expires_at: "2027-08-25T16:03:00Z",
        last_used_at: "2026-09-14T06:00:00Z",
      },
    ],
  };
}
