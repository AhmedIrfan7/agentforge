import type { StoredConversation } from "@/lib/conversationStore";
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
  return (
    <nav className={styles.sidebar} aria-label="Conversations">
      <button type="button" className={styles.newButton} onClick={onNewConversation}>
        + New conversation
      </button>
      <ul className={styles.list}>
        {conversations.length === 0 && <li className={styles.empty}>No conversations yet.</li>}
        {conversations.map((conversation) => (
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
