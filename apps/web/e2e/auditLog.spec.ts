import { expect, test } from "@playwright/test";

// Roadmap step 247: a real browser drives the audit-log viewer against
// real AuditLog rows -- creating an org (as the org's own owner) writes
// a real organization.create row, creating a workspace afterward writes
// a real workspace.create row, both attributed to the same real actor
// (routers/organization.py and routers/workspace.py both pass
// actor_user_id now). Proves newest-first ordering, real actor email
// resolution (the router's own outerjoin against users), and the
// action filter narrowing results -- not just that the page renders
// against a mocked backend.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test("audit log: real organization/workspace creation shows up attributed to the real actor", async ({
  page,
}) => {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-audit-log-${suffix}@example.com`;
  const password = "correct horse battery staple";

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E Audit Log Test" }),
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByRole("link", { name: "Audit log" }).click();
  await expect(page).toHaveURL(/\/dashboard\/audit-log$/);
  await expect(page.getByText("You don't belong to an organization yet.")).toBeVisible();

  await page.getByRole("link", { name: "Create one in Settings" }).click();
  await page.getByLabel("Name").fill(`E2E Audit Log Org ${suffix}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page.getByRole("heading", { name: "Organization settings" })).toBeVisible();

  await page.getByRole("link", { name: "Workspaces" }).click();
  // Synchronizes on the real, freshly-mounted Workspaces page before
  // touching its form -- without this, a Name-labeled field can still
  // be interacted with while the previous page (Settings' own
  // BrandingForm has a "Name" field too) hasn't fully unmounted yet,
  // the same race workspaces.spec.ts's own working version already
  // guards against with this identical wait.
  await expect(page.getByText("No workspaces yet.")).toBeVisible();
  await page.getByLabel("Name").fill("Audit Log WS");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page.getByText("Audit Log WS", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Audit log" }).click();
  const rows = page.locator("table tbody tr");
  await expect(rows).toHaveCount(2);

  // Newest first: workspace.create was written after organization.create.
  await expect(rows.nth(0)).toContainText("workspace.create");
  await expect(rows.nth(0)).toContainText(email);
  await expect(rows.nth(1)).toContainText("organization.create");
  await expect(rows.nth(1)).toContainText(email);

  await page.getByPlaceholder("e.g. workspace.create").fill("organization.create");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(rows).toHaveCount(1);
  await expect(rows.nth(0)).toContainText("organization.create");
  await expect(page.getByText("1–1 of 1")).toBeVisible();
});
