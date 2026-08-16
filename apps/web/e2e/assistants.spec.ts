import { expect, test } from "@playwright/test";

// Roadmap step 238: a real browser drives assistant creation through
// to the builder page and back, covering instructions, agent config
// (LLM provider, enabled agents, retrieval top K), and is_public --
// unlike documents (236/237), nothing here needs real storage or
// antivirus, so this is a fully real, fully automated flow.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test("assistant builder: create, edit instructions and agent config, persists for real", async ({
  page,
}) => {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-assistants-${suffix}@example.com`;
  const password = "correct horse battery staple";

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E Assistants Test" }),
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByRole("link", { name: "Workspaces" }).click();
  await page.getByRole("link", { name: "Create one in Settings" }).click();
  await page.getByLabel("Name").fill(`E2E Assistants Org ${suffix}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page.getByRole("heading", { name: "Organization settings" })).toBeVisible();

  await page.getByRole("link", { name: "Workspaces" }).click();
  await expect(page.getByRole("heading", { name: "New workspace" })).toBeVisible();
  await page.getByLabel("Name").fill("Research");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page.getByText("Research", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Knowledge bases" }).click();
  await expect(page.getByText("No knowledge bases yet.")).toBeVisible();
  await page.getByLabel("Name").fill("Product Docs");
  await page.getByRole("button", { name: "Create knowledge base" }).click();
  await expect(page.getByText("Product Docs", { exact: true })).toBeVisible();

  // Assistants live one level under the Documents page (that page's own
  // "Manage assistants" link), not directly off the knowledge-base list.
  await page.getByRole("link", { name: "Documents" }).click();
  await expect(page.getByRole("heading", { name: "Documents" })).toBeVisible();
  await page.getByRole("link", { name: "Manage assistants" }).click();
  await expect(page.getByText("No assistants yet.")).toBeVisible();
  await page.getByLabel("Name").fill("Support Bot");
  await page.getByRole("button", { name: "Create assistant" }).click();
  await expect(page.getByText("Support Bot", { exact: true })).toBeVisible();

  await page.getByText("Support Bot", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "Support Bot" })).toBeVisible();

  await page
    .getByPlaceholder("e.g. Always cite your sources. Keep answers concise.")
    .fill("Always cite your sources.");
  await page.getByLabel("Public (reachable anonymously through the embeddable widget)").check();
  await page.getByLabel("LLM provider").selectOption("anthropic");
  await page.getByLabel("citation").check();
  await page.getByLabel("Retrieval top K").fill("25");
  await page.getByRole("button", { name: "Save assistant" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  // Persisted for real, not just optimistic client-side state.
  await page.reload();
  await expect(
    page.getByPlaceholder("e.g. Always cite your sources. Keep answers concise."),
  ).toHaveValue("Always cite your sources.");
  await expect(
    page.getByLabel("Public (reachable anonymously through the embeddable widget)"),
  ).toBeChecked();
  await expect(page.getByLabel("LLM provider")).toHaveValue("anthropic");
  await expect(page.getByLabel("citation")).toBeChecked();
  await expect(page.getByLabel("Retrieval top K")).toHaveValue("25");
});
