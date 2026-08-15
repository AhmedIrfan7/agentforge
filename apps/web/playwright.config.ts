import { defineConfig, devices } from "@playwright/test";

// Roadmap step 198 -- the first real automated test coverage for
// apps/web (CI's own web-tests.yml has only ever build-checked until
// now, see that workflow's own comment). Runs against a real `next
// dev` server (webServer below), talking to a real apps/api instance
// this test's own CI job/local setup is responsible for having already
// started (see e2e/chat.spec.ts's own docstring) -- nothing here mocks
// the backend.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  webServer: {
    command: "pnpm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
