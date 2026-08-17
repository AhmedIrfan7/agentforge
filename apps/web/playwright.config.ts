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
  // Every spec here talks to ONE real, shared Postgres/Redis instance
  // (no mocked backend, see this file's own docstring) -- with no
  // `workers` pin, Playwright's own CPU-count-based default let CI run
  // multiple specs concurrently, and a real cross-spec race surfaced
  // live (analytics.spec.ts's own conversation count flipped from "2 of
  // 2" while another spec was creating conversations concurrently under
  // the same real org/DB). Serial in CI, still fast/parallel locally
  // (`undefined` keeps Playwright's own default there) -- the identical
  // "sequential, not concurrent" reasoning this project's own pytest
  // suite already applies against the same kind of shared real state.
  workers: process.env.CI ? 1 : undefined,
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
