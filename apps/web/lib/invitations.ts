// API client for invitation-management (roadmap step 240), same
// authorizedFetch pattern lib/organizations.ts already established.
// Create/list/revoke live under an org; accept is its own top-level
// endpoint (the caller doesn't know which org a token belongs to
// ahead of time -- same reasoning routers/invitation.py's own accept
// router already documents).

import { authorizedFetch } from "./auth";

export interface Invitation {
  id: string;
  tenant_id: string;
  email: string;
  role_id: string;
  role_name: string;
  workspace_id: string | null;
  invited_by_user_id: string;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
  status: "pending" | "accepted" | "revoked" | "expired";
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

export async function listInvitations(organizationId: string): Promise<Invitation[]> {
  const response = await authorizedFetch(
    `/organizations/${organizationId}/invitations?limit=200&offset=0`,
  );
  const body = await parseOrThrow<{ items: Invitation[] }>(response);
  return body.items;
}

export async function createInvitation(
  organizationId: string,
  email: string,
  roleName: string,
): Promise<Invitation> {
  const response = await authorizedFetch(`/organizations/${organizationId}/invitations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, role_name: roleName }),
  });
  return parseOrThrow<Invitation>(response);
}

export async function revokeInvitation(
  organizationId: string,
  invitationId: string,
): Promise<void> {
  const response = await authorizedFetch(
    `/organizations/${organizationId}/invitations/${invitationId}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}.`);
  }
}

export async function acceptInvitation(token: string): Promise<void> {
  const response = await authorizedFetch("/invitations/accept", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}.`);
  }
}
