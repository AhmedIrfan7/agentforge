// Real API client for organization + security-settings management
// (roadmap step 234), built on lib/auth.ts's own authorizedFetch --
// every call here needs the silent-refresh-on-401 behavior a plain
// fetch wouldn't have, the same reasoning that made authorizedFetch a
// shared utility rather than something private to lib/auth.ts itself.

import { authorizedFetch } from "./auth";

export interface Organization {
  id: string;
  name: string;
  slug: string;
  logo_url: string | null;
  primary_color: string | null;
  created_at: string;
  updated_at: string;
}

export interface SecuritySettings {
  id: string;
  tenant_id: string;
  session_timeout_minutes: number | null;
  password_min_length: number | null;
  password_require_uppercase: boolean;
  password_require_number: boolean;
  password_require_symbol: boolean;
  mfa_required: boolean;
  allowed_domains: string[];
  created_at: string;
  updated_at: string;
}

export interface OrganizationUpdate {
  name?: string;
  logo_url?: string | null;
  primary_color?: string | null;
}

export interface SecuritySettingsUpdate {
  session_timeout_minutes?: number | null;
  password_min_length?: number | null;
  password_require_uppercase?: boolean;
  password_require_number?: boolean;
  password_require_symbol?: boolean;
  mfa_required?: boolean;
  allowed_domains?: string[];
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

export async function listOrganizations(): Promise<Organization[]> {
  // Was `?limit=1&offset=0` -- silently capped every caller to at most
  // ONE organization even though the backend genuinely supports a user
  // belonging to several (repo.list_for_user). Real bug: an org switcher
  // is pointless if the client can never see more than one org to
  // switch to. 50 comfortably covers this feature's real scale today.
  const response = await authorizedFetch("/organizations?limit=50&offset=0");
  const body = await parseOrThrow<{ items: Organization[] }>(response);
  return body.items;
}

export async function createOrganization(name: string, slug: string): Promise<Organization> {
  const response = await authorizedFetch("/organizations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, slug }),
  });
  return parseOrThrow<Organization>(response);
}

export async function updateOrganization(
  organizationId: string,
  patch: OrganizationUpdate,
): Promise<Organization> {
  const response = await authorizedFetch(`/organizations/${organizationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return parseOrThrow<Organization>(response);
}

export async function getSecuritySettings(organizationId: string): Promise<SecuritySettings> {
  const response = await authorizedFetch(`/organizations/${organizationId}/security-settings`);
  return parseOrThrow<SecuritySettings>(response);
}

export async function updateSecuritySettings(
  organizationId: string,
  patch: SecuritySettingsUpdate,
): Promise<SecuritySettings> {
  const response = await authorizedFetch(`/organizations/${organizationId}/security-settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return parseOrThrow<SecuritySettings>(response);
}
