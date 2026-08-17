import { expect, test } from "@playwright/test";

// Roadmap step 240: create/list/revoke are fully real and browser-
// testable end to end, unlike the accept half of this feature -- that
// needs the real token from the invitation email, which this test has
// no way to retrieve (notifications.email only logs it server-side,
// same honest limitation members.spec.ts already documented for its
// own second-member case). The accept flow itself is covered by
// test_invitation_endpoints.py's real integration tests plus manual
// live verification against the real running stack.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test("invitations: invite someone, see it pending with the right role, then revoke it", async ({
  page,
}) => {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-invitations-${suffix}@example.com`;
  const password = "correct horse battery staple";
  const inviteeEmail = `e2e-invitee-${suffix}@example.com`;

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E Invitations Test" }),
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByRole("link", { name: "Invitations" }).click();
  await expect(page.getByText("You don't belong to an organization yet.")).toBeVisible();

  await page.getByRole("link", { name: "Create one in Settings" }).click();
  await page.getByLabel("Name").fill(`E2E Invitations Org ${suffix}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page.getByRole("heading", { name: "Organization settings" })).toBeVisible();

  await page.getByRole("link", { name: "Invitations" }).click();
  await expect(page.getByText("No invitations yet.")).toBeVisible();

  await page.getByLabel("Email").fill(inviteeEmail);
  await page.getByLabel("Role").selectOption("manager");
  await page.getByRole("button", { name: "Send invitation" }).click();

  await expect(page.getByText(inviteeEmail)).toBeVisible();
  await expect(page.getByText("manager · Pending")).toBeVisible();

  await page.getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByText("manager · Revoked")).toBeVisible();
  // A revoked invitation can't be revoked again -- the button is gone.
  await expect(page.getByRole("button", { name: "Revoke" })).not.toBeVisible();
});
