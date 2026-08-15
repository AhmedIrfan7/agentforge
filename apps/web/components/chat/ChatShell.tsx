"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createAnonymousConversation, streamMessage } from "@/lib/api";
import {
  deriveTitle,
  listConversations,
  saveConversation,
  type StoredConversation,
} from "@/lib/conversationStore";
import type { ChatMessage, MessageRead } from "@/lib/types";
import { ConversationSidebar } from "./ConversationSidebar";
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
  const [storedConversations, setStoredConversations] = useState<StoredConversation[]>([]);
  const [status, setStatus] = useState<Status>("connecting");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const nextLocalId = useRef(0);

  // On mount, resume the most recently active conversation stored for
  // this assistant on this device (step 196's own sidebar/history), or
  // start a fresh anonymous one if none exists yet -- serves AGENTS.md's
  // own "conversation continuity" ask across page reloads, not just
  // within one running tab.
  useEffect(() => {
    let cancelled = false;
    const stored = listConversations(assistantId);
    // localStorage doesn't exist during SSR -- the server (and the
    // client's first hydration pass) always render an empty sidebar,
    // then this effect syncs the real, browser-only value in right
    // after mount. That's the standard, unavoidable shape for any
    // localStorage-backed UI in Next.js; it's not a derivable-during-
    // render value the lint rule's "you might not need an effect"
    // guidance actually applies to.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setStoredConversations(stored);

    const mostRecent = stored[0];
    if (mostRecent) {
      setSession({
        conversationId: mostRecent.conversationId,
        accessToken: mostRecent.accessToken,
      });
      setMessages(mostRecent.messages);
      setStatus("ready");
      return;
    }

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

  // Persists the active conversation to this device's history whenever
  // it gains a real exchange -- an empty, never-used "new conversation"
  // deliberately never appears in the sidebar, matching how a fresh
  // chat in most real chat products only earns a history entry once
  // something was actually said in it.
  useEffect(() => {
    if (!session) {
      return;
    }
    const firstUserMessage = messages.find((message) => message.role === "user");
    if (!firstUserMessage) {
      return;
    }
    saveConversation({
      conversationId: session.conversationId,
      accessToken: session.accessToken,
      assistantId,
      title: deriveTitle(firstUserMessage.content),
      updatedAt: new Date().toISOString(),
      messages,
    });
    // Re-reads the same browser-only localStorage store this effect
    // just wrote to, to refresh the sidebar's list -- same reasoning
    // as the mount-time sync above.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setStoredConversations(listConversations(assistantId));
  }, [session, messages, assistantId]);

  const handleNewConversation = useCallback(() => {
    setStatus("connecting");
    setErrorMessage(null);
    setMessages([]);
    createAnonymousConversation(assistantId)
      .then((conversation) => {
        setSession({
          conversationId: conversation.conversation_id,
          accessToken: conversation.access_token,
        });
        setStatus("ready");
      })
      .catch((error: Error) => {
        setErrorMessage(error.message);
        setStatus("error");
      });
  }, [assistantId]);

  const handleSelectConversation = useCallback((conversation: StoredConversation) => {
    setSession({
      conversationId: conversation.conversationId,
      accessToken: conversation.accessToken,
    });
    setMessages(conversation.messages);
    setErrorMessage(null);
    setStatus("ready");
  }, []);

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

  return (
    <div className={styles.layout}>
      <ConversationSidebar
        conversations={storedConversations}
        activeConversationId={session?.conversationId ?? null}
        onSelect={handleSelectConversation}
        onNewConversation={handleNewConversation}
      />
      <div className={styles.main}>
        {status === "connecting" && !session ? (
          <div className={styles.status}>Starting conversation…</div>
        ) : status === "error" && !session ? (
          <div className={styles.status}>Couldn&apos;t start a conversation: {errorMessage}</div>
        ) : (
          <div className={styles.chatPanel}>
            <MessageList messages={messages} />
            {errorMessage && <div className={styles.errorBanner}>{errorMessage}</div>}
            <MessageInput onSend={handleSend} disabled={status === "sending" || !session} />
          </div>
        )}
      </div>
    </div>
  );
}
