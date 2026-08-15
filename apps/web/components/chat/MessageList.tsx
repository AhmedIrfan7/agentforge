import type { ChatMessage } from "@/lib/types";
import styles from "./MessageList.module.css";
import { TypingIndicator } from "./TypingIndicator";

interface MessageListProps {
  messages: ChatMessage[];
}

export function MessageList({ messages }: MessageListProps) {
  return (
    <div className={styles.list} data-testid="message-list">
      {messages.map((message) => (
        <div
          key={message.id}
          className={message.role === "user" ? styles.userMessage : styles.assistantMessage}
        >
          <span className={styles.role}>{message.role === "user" ? "You" : "Assistant"}</span>
          {message.contentHtml ? (
            <div
              className={styles.content}
              // Safe: content_html is rendered server-side by
              // apps/api's message_rendering.py (Python-Markdown +
              // nh3 sanitization, roadmap steps 185/186) before it
              // ever reaches this client.
              dangerouslySetInnerHTML={{ __html: message.contentHtml }}
            />
          ) : message.pending && message.content === "" ? (
            <TypingIndicator />
          ) : (
            <div className={styles.content}>
              {message.content}
              {message.pending && <span className={styles.cursor} />}
            </div>
          )}
          {message.citations && message.citations.length > 0 && (
            <div className={styles.citations}>
              {message.citations.map((citation) => (
                <span key={citation.chunk_id} className={styles.citation}>
                  {citation.document_title}
                  {citation.section ? ` — ${citation.section}` : ""}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
