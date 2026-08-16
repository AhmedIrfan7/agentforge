import { defineConfig, devices } from "@playwright/test";

// Roadmap step 214 -- widget-tests.yml has only ever build+bundle-size
// checked until now (see that workflow's own comment). Runs against a
// real built dist/widget.js served by scripts/serve-fixture.mjs (a
// minimal static server, no new dependency -- 201's own "minimal deps"
// constraint), talking to a real apps/api instance this test's own
// CI job/local setup is responsible for having already started (same
// convention apps/web/playwright.config.ts/198 already established).
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:4173",
    trace: "on-first-retry",
  },
  webServer: {
    command: "pnpm run build && node scripts/serve-fixture.mjs",
    url: "http://localhost:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
