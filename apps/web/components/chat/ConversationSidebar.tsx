"use client";

import { useState } from "react";
import { searchConversations, type StoredConversation } from "@/lib/conversationStore";
import styles from "./ConversationSidebar.module.css";

interface ConversationSidebarProps {
  conversations: StoredConversation[];
  activeConversationId: string | null;
  onSelect: (conversation: StoredConversation) => void;
  onNewConversation: () => void;
}

export function ConversationSidebar({
  conversations,
  activeConversationId,
  onSelect,
  onNewConversation,
}: ConversationSidebarProps) {
  const [query, setQuery] = useState("");
  const filtered = searchConversations(conversations, query);

  return (
    <nav className={styles.sidebar} aria-label="Conversations">
      <button type="button" className={styles.newButton} onClick={onNewConversation}>
        + New conversation
      </button>
      {conversations.length > 0 && (
        <input
          type="search"
          className={styles.search}
          placeholder="Search conversations…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search conversations"
        />
      )}
      <ul className={styles.list}>
        {filtered.length === 0 && (
          <li className={styles.empty}>
            {conversations.length === 0 ? "No conversations yet." : "No matching conversations."}
          </li>
        )}
        {filtered.map((conversation) => (
          <li key={conversation.conversationId}>
            <button
              type="button"
              className={
                conversation.conversationId === activeConversationId
                  ? styles.itemActive
                  : styles.item
              }
              aria-current={conversation.conversationId === activeConversationId}
              onClick={() => onSelect(conversation)}
            >
              <span className={styles.title}>{conversation.title || "New conversation"}</span>
              <span className={styles.timestamp}>
                {new Date(conversation.updatedAt).toLocaleString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
