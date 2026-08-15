// Client for apps/api's public, zero-auth anonymous-conversation
// endpoints (routers/public_conversation.py, step 192) -- the one
// real backend surface BOTH apps/web's chat UI shell (194) and
// apps/widget's chat window (205) can reach without an authenticated
// session. Promoted here from apps/web/lib/api.ts once apps/widget
// became a second real consumer.
//
// `apiUrl` is an explicit parameter on every function here, not an
// internally-resolved constant -- unlike apps/web (a Next.js app,
// where `process.env.NEXT_PUBLIC_API_URL` is a real, build-time-
// inlined value), apps/widget resolves its own API URL at runtime
// from the embedding page's own <script data-api-url> attribute
// (config.ts). This package can't assume either resolution strategy,
// so it stays a pure function of its inputs; each app's own thin
// wrapper supplies the value it already knows how to resolve.

import type { AnonymousConversationRead, MessageRead } from "./types";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function createAnonymousConversation(
  apiUrl: string,
  assistantId: string,
): Promise<AnonymousConversationRead> {
  const response = await fetch(`${apiUrl}/public/assistants/${assistantId}/conversations`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new ApiError(`Failed to start conversation (${response.status})`, response.status);
  }
  return response.json();
}

export interface StreamCallbacks {
  onChunk: (text: string) => void;
  onDone: (message: MessageRead) => void;
  onError: (error: Error) => void;
}

// Consumes apps/api's real SSE transport (routers/public_conversation.py
// :send_anonymous_message_streaming, step 194) by hand -- EventSource
// can't send a POST body or an Authorization header, so this reads the
// response body's stream directly and splits it on blank lines the
// same way the backend's own event_stream/build_message_stream writes
// each event (`event: <type>\ndata: <json>\n\n`).
export async function streamMessage(
  apiUrl: string,
  assistantId: string,
  conversationId: string,
  accessToken: string,
  content: string,
  callbacks: StreamCallbacks,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(
      `${apiUrl}/public/assistants/${assistantId}/conversations/${conversationId}/messages/stream`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ content }),
      },
    );
  } catch (error) {
    callbacks.onError(error instanceof Error ? error : new Error("Network error."));
    return;
  }

  if (!response.ok || !response.body) {
    callbacks.onError(new ApiError(`Failed to send message (${response.status})`, response.status));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      const eventLine = rawEvent.split("\n").find((line) => line.startsWith("event: "));
      const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data: "));
      if (eventLine && dataLine) {
        const eventType = eventLine.slice("event: ".length);
        const data: unknown = JSON.parse(dataLine.slice("data: ".length));
        if (eventType === "message" && typeof data === "string") {
          callbacks.onChunk(data);
        } else if (eventType === "done") {
          callbacks.onDone(data as MessageRead);
        }
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
}
