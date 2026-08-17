import { expect, test } from "@playwright/test";

// Roadmap step 243: real conversations/messages generated through the
// actual public anonymous-chat flow (fetch-based setup, same as
// chat.spec.ts's own createPublicAssistant), then read back through
// the real dashboard analytics page -- proves the whole path end to
// end, not just that the page renders without a real backend behind it.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test("analytics: real conversations show up as real conversation/message counts", async ({
  page,
}) => {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-analytics-${suffix}@example.com`;
  const password = "correct horse battery staple";

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E Analytics Test" }),
  });
  const loginResponse = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const { access_token: token } = (await loginResponse.json()) as { access_token: string };
  const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };

  const orgResponse = await fetch(`${API_BASE_URL}/organizations`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      name: `E2E Analytics Org ${suffix}`,
      slug: `e2e-analytics-org-${suffix}`,
    }),
  });
  const org = (await orgResponse.json()) as { id: string };

  const workspaceResponse = await fetch(`${API_BASE_URL}/organizations/${org.id}/workspaces`, {
    method: "POST",
    headers,
    body: JSON.stringify({ name: "E2E Analytics WS", slug: `e2e-analytics-ws-${suffix}` }),
  });
  const workspace = (await workspaceResponse.json()) as { id: string };

  const kbResponse = await fetch(
    `${API_BASE_URL}/organizations/${org.id}/workspaces/${workspace.id}/knowledge-bases`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({ name: "E2E Analytics KB", slug: `e2e-analytics-kb-${suffix}` }),
    },
  );
  const knowledgeBase = (await kbResponse.json()) as { id: string };

  const assistantResponse = await fetch(
    `${API_BASE_URL}/organizations/${org.id}/workspaces/${workspace.id}` +
      `/knowledge-bases/${knowledgeBase.id}/assistants`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({
        name: "E2E Analytics Bot",
        slug: `e2e-analytics-bot-${suffix}`,
        is_public: true,
      }),
    },
  );
  const assistant = (await assistantResponse.json()) as { id: string };

  // Two real anonymous conversations, one real message each -- each
  // real send produces a user message + a real (honest "No results
  // found." for an empty KB) assistant reply, so 2 sends -> 4 messages.
  for (const content of ["What is your refund policy?", "Hello there"]) {
    const convResponse = await fetch(
      `${API_BASE_URL}/public/assistants/${assistant.id}/conversations`,
      { method: "POST" },
    );
    const conv = (await convResponse.json()) as { conversation_id: string; access_token: string };
    await fetch(
      `${API_BASE_URL}/public/assistants/${assistant.id}/conversations/${conv.conversation_id}/messages`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${conv.access_token}`,
        },
        body: JSON.stringify({ content }),
      },
    );
  }

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByRole("link", { name: "Analytics" }).click();
  await expect(page.getByText("2 of 2 conversations (100%)")).toBeVisible();

  const pageText = (await page.locator("main").innerText()).replace(/\s+/g, " ");
  expect(pageText).toContain("2 Conversations");
  expect(pageText).toContain("4 Messages");
  expect(pageText).toContain("2.0 Avg messages / conversation");
});
