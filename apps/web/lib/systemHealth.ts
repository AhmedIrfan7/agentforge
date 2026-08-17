// API client for the platform-level system-health dashboard (roadmap
// step 248), same authorizedFetch pattern lib/analytics.ts already
// established. Not org-scoped -- GET /system-health takes no
// organization id, matching its own real gate (User.is_platform_admin,
// not a per-org permission).

import { authorizedFetch } from "./auth";

export interface ProviderStatus {
  name: string;
  configured: boolean;
}

export interface SystemHealth {
  queue_depth: number;
  worker_count: number;
  workers: string[];
  providers: ProviderStatus[];
}

export async function getSystemHealth(): Promise<SystemHealth> {
  const response = await authorizedFetch("/system-health");
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}.`);
  }
  return (await response.json()) as SystemHealth;
}
