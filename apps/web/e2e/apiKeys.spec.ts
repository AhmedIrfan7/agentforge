import { expect, test } from "@playwright/test";

// Roadmap step 241: unlike members/invitations, this feature has no
// second-party acceptance step, so create/reveal/list/revoke is fully
// real and browser-testable end to end with no honest gaps.

test("api keys: create reveals the raw key once, then list shows it active, then revoke", async ({
  page,
}) => {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-apikeys-${suffix}@example.com`;
  const password = "correct horse battery staple";
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E API Keys Test" }),
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByRole("link", { name: "API keys" }).click();
  await expect(page.getByText("You don't belong to an organization yet.")).toBeVisible();

  await page.getByRole("link", { name: "Create one in Settings" }).click();
  await page.getByLabel("Name").fill(`E2E API Keys Org ${suffix}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page.getByRole("heading", { name: "Organization settings" })).toBeVisible();

  await page.getByRole("link", { name: "API keys" }).click();
  await expect(page.getByText("No API keys yet.")).toBeVisible();

  await page.getByPlaceholder("e.g. Production integration").fill("E2E key");
  await page.getByRole("button", { name: "Create key" }).click();

  await expect(page.getByText('"E2E key" created')).toBeVisible();
  const revealedKey = await page.locator("code").textContent();
  expect(revealedKey).toMatch(/^afk_live_/);

  await page.getByRole("button", { name: "I've copied it" }).click();
  // The raw key never appears again once dismissed.
  await expect(page.locator("code")).not.toBeVisible();

  const prefix = revealedKey!.slice(0, 12);
  await expect(page.getByText(`${prefix}… · Active`)).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByText(`${prefix}… · Revoked`)).toBeVisible();
  await expect(page.getByRole("button", { name: "Revoke" })).not.toBeVisible();
});
