// Real API client for the assistant-builder UI (roadmap step 238),
// same authorizedFetch-based shape the other lib/*.ts clients use.

import { authorizedFetch } from "./auth";

// Mirrors agents/configuration.py:AgentConfiguration exactly -- the
// real, validated set apps/api actually accepts, not a client-side
// guess. llm_provider/enabled_agents below are these same real values.
export interface AgentConfiguration {
  llm_provider: string;
  enabled_agents: string[];
  retrieval_top_k: number;
}

// llm.PROVIDERS' real, current keys (llm/__init__.py). No registry
// endpoint exists to fetch these dynamically -- mirroring them here is
// the same tradeoff every other hardcoded-but-checked-against-the-real-
// source constant in this codebase's frontend already makes.
export const LLM_PROVIDERS = ["openai", "anthropic"] as const;

// agents/configuration.py:KNOWN_AGENT_NAMES' real, current values --
// each agent's own real `.name` class attribute, not restated guesses.
export const KNOWN_AGENT_NAMES = [
  "retriever",
  "citation",
  "planning",
  "memory",
  "conversation",
  "reasoning",
  "quality_review",
  "safety",
] as const;

export interface Assistant {
  id: string;
  tenant_id: string;
  knowledge_base_id: string;
  name: string;
  slug: string;
  description: string | null;
  instructions: string | null;
  agent_configuration: AgentConfiguration;
  is_public: boolean;
  created_at: string;
  updated_at: string;
}

export interface AssistantUpdate {
  name?: string;
  description?: string | null;
  instructions?: string | null;
  agent_configuration?: AgentConfiguration;
  is_public?: boolean;
}

interface Page<T> {
  items: T[];
  limit: number;
  offset: number;
  total: number;
}

async function parseOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}.`);
  }
  return (await response.json()) as T;
}

function basePath(organizationId: string, workspaceId: string, knowledgeBaseId: string): string {
  return (
    `/organizations/${organizationId}/workspaces/${workspaceId}` +
    `/knowledge-bases/${knowledgeBaseId}/assistants`
  );
}

export async function listAssistants(
  organizationId: string,
  workspaceId: string,
  knowledgeBaseId: string,
): Promise<Assistant[]> {
  const response = await authorizedFetch(
    `${basePath(organizationId, workspaceId, knowledgeBaseId)}?limit=100&offset=0`,
  );
  const body = await parseOrThrow<Page<Assistant>>(response);
  return body.items;
}

export async function getAssistant(
  organizationId: string,
  workspaceId: string,
  knowledgeBaseId: string,
  assistantId: string,
): Promise<Assistant> {
  const response = await authorizedFetch(
    `${basePath(organizationId, workspaceId, knowledgeBaseId)}/${assistantId}`,
  );
  return parseOrThrow<Assistant>(response);
}

export async function createAssistant(
  organizationId: string,
  workspaceId: string,
  knowledgeBaseId: string,
  name: string,
  slug: string,
): Promise<Assistant> {
  const response = await authorizedFetch(basePath(organizationId, workspaceId, knowledgeBaseId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, slug }),
  });
  return parseOrThrow<Assistant>(response);
}

export async function updateAssistant(
  organizationId: string,
  workspaceId: string,
  knowledgeBaseId: string,
  assistantId: string,
  patch: AssistantUpdate,
): Promise<Assistant> {
  const response = await authorizedFetch(
    `${basePath(organizationId, workspaceId, knowledgeBaseId)}/${assistantId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    },
  );
  return parseOrThrow<Assistant>(response);
}

export async function deleteAssistant(
  organizationId: string,
  workspaceId: string,
  knowledgeBaseId: string,
  assistantId: string,
): Promise<void> {
  const response = await authorizedFetch(
    `${basePath(organizationId, workspaceId, knowledgeBaseId)}/${assistantId}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}.`);
  }
}
