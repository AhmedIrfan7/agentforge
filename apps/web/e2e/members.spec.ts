import { expect, test } from "@playwright/test";

// Roadmap step 239: the Members page always shows at least the
// caller's own org_owner row (organization creation always seeds it),
// with self-management controls disabled -- both real, honestly
// testable without a second real member. Adding a SECOND member is
// only possible today via the invitation-accept flow, which has no
// UI yet (step 240, still ahead) and can't be driven through a real
// browser here since this test can't retrieve the invitation email's
// token -- role-change/removal on another member are covered by the
// real backend integration tests (test_membership_endpoints.py)
// instead.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test("members page: owner's own row renders with role locked and self-actions disabled", async ({
  page,
}) => {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-members-${suffix}@example.com`;
  const password = "correct horse battery staple";

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E Members Test" }),
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByRole("link", { name: "Members" }).click();
  await expect(page.getByText("You don't belong to an organization yet.")).toBeVisible();

  await page.getByRole("link", { name: "Create one in Settings" }).click();
  await page.getByLabel("Name").fill(`E2E Members Org ${suffix}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page.getByRole("heading", { name: "Organization settings" })).toBeVisible();

  await page.getByRole("link", { name: "Members" }).click();
  await expect(page.getByText(email)).toBeVisible();
  await expect(page.getByText("(you)")).toBeVisible();

  const roleSelect = page.getByRole("combobox", { name: `Role for ${email}` });
  await expect(roleSelect).toHaveValue("org_owner");
  await expect(roleSelect).toBeDisabled();
  await expect(page.getByRole("button", { name: "Remove" })).toBeDisabled();
});
