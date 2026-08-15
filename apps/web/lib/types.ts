// Hand-written mirrors of apps/api's Pydantic response shapes (field
// names match the JSON wire format exactly, snake_case included) --
// see packages/shared/src/index.ts's own comment: once apps/api grows
// an OpenAPI schema, generate these instead of hand-maintaining them.

export interface CitationRead {
  chunk_id: string;
  document_id: string;
  document_title: string;
  knowledge_base_name: string;
  section: string | null;
}

export interface MessageRead {
  id: string;
  tenant_id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  content_html: string;
  citations: CitationRead[];
  feedback_type: string | null;
  created_at: string;
  updated_at: string;
}

export interface AnonymousConversationRead {
  conversation_id: string;
  access_token: string;
}

// Frontend-only view model for a message in the chat UI -- distinct
// from MessageRead because a message being actively streamed has no
// id/citations/content_html from the backend yet (those only exist
// once the "done" SSE event delivers the real, persisted MessageRead).
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  contentHtml?: string;
  citations?: CitationRead[];
  pending?: boolean;
}
