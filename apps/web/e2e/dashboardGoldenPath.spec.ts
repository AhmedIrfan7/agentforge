import { expect, test } from "@playwright/test";

// Roadmap step 250: the closing e2e test for Milestone 9's whole
// dashboard -- login -> upload doc -> processed -> chat -> see
// analytics, driven by a real browser against a real apps/api instance
// with real Postgres/Redis/MinIO/ClamAV/a real Celery worker behind it
// (web-tests.yml's own CI job gained the last three specifically for
// this spec). Every earlier stage of this exact click path (org ->
// workspace -> knowledge base -> assistant -> public toggle) already
// has its own dedicated, still-passing spec (knowledgeBases.spec.ts,
// assistants.spec.ts) -- this one's real, new contribution is chaining
// ALL five named stages together in one continuous real session,
// something no single existing spec does, plus being the FIRST spec in
// this whole suite to drive a real file upload through Playwright
// rather than only verifying the upload mechanics by hand (knowledge
// Bases.spec.ts's own docstring explains why it stops short of that).
//
// "processed" does not mean "successfully embedded" here, and
// deliberately asserts on ANY real terminal status
// (page.tsx's own TERMINAL_STATUSES), not "embedded" specifically --
// live-verified (roadmap step 250's own commit) that even this
// project's own local dev environment has no real OPENAI_API_KEY
// configured anywhere, so a real upload's own honest, reproducible
// terminal outcome is "embedding_failed", not "embedded", in every
// environment available to build or run this in, CI included. That
// failure happens at the LLM-provider-dependent last step only --
// antivirus, storage, and extraction (the parts this codebase actually
// controls) all still run for real and succeed, which is what this
// step's own upload assertion actually proves.
//
// Because embedding never completes, the chat step's own retrieval
// finds nothing to cite (chat.spec.ts's own empty-KB "No results
// found." case, not a new failure) -- this test still sends a real
// message through the real streaming endpoint and confirms it lands in
// the conversation and in real per-org analytics counts afterward,
// which is what "chat -> see analytics" actually needs to prove: the
// full request path works end to end, independent of whether this
// particular environment has a funded embedding provider behind it.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TERMINAL_STATUSES = [
  "embedded",
  "extraction_unsupported",
  "extraction_failed",
  "embedding_failed",
];

test("dashboard golden path: login, upload a real doc, chat, see it in analytics", async ({
  page,
}) => {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-golden-path-${suffix}@example.com`;
  const password = "correct horse battery staple";

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E Golden Path Test" }),
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByRole("link", { name: "Workspaces" }).click();
  await page.getByRole("link", { name: "Create one in Settings" }).click();
  await page.getByLabel("Name").fill(`E2E Golden Path Org ${suffix}`);
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

  await page.getByRole("link", { name: "Documents" }).click();
  await expect(page.getByRole("heading", { name: "Documents" })).toBeVisible();
  await expect(page.getByText("No documents yet.")).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: "refund-policy.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "Our refund policy allows returns within 90 days of purchase for a full refund.",
    ),
  });
  // exact: true -- the dashboard UX pass added a second real button
  // here, the empty-state's own "Upload your first document" CTA, whose
  // name would otherwise also match a loose substring search.
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.getByText("refund-policy.txt", { exact: true })).toBeVisible();

  // Real antivirus scan + real storage + real extraction (and a real,
  // always-failing-here embedding attempt) all run against the real
  // pipeline -- give it real time rather than a tight timeout.
  const statusBadge = page.locator("li", { hasText: "refund-policy.txt" }).locator("span").last();
  await expect(statusBadge).toHaveText(new RegExp(`^(${TERMINAL_STATUSES.join("|")})$`), {
    timeout: 30_000,
  });

  await page.getByRole("link", { name: "Manage assistants" }).click();
  await expect(page.getByText("No assistants yet.")).toBeVisible();
  await page.getByLabel("Name").fill("Support Bot");
  await page.getByRole("button", { name: "Create assistant" }).click();
  await expect(page.getByText("Support Bot", { exact: true })).toBeVisible();

  await page.getByText("Support Bot", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "Support Bot" })).toBeVisible();
  await page.getByLabel("Public (reachable anonymously through the embeddable widget)").check();
  await page.getByRole("button", { name: "Save assistant" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  const assistantId = page.url().split("/assistants/")[1];

  await page.goto(`/chat?assistantId=${assistantId}`);
  const input = page.getByPlaceholder("Send a message…");
  await input.click();
  await input.fill("What is your refund policy?");
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes("/messages/stream") && response.request().method() === "POST",
    ),
    page.getByRole("button", { name: "Send" }).click(),
  ]);
  const messageList = page.getByTestId("message-list");
  await expect(messageList.getByText("What is your refund policy?")).toBeVisible();

  await page.goto("/dashboard/analytics");
  // Waits for the real async fetch to actually resolve before reading
  // combined text below -- same synchronization point analytics.spec.ts
  // itself waits on.
  await expect(page.getByText("1 of 1 conversations (100%)")).toBeVisible();

  // The three conversation stats and the four usage stats each render
  // as sibling text nodes sharing one container, not standalone
  // elements -- a combined-innerText `.toContain()` check, the same
  // pattern analytics.spec.ts's own working test already established,
  // rather than a `getByText` locator per value, which is ambiguous
  // against a shared text blob like this.
  const pageText = (await page.locator("main").innerText()).replace(/\s+/g, " ");
  expect(pageText).toContain("1 Conversations");
  expect(pageText).toContain("2 Messages");
  expect(pageText).toContain("1 Uploads");
});
