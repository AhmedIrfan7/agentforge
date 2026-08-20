import { expect, test } from "@playwright/test";

// Roadmap step 236: a real browser drives knowledge-base creation
// through to the documents page, covering everything the new nested
// dynamic routes (/dashboard/workspaces/[workspaceId]/knowledge-bases,
// .../[knowledgeBaseId]) render and fetch for real. Deliberately does
// NOT drive a real file upload through this suite -- web-tests.yml's
// own CI job has no MinIO/ClamAV services (see that file's comment on
// chat.spec.ts, which has the identical limitation for the same
// reason: nothing in this workflow's path has ever needed real
// storage/antivirus before now). The upload/status/polling mechanics
// themselves were live-verified by hand against a real running
// server, worker, MinIO, and ClamAV instead -- see the roadmap step
// 236 entry for what that covered.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test("knowledge bases: create within a workspace, reach the documents page", async ({ page }) => {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-kb-${suffix}@example.com`;
  const password = "correct horse battery staple";

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E KB Test" }),
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByRole("link", { name: "Workspaces" }).click();
  await page.getByRole("link", { name: "Create one in Settings" }).click();
  await page.getByLabel("Name").fill(`E2E KB Org ${suffix}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page.getByRole("heading", { name: "Organization settings" })).toBeVisible();

  await page.getByRole("link", { name: "Workspaces" }).click();
  // Settings' own "Name" branding field is still on screen the instant
  // this click fires (client-side navigation is async) -- getByLabel
  // would otherwise resolve against that stale field immediately rather
  // than waiting for the real navigation, since a "Name" label already
  // satisfies the locator before Workspaces even renders. Waiting for
  // something unique to the destination page first avoids that.
  await expect(page.getByRole("heading", { name: "New workspace" })).toBeVisible();
  await page.getByLabel("Name").fill("Research");
  await page.getByRole("button", { name: "Create workspace" }).click();
  // Wait for the real created row to actually render before clicking its
  // own link -- Playwright's click() resolves once the click event
  // dispatches, not once handleCreate's own async POST settles.
  await expect(page.getByText("Research", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Knowledge bases" }).click();
  await expect(page).toHaveURL(/\/knowledge-bases$/);
  await expect(page.getByText("No knowledge bases yet.")).toBeVisible();

  await page.getByLabel("Name").fill("Product Docs");
  await page.getByRole("button", { name: "Create knowledge base" }).click();
  await expect(page.getByText("Product Docs", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Documents" }).click();
  await expect(page).toHaveURL(/\/knowledge-bases\/[^/]+$/);
  await expect(page.getByRole("heading", { name: "Documents" })).toBeVisible();
  await expect(page.getByText("No documents yet.")).toBeVisible();
  await expect(page.locator('input[type="file"]')).toBeVisible();
  // exact: true -- the dashboard UX pass added a second real button
  // here, the empty-state's own "Upload your first document" CTA, whose
  // name would otherwise also match a loose substring search.
  await expect(page.getByRole("button", { name: "Upload", exact: true })).toBeVisible();
});
