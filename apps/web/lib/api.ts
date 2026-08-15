// Thin, app-specific wrapper around @agentforge/shared's own real API
// client (roadmap step 205 -- promoted there once apps/widget became a
// second real consumer of the identical logic). This file's only real
// job is supplying the one thing a Next.js app resolves differently
// from a vanilla-TS widget script: the API base URL, a build-time env
// var here rather than a runtime <script data-api-url> attribute.

import {
  createAnonymousConversation as sharedCreateAnonymousConversation,
  streamMessage as sharedStreamMessage,
  type StreamCallbacks,
} from "@agentforge/shared";

export { ApiError, type StreamCallbacks } from "@agentforge/shared";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function createAnonymousConversation(assistantId: string) {
  return sharedCreateAnonymousConversation(API_BASE_URL, assistantId);
}

export function streamMessage(
  assistantId: string,
  conversationId: string,
  accessToken: string,
  content: string,
  callbacks: StreamCallbacks,
) {
  return sharedStreamMessage(
    API_BASE_URL,
    assistantId,
    conversationId,
    accessToken,
    content,
    callbacks,
  );
}
