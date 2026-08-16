// Real API client for document upload/list/status/detail (roadmap
// steps 236-237), same authorizedFetch-based shape the other
// lib/*.ts clients use. Deliberately covers only what these steps ask
// for -- upload, list, status, chunking decision, pipeline stages --
// not chunking-strategy OVERRIDE, reindex, or versions, which are
// real apps/api capabilities but have no roadmap step asking for a UI
// yet (this stays read-only).

import { authorizedFetch } from "./auth";

export interface Document {
  id: string;
  tenant_id: string;
  knowledge_base_id: string;
  title: string;
  status: string;
  content_type: string;
  size_bytes: number;
  chunking_strategy: string | null;
  chunking_strategy_source: string | null;
  chunking_strategy_reasoning: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentStatus {
  id: string;
  status: string;
  updated_at: string;
}

export interface PipelineStage {
  stage: string;
  status: string;
}

export interface DocumentPipelineStatus {
  id: string;
  status: string;
  stages: PipelineStage[];
  chunk_count: number;
  embedded_chunk_count: number;
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

function basePath(organizationId: string, workspaceId: string, knowledgeBaseId: string): string {
  return (
    `/organizations/${organizationId}/workspaces/${workspaceId}` +
    `/knowledge-bases/${knowledgeBaseId}/documents`
  );
}

export async function listDocuments(
  organizationId: string,
  workspaceId: string,
  knowledgeBaseId: string,
): Promise<Document[]> {
  const response = await authorizedFetch(
    `${basePath(organizationId, workspaceId, knowledgeBaseId)}?limit=100&offset=0`,
  );
  const body = await parseOrThrow<Page<Document>>(response);
  return body.items;
}

export async function uploadDocument(
  organizationId: string,
  workspaceId: string,
  knowledgeBaseId: string,
  file: File,
): Promise<Document> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await authorizedFetch(basePath(organizationId, workspaceId, knowledgeBaseId), {
    method: "POST",
    body: formData,
  });
  return parseOrThrow<Document>(response);
}

export async function getDocumentStatus(
  organizationId: string,
  workspaceId: string,
  knowledgeBaseId: string,
  documentId: string,
): Promise<DocumentStatus> {
  const response = await authorizedFetch(
    `${basePath(organizationId, workspaceId, knowledgeBaseId)}/${documentId}/status`,
  );
  return parseOrThrow<DocumentStatus>(response);
}

export async function getDocument(
  organizationId: string,
  workspaceId: string,
  knowledgeBaseId: string,
  documentId: string,
): Promise<Document> {
  const response = await authorizedFetch(
    `${basePath(organizationId, workspaceId, knowledgeBaseId)}/${documentId}`,
  );
  return parseOrThrow<Document>(response);
}

export async function getDocumentPipelineStatus(
  organizationId: string,
  workspaceId: string,
  knowledgeBaseId: string,
  documentId: string,
): Promise<DocumentPipelineStatus> {
  const response = await authorizedFetch(
    `${basePath(organizationId, workspaceId, knowledgeBaseId)}/${documentId}/pipeline-status`,
  );
  return parseOrThrow<DocumentPipelineStatus>(response);
}
