import type { ChatMessage } from "@agentforge/shared";

const STORAGE_PREFIX = "agentforge:conversations:";
const MAX_STORED_CONVERSATIONS = 20;
const TITLE_MAX_LENGTH = 42;

// Client-side conversation history (roadmap step 196), backed by
// localStorage rather than apps/api's own list_conversations endpoint
// (182) -- that endpoint requires a real authenticated JWT + Membership,
// which nothing in apps/web can supply yet (no dashboard/login UI
// exists until step 233). The anonymous flow this chat UI shell (194)
// actually runs on has no concept of "list my past conversations"
// server-side either, by design: an anonymous session is proven only
// by possessing its own access token (auth/jwt.py's own "anonymous_
// session" ticket), so there's no real identity to list conversations
// FOR. "Your recent chats on this device" is the honest, real
// capability this surface can offer today -- the same pattern real
// embeddable chat widgets use for anonymous visitors. Once step 233's
// authenticated dashboard exists, it gets its own real sidebar wired
// to list_conversations instead; this remains the anonymous-widget
// experience.
export interface StoredConversation {
  conversationId: string;
  accessToken: string;
  assistantId: string;
  title: string;
  updatedAt: string;
  messages: ChatMessage[];
}

function storageKey(assistantId: string): string {
  return `${STORAGE_PREFIX}${assistantId}`;
}

export function listConversations(assistantId: string): StoredConversation[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(storageKey(assistantId));
    if (!raw) {
      return [];
    }
    const parsed: StoredConversation[] = JSON.parse(raw);
    return [...parsed].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  } catch {
    return [];
  }
}

export function saveConversation(conversation: StoredConversation): void {
  if (typeof window === "undefined") {
    return;
  }
  const rest = listConversations(conversation.assistantId).filter(
    (entry) => entry.conversationId !== conversation.conversationId,
  );
  const updated = [conversation, ...rest].slice(0, MAX_STORED_CONVERSATIONS);
  window.localStorage.setItem(storageKey(conversation.assistantId), JSON.stringify(updated));
}

export function deriveTitle(firstUserMessage: string): string {
  const trimmed = firstUserMessage.trim();
  return trimmed.length > TITLE_MAX_LENGTH ? `${trimmed.slice(0, TITLE_MAX_LENGTH)}…` : trimmed;
}

// Client-side conversation search (roadmap step 197) over this
// device's own stored history -- apps/api's real message search
// endpoints (routers/conversation.py:search_keyword/search_semantic,
// step 183) search across the CALLER's OWN conversations via an
// authenticated request, which this anonymous chat UI shell has no way
// to make (same constraint step 196's own sidebar already documented).
// This searches the exact same local corpus the sidebar already
// renders: a conversation matches if its title OR any message's
// content contains the query, case-insensitively.
export function searchConversations(
  conversations: StoredConversation[],
  query: string,
): StoredConversation[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return conversations;
  }
  return conversations.filter(
    (conversation) =>
      conversation.title.toLowerCase().includes(normalized) ||
      conversation.messages.some((message) => message.content.toLowerCase().includes(normalized)),
  );
}
