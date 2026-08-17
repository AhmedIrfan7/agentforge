// API client for API-key management (roadmap step 241), same
// authorizedFetch pattern lib/organizations.ts already established.

import { authorizedFetch } from "./auth";

export interface ApiKey {
  id: string;
  tenant_id: string;
  name: string;
  key_prefix: string;
  created_by_user_id: string;
  revoked_at: string | null;
  created_at: string;
}

export interface ApiKeyCreated extends ApiKey {
  // Present ONLY in the create response -- the one moment the raw key
  // is ever visible. Never returned by list, never persisted anywhere
  // the frontend can re-fetch it from.
  key: string;
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

export async function listApiKeys(organizationId: string): Promise<ApiKey[]> {
  const response = await authorizedFetch(
    `/organizations/${organizationId}/api-keys?limit=200&offset=0`,
  );
  const body = await parseOrThrow<{ items: ApiKey[] }>(response);
  return body.items;
}

export async function createApiKey(organizationId: string, name: string): Promise<ApiKeyCreated> {
  const response = await authorizedFetch(`/organizations/${organizationId}/api-keys`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return parseOrThrow<ApiKeyCreated>(response);
}

export async function revokeApiKey(organizationId: string, apiKeyId: string): Promise<void> {
  const response = await authorizedFetch(`/organizations/${organizationId}/api-keys/${apiKeyId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}.`);
  }
}
