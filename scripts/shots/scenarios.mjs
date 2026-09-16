// One entry per image. `page` scenarios drive the real app against the mock
// backend; `scene` scenarios open a /preview frame, which needs no backend
// for its data (covers still come from the mock's media folder).
// Every scenario returns what to capture: a locator, `{ element, radius }`
// for a floating surface, or nothing for the whole viewport. Add an image by
// adding an entry; the runner does the rest.
import { PLAN, STORY } from "../../app/src/lib/__fixtures__/solo-story.mjs";

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
