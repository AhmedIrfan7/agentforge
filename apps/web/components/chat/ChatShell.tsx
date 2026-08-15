"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createAnonymousConversation, streamMessage } from "@/lib/api";
import type { ChatMessage, MessageRead } from "@/lib/types";
import { MessageInput } from "./MessageInput";
import { MessageList } from "./MessageList";
import styles from "./ChatShell.module.css";

interface ChatShellProps {
  assistantId: string;
}

interface AnonymousSession {
  conversationId: string;
  accessToken: string;
}

type Status = "connecting" | "ready" | "sending" | "error";

export function ChatShell({ assistantId }: ChatShellProps) {
  const [session, setSession] = useState<AnonymousSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<Status>("connecting");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const nextLocalId = useRef(0);

  useEffect(() => {
    let cancelled = false;
    createAnonymousConversation(assistantId)
      .then((conversation) => {
        if (cancelled) {
          return;
        }
        setSession({
          conversationId: conversation.conversation_id,
          accessToken: conversation.access_token,
        });
        setStatus("ready");
      })
      .catch((error: Error) => {
        if (cancelled) {
          return;
        }
        setErrorMessage(error.message);
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [assistantId]);

  const handleSend = useCallback(
    (content: string) => {
      if (!session) {
        return;
      }

      const userMessage: ChatMessage = {
        id: `local-${nextLocalId.current++}`,
        role: "user",
        content,
      };
      const assistantMessageId = `local-${nextLocalId.current++}`;
      const assistantPlaceholder: ChatMessage = {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        pending: true,
      };
      setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);
      setStatus("sending");
      setErrorMessage(null);

      void streamMessage(assistantId, session.conversationId, session.accessToken, content, {
        onChunk: (text) => {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantMessageId
                ? { ...message, content: message.content + text }
                : message,
            ),
          );
        },
        onDone: (finalMessage: MessageRead) => {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantMessageId
                ? {
                    ...message,
                    content: finalMessage.content,
                    contentHtml: finalMessage.content_html,
                    citations: finalMessage.citations,
                    pending: false,
                  }
                : message,
            ),
          );
          setStatus("ready");
        },
        onError: (error) => {
          setErrorMessage(error.message);
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantMessageId
                ? { ...message, pending: false, content: "Something went wrong." }
                : message,
            ),
          );
          setStatus("ready");
        },
      });
    },
    [assistantId, session],
  );

  if (status === "connecting") {
    return <div className={styles.status}>Starting conversation…</div>;
  }

  if (status === "error" && !session) {
    return <div className={styles.status}>Couldn&apos;t start a conversation: {errorMessage}</div>;
  }

  return (
    <div className={styles.shell}>
      <MessageList messages={messages} />
      {errorMessage && <div className={styles.errorBanner}>{errorMessage}</div>}
      <MessageInput onSend={handleSend} disabled={status === "sending" || !session} />
    </div>
  );
}
