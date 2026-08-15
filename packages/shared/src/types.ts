// Hand-written mirrors of apps/api's Pydantic response shapes (field
// names match the JSON wire format exactly, snake_case included) --
// see index.ts's own comment: once apps/api grows an OpenAPI schema,
// generate these instead of hand-maintaining them.
//
// Promoted here from apps/web/lib/types.ts (roadmap step 205) once
// apps/widget became a second real consumer needing the identical
// shapes -- the same "share once a genuine second caller exists" bar
// this whole project applies elsewhere.

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

// Framework-agnostic view model for a message in a chat UI -- distinct
// from MessageRead because a message being actively streamed has no
// id/citations/content_html from the backend yet (those only exist
// once the "done" SSE event delivers the real, persisted MessageRead).
// Consumed identically by apps/web's React rendering and apps/widget's
// plain DOM rendering -- nothing about this shape is React-specific.
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  contentHtml?: string;
  citations?: CitationRead[];
  pending?: boolean;
}
