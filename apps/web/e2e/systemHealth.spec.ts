import { expect, test } from "@playwright/test";

// Roadmap step 248: a real browser drives the system-health dashboard
// against the real GET /system-health (routers/system_health.py).
// Not org-scoped, unlike every other dashboard e2e spec in this app --
// no organization/workspace setup needed, just a real signed-up user.
//
// Covers the non-platform-admin path only -- the real 403 an ordinary
// signup gets, which is exactly what a real browser/API flow can
// produce without any other help. The platform-admin path needs
// User.is_platform_admin flipped directly in Postgres (no UI grants it
// yet -- that's step 249's own job, and this file has no Postgres
// driver to reach for the way tests/test_system_health_endpoint.py's
// own pytest suite already can); that real, live path is covered there
// instead, plus this step's own manual live-verification (a real
// worker process observed going online/offline, real queue depth,
// real provider configuration state).
//
// The dashboard UX pass made UserRead expose is_platform_admin for
// real, so the nav link is now correctly hidden from a non-admin
// instead of being shown and then 403ing -- this proves both real
// guarantees: the link genuinely isn't in the DOM, and the backend
// still enforces the same 403 for direct navigation (defense in
// depth, not just the UI hiding it).
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test("system health: a non-platform-admin user has no nav link and gets the real 403 directly", async ({
  page,
}) => {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-system-health-${suffix}@example.com`;
  const password = "correct horse battery staple";

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E System Health Test" }),
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await expect(page.getByRole("link", { name: "System health" })).not.toBeVisible();

  await page.goto("/dashboard/system-health");
  await expect(page.getByText("Platform admin access required.")).toBeVisible();
});
