// Real API client for workspace management (roadmap step 235), same
// authorizedFetch-based shape lib/organizations.ts already established.

import { authorizedFetch } from "./auth";

export interface Workspace {
  id: string;
  tenant_id: string;
  name: string;
  slug: string;
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

export async function listWorkspaces(organizationId: string): Promise<Workspace[]> {
  const response = await authorizedFetch(
    `/organizations/${organizationId}/workspaces?limit=100&offset=0`,
  );
  const body = await parseOrThrow<Page<Workspace>>(response);
  return body.items;
}

export async function createWorkspace(
  organizationId: string,
  name: string,
  slug: string,
): Promise<Workspace> {
  const response = await authorizedFetch(`/organizations/${organizationId}/workspaces`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, slug }),
  });
  return parseOrThrow<Workspace>(response);
}

export async function deleteWorkspace(organizationId: string, workspaceId: string): Promise<void> {
  const response = await authorizedFetch(
    `/organizations/${organizationId}/workspaces/${workspaceId}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}.`);
  }
}
