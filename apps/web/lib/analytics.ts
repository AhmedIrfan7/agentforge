// API client for conversation analytics (roadmap step 243), same
// authorizedFetch pattern lib/organizations.ts already established.

import { authorizedFetch } from "./auth";

export interface ConversationMetrics {
  total_conversations: number;
  total_messages: number;
  average_messages_per_conversation: number;
  conversations_last_7_days: number;
}

export async function getConversationMetrics(organizationId: string): Promise<ConversationMetrics> {
  const response = await authorizedFetch(
    `/organizations/${organizationId}/analytics/conversations`,
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}.`);
  }
  return (await response.json()) as ConversationMetrics;
}
