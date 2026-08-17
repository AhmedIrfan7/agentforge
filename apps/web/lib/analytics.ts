// API client for conversation analytics (roadmap step 243), same
// authorizedFetch pattern lib/organizations.ts already established.

import { authorizedFetch } from "./auth";

export interface ConversationMetrics {
  total_conversations: number;
  total_messages: number;
  average_messages_per_conversation: number;
  conversations_last_7_days: number;
}

export interface KnowledgeMetrics {
  total_documents: number;
  duplicate_document_count: number;
  low_confidence_document_count: number;
  unused_document_count: number;
}

export interface AgentPerformanceEntry {
  agent_name: string;
  execution_count: number;
  success_rate: number;
  average_latency_ms: number;
}

export interface AgentPerformanceMetrics {
  per_agent: AgentPerformanceEntry[];
}

async function getJson<T>(path: string): Promise<T> {
  const response = await authorizedFetch(path);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}.`);
  }
  return (await response.json()) as T;
}

export async function getConversationMetrics(organizationId: string): Promise<ConversationMetrics> {
  return getJson<ConversationMetrics>(`/organizations/${organizationId}/analytics/conversations`);
}

export async function getKnowledgeMetrics(organizationId: string): Promise<KnowledgeMetrics> {
  return getJson<KnowledgeMetrics>(`/organizations/${organizationId}/analytics/knowledge`);
}

export async function getAgentPerformanceMetrics(
  organizationId: string,
): Promise<AgentPerformanceMetrics> {
  return getJson<AgentPerformanceMetrics>(
    `/organizations/${organizationId}/analytics/agent-performance`,
  );
}
