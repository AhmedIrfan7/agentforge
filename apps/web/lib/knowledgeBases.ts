// Real API client for knowledge-base management (roadmap step 236),
// same authorizedFetch-based shape lib/organizations.ts/lib/workspaces.ts
// already established. No update endpoint exists in apps/api (create/
// read/delete only, mirroring Workspace's own scope), so no update
// function here either.

import { authorizedFetch } from "./auth";

export interface KnowledgeBase {
  id: string;
  tenant_id: string;
  workspace_id: string;
  name: string;
  slug: string;
  description: string | null;
  created_at: string;
  updated_at: string;
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

function basePath(organizationId: string, workspaceId: string): string {
  return `/organizations/${organizationId}/workspaces/${workspaceId}/knowledge-bases`;
}

export async function listKnowledgeBases(
  organizationId: string,
  workspaceId: string,
): Promise<KnowledgeBase[]> {
  const response = await authorizedFetch(
    `${basePath(organizationId, workspaceId)}?limit=100&offset=0`,
  );
  const body = await parseOrThrow<Page<KnowledgeBase>>(response);
  return body.items;
}

export async function createKnowledgeBase(
  organizationId: string,
  workspaceId: string,
  name: string,
  slug: string,
): Promise<KnowledgeBase> {
  const response = await authorizedFetch(basePath(organizationId, workspaceId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, slug }),
  });
  return parseOrThrow<KnowledgeBase>(response);
}

export async function deleteKnowledgeBase(
  organizationId: string,
  workspaceId: string,
  knowledgeBaseId: string,
): Promise<void> {
  const response = await authorizedFetch(
    `${basePath(organizationId, workspaceId)}/${knowledgeBaseId}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}.`);
  }
}
