import { expect, test } from "@playwright/test";

// Roadmap step 235: a real browser drives workspace management end to
// end -- create, see it listed, delete, confirm it's really gone (not
// just removed from local state) via a fresh page load. One signup for
// the whole flow, matching settings.spec.ts's own reasoning for keeping
// this file's real cost (apps/api's per-IP signup rate limit) to a
// single account.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test("workspaces: create, list, and delete within a real organization", async ({ page }) => {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-workspaces-${suffix}@example.com`;
  const password = "correct horse battery staple";

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E Workspaces Test" }),
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  // No org yet -- Workspaces must point at Settings, not offer a dead
  // end or its own duplicate create-organization form.
  await page.getByRole("link", { name: "Workspaces" }).click();
  await expect(page).toHaveURL(/\/dashboard\/workspaces$/);
  await expect(page.getByText("You don't belong to an organization yet.")).toBeVisible();
  await page.getByRole("link", { name: "Create one in Settings" }).click();
  await expect(page).toHaveURL(/\/dashboard\/settings$/);

  await page.getByLabel("Name").fill(`E2E Workspaces Org ${suffix}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page.getByRole("heading", { name: "Organization settings" })).toBeVisible();

  await page.getByRole("link", { name: "Workspaces" }).click();
  await expect(page.getByText("No workspaces yet.")).toBeVisible();

  await page.getByLabel("Name").fill("Engineering");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page.getByText("Engineering", { exact: true })).toBeVisible();
  await expect(page.getByText("engineering", { exact: true })).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("No workspaces yet.")).toBeVisible();

  // Really gone server-side, not just removed from local component
  // state -- a fresh load reflects the real persisted (lack of) data.
  await page.reload();
  await expect(page.getByText("No workspaces yet.")).toBeVisible();
});
