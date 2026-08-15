import styles from "./TypingIndicator.module.css";

// The "assistant is composing" signal (roadmap step 195) -- a real,
// distinct capability from step 194's own streaming render, matching
// AGENTS.md's own "CHAT EXPERIENCE" section, which lists "Streaming
// responses" and "Typing indicators" as separate line items. Shown for
// the real gap between sending a message and the first SSE chunk
// arriving: orchestrator.handle() computes the FULL response before
// apps/api's streaming endpoint starts emitting anything (see
// routers/conversation.py's own docstring), so that gap is genuine
// backend work time, not an artificial delay -- once the first word
// chunk lands, ChatShell swaps this out for the real streamed text.
export function TypingIndicator() {
  return (
    <span className={styles.dots} role="status" aria-label="Assistant is typing">
      <span className={styles.dot} />
      <span className={styles.dot} />
      <span className={styles.dot} />
    </span>
  );
}
