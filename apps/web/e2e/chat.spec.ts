import { expect, test } from "@playwright/test";

// Roadmap step 198: a real browser sends a real message through the
// real chat UI shell (194) and receives a real streamed response --
// nothing here is mocked. Requires a real apps/api instance already
// running at NEXT_PUBLIC_API_URL (defaults to http://localhost:8000,
// matching apps/web/.env.example) with a real Postgres/Redis behind
// it, the same way every apps/api integration test in this project
// requires the real stack, just reached through a real browser this
// time instead of FastAPI's TestClient. Creates its own real
// organization/workspace/knowledge-base/public assistant via direct
// HTTP calls (the same signup->org->workspace->kb->assistant chain
// every apps/api endpoint test already builds) -- no seed fixture or
// mocked API layer, so this test proves the real, deployed system
// works end to end, not a stand-in for it. Deliberately does not
// upload a document: the orchestrator's own honest "No results
// found." reply for an empty knowledge base (orchestrator.py, step
// 143) is itself a real, deterministic response worth asserting on,
// and needs none of the ingestion pipeline's async
// extraction/chunking/embedding machinery to produce.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function createPublicAssistant(): Promise<string> {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-chat-${suffix}@example.com`;
  const password = "correct horse battery staple";

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E Chat Test" }),
  });

  const loginResponse = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!loginResponse.ok) {
    throw new Error(`Login failed with status ${loginResponse.status}`);
  }
  const { access_token: token } = (await loginResponse.json()) as { access_token: string };
  const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };

  const orgResponse = await fetch(`${API_BASE_URL}/organizations`, {
    method: "POST",
    headers,
    body: JSON.stringify({ name: "E2E Chat Org", slug: `e2e-chat-org-${suffix}` }),
  });
  const org = (await orgResponse.json()) as { id: string };

  const workspaceResponse = await fetch(`${API_BASE_URL}/organizations/${org.id}/workspaces`, {
    method: "POST",
    headers,
    body: JSON.stringify({ name: "E2E Chat Workspace", slug: `e2e-chat-ws-${suffix}` }),
  });
  const workspace = (await workspaceResponse.json()) as { id: string };

  const kbResponse = await fetch(
    `${API_BASE_URL}/organizations/${org.id}/workspaces/${workspace.id}/knowledge-bases`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({ name: "E2E Chat KB", slug: `e2e-chat-kb-${suffix}` }),
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
        name: "E2E Chat Bot",
        slug: `e2e-chat-bot-${suffix}`,
        is_public: true,
      }),
    },
  );
  const assistant = (await assistantResponse.json()) as { id: string };
  return assistant.id;
}

test("send message and receive a streamed response", async ({ page }) => {
  const assistantId = await createPublicAssistant();

  await page.goto(`/chat?assistantId=${assistantId}`);

  const input = page.getByPlaceholder("Send a message…");
  await input.click();
  await input.fill("What is your refund policy?");

  const [streamResponse] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes("/messages/stream") && response.request().method() === "POST",
    ),
    page.getByRole("button", { name: "Send" }).click(),
  ]);

  expect(streamResponse.status()).toBe(200);
  expect(streamResponse.headers()["content-type"]).toContain("text/event-stream");

  const streamBody = await streamResponse.text();
  const messageEventCount = (streamBody.match(/^event: message$/gm) ?? []).length;
  // Real, incremental delivery -- more than one SSE "message" event,
  // not the whole reply dressed up as a single write.
  expect(messageEventCount).toBeGreaterThan(1);
  expect(streamBody).toContain("event: done");

  // Scoped to the message list, not the whole page -- the sidebar
  // (196) shows this same text as the conversation's title, which
  // would otherwise make these locators ambiguous.
  const messageList = page.getByTestId("message-list");
  await expect(messageList.getByText("What is your refund policy?")).toBeVisible();
  await expect(messageList.getByText("No results found.")).toBeVisible();
});
