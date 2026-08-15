import { ChatShell } from "@/components/chat/ChatShell";
import styles from "./page.module.css";

// The chat UI shell (roadmap step 194) reads which assistant to talk
// to from a query param rather than a route segment or auth context --
// no dashboard (auth-gated org/workspace/assistant navigation, step
// 233) exists yet to hand this page an assistant id any other way, the
// same reason apps/api's own real embeddable-widget deployment channel
// (routers/public_conversation.py, step 192) is keyed by assistant_id
// alone. A future embed script or dashboard "open chat" link both plug
// into this same `?assistantId=` contract without this page changing.
export default async function ChatPage({
  searchParams,
}: {
  searchParams: Promise<{ assistantId?: string }>;
}) {
  const { assistantId } = await searchParams;

  if (!assistantId) {
    return (
      <main className={styles.main}>
        <div className={styles.missingAssistant}>
          Add <code>?assistantId=&lt;id&gt;</code> to the URL to start a conversation.
        </div>
      </main>
    );
  }

  return (
    <main className={styles.main}>
      {/* key forces a full remount if assistantId ever changes via
          client-side navigation -- ChatShell's own sidebar/session
          state is only ever correct for the assistant it mounted
          with. */}
      <ChatShell key={assistantId} assistantId={assistantId} />
    </main>
  );
}
