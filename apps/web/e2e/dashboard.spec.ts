import { expect, test } from "@playwright/test";

// Roadmap step 233: a real browser drives the real auth-gated
// dashboard shell end to end -- no mocks. Creates its own real user
// via direct HTTP (the same signup helper shape chat.spec.ts already
// established) since this flow has nothing to do with any assistant/
// knowledge-base setup those other e2e suites need.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface TestUser {
  email: string;
  password: string;
  fullName: string;
}

async function createUser(): Promise<TestUser> {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-dashboard-${suffix}@example.com`;
  const password = "correct horse battery staple";
  const fullName = "E2E Dashboard Test";

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: fullName }),
  });

  return { email, password, fullName };
}

test("visiting /dashboard while logged out redirects to /login", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Sign in to AgentForge" })).toBeVisible();
});

test("logging in reaches the dashboard, logging out returns to /login", async ({ page }) => {
  const user = await createUser();

  await page.goto("/login");
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByRole("heading", { name: `Welcome back, ${user.fullName}.` }),
  ).toBeVisible();
  await expect(page.getByText(user.email)).toBeVisible();

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  // The gate re-applies for real, not just for the tab that logged out.
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
});

test("a wrong password shows an inline error and stays on /login", async ({ page }) => {
  const user = await createUser();

  await page.goto("/login");
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill("the wrong password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByText("Incorrect email or password.")).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});
