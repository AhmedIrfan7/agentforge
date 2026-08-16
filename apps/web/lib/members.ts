// API client for org-member listing + role management (roadmap step
// 239), same authorizedFetch pattern lib/organizations.ts already
// established.

import { authorizedFetch } from "./auth";

export interface Member {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role_id: string;
  role_name: string;
  role_display_name: string;
  created_at: string;
}

// Mirrors the backend's own seeded role catalog (migrations/versions/
// *_seed_role_catalog*.py) -- no endpoint lists roles themselves, so
// this stays a plain constant, same as apps/widget's own
// LLM_PROVIDERS/KNOWN_AGENT_NAMES precedent for a small, backend-fixed
// enum with no dedicated listing endpoint.
export const ROLE_NAMES = [
  "org_owner",
  "admin",
  "manager",
  "knowledge_manager",
  "developer",
  "support_agent",
  "analyst",
  "viewer",
  "end_user",
  "guest",
] as const;

async function parseOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}.`);
  }
  return (await response.json()) as T;
}

export async function listMembers(organizationId: string): Promise<Member[]> {
  const response = await authorizedFetch(
    `/organizations/${organizationId}/members?limit=200&offset=0`,
  );
  const body = await parseOrThrow<{ items: Member[] }>(response);
  return body.items;
}

export async function updateMemberRole(
  organizationId: string,
  membershipId: string,
  roleName: string,
): Promise<Member> {
  const response = await authorizedFetch(
    `/organizations/${organizationId}/members/${membershipId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role_name: roleName }),
    },
  );
  return parseOrThrow<Member>(response);
}

export async function removeMember(organizationId: string, membershipId: string): Promise<void> {
  const response = await authorizedFetch(
    `/organizations/${organizationId}/members/${membershipId}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}.`);
  }
}
