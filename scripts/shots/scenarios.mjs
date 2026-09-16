// One entry per image. `page` scenarios drive the real app against the mock
// backend; `scene` scenarios open a /preview frame, which needs no backend
// for its data (covers still come from the mock's media folder).
// Every scenario returns what to capture: a locator, `{ element, radius }`
// for a floating surface, or nothing for the whole viewport. Add an image by
// adding an entry; the runner does the rest.
import { ANSWERS, PLAN, STORY } from "../../app/src/lib/__fixtures__/solo-story.mjs";

export const SCENARIOS = [
  {
    id: "insights-session",
    kind: "page",
    viewport: { width: 1440, height: 900 },
    theme: "light",
    frame: "window",
    async run({ page, app }) {
      await page.goto(`${app}/insights/session?q=${encodeURIComponent("Why are signups down when ROAS is up?")}&project=${STORY.project.id}`);
      await page.getByText("Which matters more this week?", { exact: true }).waitFor({ timeout: 60000 });
      await page.getByRole("button", { name: /^Retention/ }).click();
      await page.getByRole("button", { name: /Continue/ }).click();
      await page.getByText("Pause Performance Max, keep brand search").waitFor({ timeout: 60000 });
      await page.locator('[role="status"]', { hasText: "Ready" }).first().waitFor({ timeout: 30000 });
      // The brief is an HTML report in a frame; wait for its heading to paint.
      await page.frameLocator("iframe[title]").getByText("Signups are down.").waitFor({ timeout: 30000 });
      // Scroll the transcript so the answer, the change set and the composer are all in frame.
      await page.getByText("The Legacy brand campaign stays untouched").scrollIntoViewIfNeeded();
      await page.waitForTimeout(600);
      return null;
    },
  },
  // The same workspace with the artifact pane hidden: these two sessions
  // write no brief, and at a third of its size on a page the pane only made
  // the chat unreadable. The override is capture-only; the app has no such
  // mode, and should not grow one for a screenshot.
  ...[
    { id: "product-session", q: ANSWERS.product.question, answer: /^Connect bank/, proposed: "Track the permission dead end", last: "ask for the permission after the first budget" },
    { id: "paid-session", q: ANSWERS.paid.question, answer: /^The €12 CPA/, proposed: "Pause Performance Max, keep brand search", last: "The Legacy brand campaign stays untouched" },
  ].map((s) => ({
    id: s.id,
    kind: "page",
    viewport: { width: 1180, height: 900 },
    theme: "light",
    frame: "window",
    async run({ page, app }) {
      await page.goto(`${app}/insights/session?q=${encodeURIComponent(s.q)}&project=${STORY.project.id}`);
      await page.addStyleTag({ content: "#insights_split_w-left { width: 100% !important; border-right: 0 !important; } #insights_split_w-left ~ div { display: none !important; }" });
      await page.getByRole("button", { name: s.answer }).waitFor({ timeout: 60000 });
      await page.getByRole("button", { name: s.answer }).click();
      await page.getByRole("button", { name: /Continue/ }).click();
      await page.getByText(s.proposed).waitFor({ timeout: 60000 });
      await page.locator('[role="status"]', { hasText: "Ready" }).first().waitFor({ timeout: 30000 });
      await page.getByText(s.last).scrollIntoViewIfNeeded();
      await page.waitForTimeout(600);
      return null;
    },
  })),
  {
    id: "executions",
    kind: "page",
    viewport: { width: 1440, height: 900 },
    theme: "light",
    frame: "window",
    async run({ page, app }) {
      await page.goto(`${app}/execute`);
      await page.getByText("Pause Performance Max, keep brand search").first().waitFor({ timeout: 60000 });
      // The queue as it is: this week's proposal waiting on Approve all, the
      // three that already went through under it. The drawer stays closed;
      // its overlay blurs the whole window.
      await page.waitForTimeout(500);
      return null;
    },
  },
  {
    id: "content-session",
    kind: "page",
    viewport: { width: 1440, height: 900 },
    theme: "light",
    frame: "window",
    async run({ page, app }) {
      await page.goto(`${app}/content/posts/new?plan_id=${PLAN.id}&day=2`);
      await page.getByText("Slide 1 is in so you can see the look").waitFor({ timeout: 60000 });
      // The slide renders in a sandboxed frame; give its image and fonts a moment.
      await page.frameLocator('iframe[title="slide 1 preview"]').locator("img.bg").waitFor({ timeout: 30000 });
      await page.waitForTimeout(1200);
      return null;
    },
  },
  {
    id: "content-plan",
    kind: "scene",
    scene: "shot-plan-board",
    viewport: { width: 1040, height: 680 },
    theme: "light",
    frame: "window",
    async run({ page }) {
      await page.locator("img[src*='/uploads/story/']").nth(2).waitFor({ timeout: 30000 });
      await page.waitForTimeout(400);
      return page.locator("[data-preview-content]");
    },
  },
  {
    id: "connectors",
    kind: "scene",
    scene: "shot-connectors",
    viewport: { width: 1040, height: 700 },
    theme: "light",
    frame: "window",
    async run({ page }) {
      await page.locator("img[alt='Microsoft Clarity']").waitFor({ timeout: 15000 });
      await page.waitForTimeout(400);
      return page.locator("[data-preview-content]");
    },
  },
  // The answer alone: one question, the sources it read, what it found. The
  // job cards on the landing pages want this, not a whole window at a third
  // of its size.
  ...["product", "paid", "organic"].map((key) => ({
    id: `answer-${key}`,
    kind: "scene",
    scene: `shot-answer-${key}`,
    viewport: { width: 820, height: 900 },
    theme: "light",
    frame: "card",
    async run({ page }) {
      await page.getByText(ANSWERS[key].question).waitFor({ timeout: 15000 });
      await page.waitForTimeout(300);
      return page.locator("[data-shot]");
    },
  })),
  {
    id: "review-card",
    kind: "scene",
    scene: "shot-change-set",
    viewport: { width: 640, height: 640 },
    theme: "light",
    frame: "card",
    async run({ page }) {
      return page.locator("[data-shot] > *").first();
    },
  },
  {
    id: "chatgpt-card",
    kind: "scene",
    scene: "shot-chatgpt-card",
    viewport: { width: 900, height: 760 },
    theme: "light",
    frame: "card",
    // The desktop shell, as far as the page can tell: capability flags and a
    // signed-in ChatGPT plan. Installed before any script on the page runs.
    shell: {
      get_shell_info: { version: "0.6.0", capabilities: { browserAuth: true, browserConnectors: true, localSidecar: false, autoUpdate: true, notifications: true, chatgptAuth: true } },
      chatgpt_status: { connected: true, plan_type: "plus", email: STORY.user.email, account_id: "acct_solo" },
      get_provider_key: null,
    },
    async run({ page }) {
      await page.getByRole("button", { name: /OpenAI/ }).first().click();
      const dialog = page.getByRole("dialog");
      await dialog.getByText("Signed in as").waitFor({ timeout: 15000 });
      await page.waitForTimeout(300);
      // The dialog alone, with its own corner radius; the dimmed page behind
      // it would only read as a grey band once it is framed.
      await page.addStyleTag({ content: "[data-slot=dialog-overlay], [data-radix-dialog-overlay] { opacity: 0 !important; }" });
      const radius = await dialog.evaluate((el) => parseFloat(getComputedStyle(el).borderRadius) || 0);
      return { element: dialog, radius };
    },
  },
  {
    id: "memory-timeline",
    kind: "scene",
    scene: "shot-memory-timeline",
    viewport: { width: 940, height: 900 },
    theme: "light",
    frame: "card",
    async run({ page }) {
      await page.getByText("CPA target is €12 across paid channels").waitFor({ timeout: 15000 });
      await page.waitForTimeout(300);
      return page.locator("[data-preview-content]");
    },
  },
];
