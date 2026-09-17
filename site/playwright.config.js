const { defineConfig, devices } = require("@playwright/test");
const path = require("path");

module.exports = defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // Two workers everywhere, not only on CI. Locally the default (half the
  // cores) opened four Chromium contexts at once, each playing the home
  // page's film, and desktop contexts then took longer than the 30 s test
  // timeout to tear down: three consent tests failing on a machine where
  // the same twelve pass in 23 s with two workers. The Makefile mirrors CI,
  // so the local run has to see what CI sees.
  workers: 2,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:4317",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: `node "${path.resolve(__dirname, "tests/e2e/static-server.js")}"`,
    port: 4317,
    reuseExistingServer: false,
    timeout: 30 * 1000,
  },
  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-chromium",
      use: { ...devices["Pixel 7"] },
    },
  ],
});
