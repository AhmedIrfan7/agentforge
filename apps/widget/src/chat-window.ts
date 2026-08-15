// Chat window UI (roadmap step 205) -- real message list, input, and
// SSE streaming render, sharing its wire-format types and API-calling
// logic with apps/web via @agentforge/shared (the second real
// consumer that promoted apps/web's own lib/types.ts/lib/api.ts out
// into that package -- the same "share once a genuine second caller
// exists" bar this whole project applies elsewhere). Vanilla DOM here
// where apps/web's own ChatShell.tsx/MessageList.tsx use React -- same
// real behavior, different rendering mechanism, since this app has no
// framework (201).
//
// The anonymous conversation is created LAZILY, on first send, not
// eagerly when the script loads. Unlike apps/web's own dedicated
// /chat page (visiting it already implies intent to chat), this
// script runs on EVERY page of a customer's site -- eagerly creating
// a Conversation row per page view for a visitor who never opens the
// widget would be real, wasted backend work this step doesn't need to
// cause.

import {
  createAnonymousConversation,
  streamMessage,
  type ChatMessage,
  type MessageRead,
} from "@agentforge/shared";
import type { WidgetConfig } from "./config";

const CHAT_WINDOW_STYLES = `
  .panel.open { display: flex; flex-direction: column; }
  .header {
    padding: 12px 16px;
    font-weight: 600;
    background: #4f46e5;
    color: white;
    flex-shrink: 0;
  }
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .message { display: flex; }
  .message.user { justify-content: flex-end; }
  .message.assistant { justify-content: flex-start; }
  .stack {
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-width: 80%;
  }
  .bubble {
    padding: 8px 12px;
    border-radius: 12px;
    font-size: 14px;
    line-height: 1.4;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .message.user .bubble { background: #4f46e5; color: white; }
  .message.assistant .bubble { background: #f3f4f6; color: #111827; }
  .citations {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .citation {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 999px;
    background: #e5e7eb;
    color: #374151;
  }
  .input-row {
    display: flex;
    gap: 8px;
    padding: 10px;
    border-top: 1px solid #e5e7eb;
    flex-shrink: 0;
  }
  .input-row textarea {
    flex: 1;
    resize: none;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 6px 8px;
    font: inherit;
    font-size: 14px;
    max-height: 80px;
  }
  .input-row button {
    border: none;
    border-radius: 8px;
    background: #4f46e5;
    color: white;
    padding: 0 14px;
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }
  .input-row button:disabled { opacity: 0.5; cursor: not-allowed; }
`;

interface AnonymousSession {
  conversationId: string;
  accessToken: string;
}

export function renderChatWindow(
  shadow: ShadowRoot,
  panel: HTMLElement,
  config: WidgetConfig,
): void {
  const style = document.createElement("style");
  style.textContent = CHAT_WINDOW_STYLES;
  shadow.appendChild(style);

  const header = document.createElement("div");
  header.className = "header";
  header.textContent = "Chat";
  panel.appendChild(header);

  const messagesEl = document.createElement("div");
  messagesEl.className = "messages";
  panel.appendChild(messagesEl);

  const inputRow = document.createElement("div");
  inputRow.className = "input-row";
  const textarea = document.createElement("textarea");
  textarea.placeholder = "Send a message…";
  textarea.rows = 1;
  const sendButton = document.createElement("button");
  sendButton.type = "button";
  sendButton.textContent = "Send";
  inputRow.appendChild(textarea);
  inputRow.appendChild(sendButton);
  panel.appendChild(inputRow);

  let session: AnonymousSession | null = null;
  let messages: ChatMessage[] = [];
  let nextLocalId = 0;
  let sending = false;

  function renderMessages(): void {
    messagesEl.innerHTML = "";
    for (const message of messages) {
      const row = document.createElement("div");
      row.className = `message ${message.role}`;

      const stack = document.createElement("div");
      stack.className = "stack";

      const bubble = document.createElement("div");
      bubble.className = "bubble";
      if (message.contentHtml) {
        // Safe: content_html is rendered server-side by apps/api's
        // message_rendering.py (Python-Markdown + nh3 sanitization,
        // steps 185/186) before it ever reaches this client -- the
        // same trust boundary apps/web's own MessageList.tsx already
        // relies on.
        bubble.innerHTML = message.contentHtml;
      } else {
        bubble.textContent = message.content;
      }
      stack.appendChild(bubble);

      if (message.citations && message.citations.length > 0) {
        const citationsEl = document.createElement("div");
        citationsEl.className = "citations";
        for (const citation of message.citations) {
          const pill = document.createElement("span");
          pill.className = "citation";
          pill.textContent = citation.section
            ? `${citation.document_title} — ${citation.section}`
            : citation.document_title;
          citationsEl.appendChild(pill);
        }
        stack.appendChild(citationsEl);
      }

      row.appendChild(stack);
      messagesEl.appendChild(row);
    }
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function setSending(value: boolean): void {
    sending = value;
    sendButton.disabled = sending;
    textarea.disabled = sending;
  }

  async function handleSend(): Promise<void> {
    const content = textarea.value.trim();
    if (!content || sending) {
      return;
    }
    textarea.value = "";
    setSending(true);

    if (!session) {
      try {
        const conversation = await createAnonymousConversation(config.apiUrl, config.assistantId);
        session = {
          conversationId: conversation.conversation_id,
          accessToken: conversation.access_token,
        };
      } catch (error) {
        console.error(error);
        setSending(false);
        return;
      }
    }

    const userMessageId = `local-${nextLocalId++}`;
    const assistantMessageId = `local-${nextLocalId++}`;
    messages = [
      ...messages,
      { id: userMessageId, role: "user", content },
      { id: assistantMessageId, role: "assistant", content: "", pending: true },
    ];
    renderMessages();

    await streamMessage(
      config.apiUrl,
      config.assistantId,
      session.conversationId,
      session.accessToken,
      content,
      {
        onChunk: (text) => {
          messages = messages.map((message) =>
            message.id === assistantMessageId
              ? { ...message, content: message.content + text }
              : message,
          );
          renderMessages();
        },
        onDone: (finalMessage: MessageRead) => {
          messages = messages.map((message) =>
            message.id === assistantMessageId
              ? {
                  ...message,
                  content: finalMessage.content,
                  contentHtml: finalMessage.content_html,
                  citations: finalMessage.citations,
                  pending: false,
                }
              : message,
          );
          renderMessages();
          setSending(false);
        },
        onError: (error) => {
          console.error(error);
          messages = messages.map((message) =>
            message.id === assistantMessageId
              ? { ...message, pending: false, content: "Something went wrong." }
              : message,
          );
          renderMessages();
          setSending(false);
        },
      },
    );
  }

  sendButton.addEventListener("click", () => {
    void handleSend();
  });
  textarea.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  });
}
