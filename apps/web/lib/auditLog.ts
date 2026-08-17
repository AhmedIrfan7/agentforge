// API client for the audit-log viewer (roadmap step 247), same
// authorizedFetch pattern lib/analytics.ts already established.

import { authorizedFetch } from "./auth";

export interface AuditLogEntry {
  id: string;
  actor_user_id: string | null;
  actor_email: string | null;
  action: string;
  resource_type: string;
  resource_id: string;
  extra: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditLogFilters {
  action?: string;
  resource_type?: string;
  since?: string;
  until?: string;
  limit: number;
  offset: number;
}

export interface AuditLogPage {
  items: AuditLogEntry[];
  total: number;
}

export async function getAuditLogs(
  organizationId: string,
  filters: AuditLogFilters,
): Promise<AuditLogPage> {
  const params = new URLSearchParams();
  if (filters.action) {
    params.set("action", filters.action);
  }
  if (filters.resource_type) {
    params.set("resource_type", filters.resource_type);
  }
  if (filters.since) {
    params.set("since", filters.since);
  }
  if (filters.until) {
    params.set("until", filters.until);
  }
  params.set("limit", String(filters.limit));
  params.set("offset", String(filters.offset));

  const response = await authorizedFetch(
    `/organizations/${organizationId}/audit-logs?${params.toString()}`,
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}.`);
  }
  return (await response.json()) as AuditLogPage;
}
