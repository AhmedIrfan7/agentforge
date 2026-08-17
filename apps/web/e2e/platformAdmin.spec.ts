import { expect, test } from "@playwright/test";

// Roadmap step 249: a real browser drives the platform-admin dashboard
// against the real GET /platform-admin/organizations (routers/
// platform_admin.py). Not org-scoped, same as systemHealth.spec.ts --
// just a real signed-up user, no organization/workspace setup needed
// for this test's own real path.
//
// Covers the non-platform-admin path only, the same honest carve-out
// systemHealth.spec.ts already established -- the platform-admin path
// needs User.is_platform_admin flipped directly in Postgres (no UI
// grants it yet, and this file has no Postgres driver to reach for the
// way tests/test_platform_admin_endpoints.py's own pytest suite
// already can); that real, live path is covered there instead, plus
// this step's own manual live-verification against 100+ real
// organizations already in the local dev database.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test("platform admin: a non-platform-admin user sees the real 403", async ({ page }) => {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-platform-admin-${suffix}@example.com`;
  const password = "correct horse battery staple";

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E Platform Admin Test" }),
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByRole("link", { name: "Platform admin" }).click();
  await expect(page).toHaveURL(/\/dashboard\/platform-admin$/);
  await expect(page.getByText("Platform admin access required.")).toBeVisible();
});
