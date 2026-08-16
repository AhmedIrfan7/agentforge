import { expect, test } from "@playwright/test";

// Roadmap step 234: a real browser drives the org-settings page end to
// end -- empty state (create an organization) through to branding and
// security-settings updates persisting for real. One cohesive test,
// not several small ones, to keep this file's own real cost (a real
// signup against apps/api's per-IP rate limit) to a single account.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function login(page: import("@playwright/test").Page): Promise<string> {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-settings-${suffix}@example.com`;
  const password = "correct horse battery staple";

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E Settings Test" }),
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  return email;
}

test("org-settings: create an organization, then update its branding and security settings", async ({
  page,
}) => {
  await login(page);

  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page).toHaveURL(/\/dashboard\/settings$/);
  await expect(page.getByRole("heading", { name: "Create your organization" })).toBeVisible();

  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  await page.getByLabel("Name").fill(`E2E Settings Org ${suffix}`);
  // Slug auto-derives from name -- leave it as-is.
  await page.getByRole("button", { name: "Create organization" }).click();

  await expect(page.getByRole("heading", { name: "Organization settings" })).toBeVisible();

  const nameField = page.getByRole("textbox").first();
  await expect(nameField).toHaveValue(`E2E Settings Org ${suffix}`);
  await nameField.fill(`E2E Settings Org ${suffix} (renamed)`);
  await page.getByRole("button", { name: "Save branding" }).click();
  await expect(page.getByText("Saved.").first()).toBeVisible();

  await page.getByLabel(/Allowed embed domains/).fill("example.com");
  await page.getByRole("button", { name: "Save security settings" }).click();
  await expect(page.getByText("Saved.").nth(1)).toBeVisible();

  // Persisted for real -- a fresh load reflects the actual server state,
  // not just optimistic client-side UI state.
  await page.reload();
  await expect(page.getByRole("textbox").first()).toHaveValue(
    `E2E Settings Org ${suffix} (renamed)`,
  );
  await expect(page.getByLabel(/Allowed embed domains/)).toHaveValue("example.com");
});
