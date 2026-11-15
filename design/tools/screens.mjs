// Every screen on the canvas, in canvas order. capture.mjs shoots each at
// every variant and keeps the 1440 light one as an editable board; layout.mjs
// rows them by `group`. Add a screen by adding an entry: `open` drives the app
// to the state worth drawing, against the story in
// app/src/lib/__fixtures__/solo-story.mjs.
//
// `workspace: true` is a full-bleed agent screen: it fills the window and
// scrolls inside, so it is shot at the window's height, never the page's.
// `board: false` keeps a screen on "As built" only; `variants` limits a screen
// to some sizes (the phone's navigation sheet exists only on the phone);
// `shot` picks the mock's <agent>@<shot>.json stream for this screen.
// `open` gets { page, app, story, plan, variant, fixtures }: ids the story
// does not name (a document, a post) come from fixtures.SHOWCASE.

// The four sizes every screen is judged at. Phone, the desktop app's window
// and a laptop are check:layout's three; the laptop again in dark is the
// theme people actually leave on.
export const VARIANTS = [
  { id: "1440", label: "Laptop · 1440 · light", width: 1440, height: 900, theme: "light", scale: 1, board: true },
  { id: "1440-dark", label: "Laptop · 1440 · dark", width: 1440, height: 900, theme: "dark", scale: 1 },
  { id: "1100", label: "Desktop app · 1100 · light", width: 1100, height: 760, theme: "light", scale: 1 },
  { id: "390", label: "Phone · 390 · light", width: 390, height: 844, theme: "light", scale: 2 },
];

const framed = (route) => async ({ page, app }) => {
  await page.goto(`${app}${typeof route === "function" ? route() : route}`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-slot="page-header"] h1', { timeout: 20000 }).catch(() => {});
};

const project = (story, path = "") => `/project/${story.project.id}${path}`;

// An overlay is opened on top of its page and shot with the page under it.
const dialog = (page) => page.getByRole("dialog").first().waitFor({ timeout: 20000 });

export const SCREENS = [
  // --- Front door ---------------------------------------------------------------
  {
    id: "front-door", group: "Front door", title: "Front door · sign in", route: "/", signedOut: true,
    open: async ({ page, app }) => {
      await page.goto(`${app}/`, { waitUntil: "domcontentloaded" });
      await page.getByRole("button", { name: /Google/i }).first().waitFor({ timeout: 20000 }).catch(() => {});
    },
  },
  {
    id: "start", group: "Front door", title: "Start · audit a site", route: "/start", signedOut: true,
    open: async ({ page, app }) => {
      await page.goto(`${app}/start`, { waitUntil: "domcontentloaded" });
      await page.locator("input").first().waitFor({ timeout: 20000 }).catch(() => {});
    },
  },
  {
    id: "start-found", group: "Front door", title: "Start · found your site", route: "/start", signedOut: true,
    open: async ({ page, app, story }) => {
      // Typed after hydration: the backend gate holds it, and a value filled
      // into the server's HTML is reset when React takes the field over.
      await page.goto(`${app}/start`, { waitUntil: "networkidle" });
      await page.locator("input").first().fill(story.company.site);
      await page.getByRole("button", { name: /Read my site/i }).click();
      await page.getByRole("heading", { name: "Found it." }).waitFor({ timeout: 30000 });
    },
  },
  {
    id: "invite", group: "Front door", title: "Invitation", route: "/invite/tok1", signedOut: true,
    open: async ({ page, app }) => {
      await page.goto(`${app}/invite/tok1`, { waitUntil: "domcontentloaded" });
      await page.getByRole("button").first().waitFor({ timeout: 20000 });
    },
  },
  {
    id: "authorize", group: "Front door", title: "Agent sign-in · consent", route: "/authorize",
    open: async ({ page, app }) => {
      await page.goto(`${app}/authorize?request=r1`, { waitUntil: "domcontentloaded" });
      await page.getByRole("button", { name: /Allow/i }).first().waitFor({ timeout: 20000 });
    },
  },
  {
    id: "desktop-auth", group: "Front door", title: "Desktop sign-in · hand-off", route: "/desktop-auth", signedOut: true,
    open: async ({ page, app }) => {
      await page.goto(`${app}/desktop-auth?auth_code=story`, { waitUntil: "domcontentloaded" });
      await page.locator("main, h1").first().waitFor({ timeout: 20000 });
    },
  },

  // --- Work -----------------------------------------------------------------------
  { id: "home", group: "Work", title: "Home · the desk", route: "/insights/organic-growth", open: framed("/insights/organic-growth") },
  {
    id: "palette", group: "Work", title: "Command palette", route: "/insights/organic-growth#palette",
    open: async (ctx) => {
      await framed("/insights/organic-growth")(ctx);
      await ctx.page.keyboard.press("ControlOrMeta+k");
      await dialog(ctx.page);
    },
  },
  {
    id: "nav-sheet", group: "Work", title: "Navigation · phone", route: "/insights/organic-growth#nav", board: false, variants: ["390"],
    open: async (ctx) => {
      await framed("/insights/organic-growth")(ctx);
      await ctx.page.locator('[data-sidebar="trigger"]').first().click();
      await dialog(ctx.page);
    },
  },
  {
    id: "insights-session", group: "Work", title: "Insights workspace · a brief", route: "/insights/session", workspace: true,
    open: async ({ page, app, story }) => {
      await page.goto(`${app}/insights/session?q=${encodeURIComponent("Why are signups down when ROAS is up?")}&project=${story.project.id}`);
      await page.getByText("Which matters more this week?", { exact: true }).waitFor({ timeout: 60000 });
      // The options are radio rows (workspace/QuestionsCard), not chips.
      await page.getByRole("radio", { name: /^Retention/ }).click();
      await page.getByRole("button", { name: /Continue/ }).click();
      await page.getByText("Pause Performance Max, keep brand search").first().waitFor({ timeout: 60000 });
      await page.locator('[role="status"]', { hasText: "Ready" }).first().waitFor({ timeout: 30000 }).catch(() => {});
      await page.frameLocator("iframe[title]").getByText("Signups are down.").waitFor({ timeout: 30000 }).catch(() => {});
      await page.getByText("The Legacy brand campaign stays untouched").first().scrollIntoViewIfNeeded().catch(() => {});
    },
  },
  { id: "seo-audit", group: "Work", title: "SEO Audit", route: "/audit/seo", open: framed("/audit/seo") },
  {
    id: "audit-workspace", group: "Work", title: "SEO Audit workspace · a report", route: "/audit/seo/session", workspace: true,
    open: async ({ page, app, story }) => {
      const id = "11111111-2222-4333-8444-555555555555";
      await page.evaluate(({ sid, url, projectId }) => {
        sessionStorage.setItem(`audit_session_${sid}`, JSON.stringify({ url, project_id: projectId, report_mode: "template" }));
      }, { sid: id, url: `https://${story.company.site}`, projectId: story.project.id });
      await page.goto(`${app}/audit/seo/${id}`);
      await page.getByText("Your report is on the right").waitFor({ timeout: 45000 });
      await page.waitForTimeout(1500);
    },
  },
  { id: "changes", group: "Work", title: "Changes", route: "/execute", open: framed("/execute") },
  { id: "scheduled", group: "Work", title: "Scheduled", route: "/scheduled", open: framed("/scheduled") },
  { id: "toolbox", group: "Work", title: "Toolbox", route: "/connections", open: framed("/connections") },

  // --- Content Studio ---------------------------------------------------------------
  { id: "content", group: "Content Studio", title: "Content Studio · Plans", route: "/content", open: framed("/content") },
  { id: "content-posts", group: "Content Studio", title: "Content Studio · Posts", route: "/content?tab=posts", board: false, open: framed("/content?tab=posts") },
  { id: "content-analytics", group: "Content Studio", title: "Content Studio · Analytics", route: "/content?tab=analytics", board: false, open: framed("/content?tab=analytics") },
  { id: "content-discover", group: "Content Studio", title: "Content Studio · Discover", route: "/content?tab=discover", board: false, open: framed("/content?tab=discover") },
  { id: "content-library", group: "Content Studio", title: "Content Studio · Library", route: "/content?tab=library", board: false, open: framed("/content?tab=library") },
  { id: "content-brand", group: "Content Studio", title: "Content Studio · Brand", route: "/content?tab=brand", board: false, open: framed("/content?tab=brand") },
  { id: "content-accounts", group: "Content Studio", title: "Content Studio · Accounts", route: "/content?tab=accounts", board: false, open: framed("/content?tab=accounts") },
  {
    id: "content-session", group: "Content Studio", title: "Content workspace · a post", route: "/content/posts/new", workspace: true,
    open: async ({ page, app, plan }) => {
      await page.goto(`${app}/content/posts/new?plan_id=${plan.id}&day=2`);
      await page.getByText("Slide 1 is in so you can see the look").waitFor({ timeout: 60000 });
      await page.frameLocator('iframe[title="slide 1 preview"]').locator("img.bg").waitFor({ timeout: 30000 }).catch(() => {});
      await page.waitForTimeout(1200);
    },
  },

  {
    id: "content-plan", group: "Content Studio", title: "Plan board · full width", route: "/content/plan", workspace: true,
    open: async ({ page, app, plan }) => {
      await page.goto(`${app}/content/plan`, { waitUntil: "domcontentloaded" });
      await page.getByText(plan.name, { exact: false }).first().waitFor({ timeout: 30000 }).catch(() => {});
    },
  },
  {
    id: "plan-session", group: "Content Studio", title: "Content workspace · a plan", route: "/content/sessions/new", workspace: true, shot: "plan",
    open: async ({ page, app, story, plan }) => {
      // Revise plan: the board's own week, so the session and the board agree.
      await page.goto(`${app}/content/sessions/new?plan=${plan.id}&project=${story.project.id}`);
      await page.locator('[role="status"]', { hasText: /Ready|Done/ }).first().waitFor({ timeout: 60000 }).catch(() => {});
      await page.waitForTimeout(1500);
    },
  },
  {
    id: "post-view", group: "Content Studio", title: "A posted post", route: "/content/posts/:id", workspace: true,
    link: ({ fixtures }) => `/content/posts/${fixtures.SHOWCASE.postedPostId}`,
    open: async ({ page, app, fixtures }) => {
      await page.goto(`${app}/content/posts/${fixtures.SHOWCASE.postedPostId}`, { waitUntil: "domcontentloaded" });
      await page.getByRole("button", { name: /Revise with Duct/i }).first().waitFor({ timeout: 30000 }).catch(() => {});
      await page.waitForTimeout(1200);
    },
  },
  {
    id: "feed-sheet", group: "Content Studio", title: "Plan from your work · sheet", route: "/content?tab=plans&from=work",
    open: async (ctx) => {
      await framed("/content?tab=plans&from=work")(ctx);
      await dialog(ctx.page);
      // Opened at its top, as a person sees it: focus can scroll the sheet,
      // and a scroll kept from 1440 is wrong at any other width.
      await ctx.page.evaluate(() => document.querySelectorAll('[role="dialog"], [role="dialog"] *').forEach((el) => { el.scrollTop = 0; }));
    },
  },

  // --- Library ------------------------------------------------------------------------
  { id: "documents", group: "Library", title: "Documents", route: "/artifacts", open: framed("/artifacts") },
  {
    id: "document", group: "Library", title: "A document", route: "/artifacts/:id",
    link: ({ fixtures }) => `/artifacts/${fixtures.SHOWCASE.artifactId}`,
    open: async (ctx) => {
      await framed(`/artifacts/${ctx.fixtures.SHOWCASE.artifactId}`)(ctx);
      await ctx.page.waitForTimeout(1500);
    },
  },
  { id: "activity", group: "Library", title: "Activity", route: "/activity", open: framed("/activity") },
  { id: "memory", group: "Library", title: "Memory · only you", route: "/memory", open: framed("/memory") },
  {
    id: "project-memory", group: "Library", title: "Memory · project", route: "/project/:id/memory", board: false,
    open: async (ctx) => framed(project(ctx.story, "/memory"))(ctx),
  },

  // --- Settings ---------------------------------------------------------------------------
  { id: "models", group: "Settings", title: "Models & providers", route: "/settings/models", open: framed("/settings/models") },
  { id: "profile", group: "Settings", title: "Profile", route: "/settings/profile", open: framed("/settings/profile") },
  { id: "agents", group: "Settings", title: "Connect your AI agent", route: "/settings/agents", open: framed("/settings/agents") },
  { id: "projects", group: "Settings", title: "Projects", route: "/projects", open: framed("/projects") },
  {
    id: "project", group: "Settings", title: "Project context", route: "/project/:id",
    open: async (ctx) => framed(project(ctx.story))(ctx),
  },
  {
    id: "members", group: "Settings", title: "Project members", route: "/project/:id/members", board: false,
    open: async (ctx) => framed(project(ctx.story, "/members"))(ctx),
  },
  { id: "usage", group: "Settings", title: "Usage", route: "/usage", open: framed("/usage") },
];

