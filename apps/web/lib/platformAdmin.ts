// API client for the cross-org platform-admin view (roadmap step 249),
// same authorizedFetch pattern lib/systemHealth.ts already established.
// Not org-scoped -- GET /platform-admin/organizations takes no
// organization id, gated by User.is_platform_admin server-side.

import { authorizedFetch } from "./auth";

export interface OrganizationSummary {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  workspace_count: number;
  member_count: number;
  conversation_count: number;
  document_count: number;
}

export interface PlatformOrganizations {
  organizations: OrganizationSummary[];
}

export async function getPlatformOrganizations(): Promise<PlatformOrganizations> {
  const response = await authorizedFetch("/platform-admin/organizations");
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}.`);
  }
  return (await response.json()) as PlatformOrganizations;
}
