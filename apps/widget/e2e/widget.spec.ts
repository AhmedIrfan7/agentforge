import { expect, test } from "@playwright/test";

// Roadmap step 214: a real browser loads the real built widget.js on a
// real fixture host page (e2e/fixtures/host-page.html) and sends a
// real message through it -- this app's own equivalent of
// apps/web/e2e/chat.spec.ts (198), same "no mocks, real apps/api"
// requirement. Creates its own real organization/workspace/
// knowledge-base/public assistant via direct HTTP, the identical chain
// chat.spec.ts's own createPublicAssistant already builds --
// duplicated here rather than shared, since @agentforge/shared (207)
// is a browser-runtime package and this is Node-side test setup code, a
// genuinely different concern.
const API_BASE_URL = process.env.AGENTFORGE_API_URL ?? "http://localhost:8000";

async function createPublicAssistant(): Promise<string> {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e-widget-${suffix}@example.com`;
  const password = "correct horse battery staple";

  await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E Widget Test" }),
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
    body: JSON.stringify({ name: "E2E Widget Org", slug: `e2e-widget-org-${suffix}` }),
  });
  const org = (await orgResponse.json()) as { id: string };

  const workspaceResponse = await fetch(`${API_BASE_URL}/organizations/${org.id}/workspaces`, {
    method: "POST",
    headers,
    body: JSON.stringify({ name: "E2E Widget Workspace", slug: `e2e-widget-ws-${suffix}` }),
  });
  const workspace = (await workspaceResponse.json()) as { id: string };

  const kbResponse = await fetch(
    `${API_BASE_URL}/organizations/${org.id}/workspaces/${workspace.id}/knowledge-bases`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({ name: "E2E Widget KB", slug: `e2e-widget-kb-${suffix}` }),
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
        name: "E2E Widget Bot",
        slug: `e2e-widget-bot-${suffix}`,
        is_public: true,
      }),
    },
  );
  const assistant = (await assistantResponse.json()) as { id: string };
  return assistant.id;
}

test("widget loads on a host page and sends a message", async ({ page }) => {
  const assistantId = await createPublicAssistant();

  await page.goto(
    `/host-page.html?assistantId=${assistantId}&apiUrl=${encodeURIComponent(API_BASE_URL)}`,
  );

  // Playwright locators pierce open shadow roots automatically -- no
  // special handling needed to reach into launcher.ts's own shadow DOM.
  const launcherButton = page.getByRole("button", { name: "Open chat" });
  await expect(launcherButton).toBeVisible();
  await launcherButton.click();

  const textarea = page.getByPlaceholder("Send a message…");
  await textarea.click();
  await textarea.fill("What is your refund policy?");
  await page.getByRole("button", { name: "Send" }).click();

  // Same empty-KB honest response chat.spec.ts (198) already asserts on.
  await expect(page.getByText("No results found.")).toBeVisible();
  // A fresh locator, not `launcherButton` -- its accessible name changed
  // from "Open chat" to "Close chat" on click, so the ORIGINAL
  // name-filtered locator no longer matches anything post-toggle.
  await expect(page.getByRole("button", { name: "Close chat" })).toBeVisible();
});
