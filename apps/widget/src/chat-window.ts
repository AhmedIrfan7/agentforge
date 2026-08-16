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
//
// As of step 229, a real mic button + waveform indicator wire this
// panel into the full voice pipeline Milestone 8 already built and
// tested end to end (216-228) -- `voice.ts` owns the low-level
// browser I/O (MediaRecorder, the websocket protocol, real-time mic
// levels); this module owns the UI state machine and reuses the SAME
// message list/bubble rendering text chat already has, since a real
// voice turn's transcript/reply ARE real chat messages, not a
// parallel display. `ensureSession` is the ONE real refactor this
// step needed: the anonymous-conversation-creation logic `handleSend`
// already had, extracted once voice became a genuine second real
// caller needing it -- same "share once a second caller exists" bar
// this whole project applies everywhere.
//
// The mic button is a real "push to talk" control, not an always-on
// mic: `startRecording`/`stopRecording` bound to explicit clicks, not
// a persistently-open stream the server's own VAD alone decides when
// to end -- the server's own silence-timeout/voice-activity detection
// (223/224) still apply WHILE recording as a real fallback, but a
// deliberate stop click sends a real `end_turn` immediately rather
// than waiting on them. Clicking the mic again WHILE the assistant is
// speaking is real, explicit barge-in: stops local playback
// immediately (the server cancelling synthesis doesn't silence audio
// the client already started playing) and sends the real `interrupt`
// message before starting a new recording.

import {
  createAnonymousConversation,
  streamMessage,
  type ChatMessage,
  type CitationRead,
  type MessageRead,
} from "@agentforge/shared";
import type { WidgetConfig } from "./config";
import { endVoiceSession, startVoiceSession, VoiceSession } from "./voice";

const CHAT_WINDOW_STYLES = `
  .panel.open { display: flex; flex-direction: column; }
  .header {
    padding: 12px 16px;
    font-weight: 600;
    background: var(--af-primary-color);
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
  .message.user .bubble { background: var(--af-primary-color); color: white; }
  .message.assistant .bubble {
    background: var(--af-assistant-bubble-bg);
    color: var(--af-assistant-bubble-text);
  }
  .citations {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .citation {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--af-citation-bg);
    color: var(--af-citation-text);
  }
  .input-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px;
    border-top: 1px solid var(--af-border);
    flex-shrink: 0;
  }
  .input-row textarea {
    flex: 1;
    resize: none;
    border: 1px solid var(--af-input-border);
    border-radius: 8px;
    padding: 6px 8px;
    font: inherit;
    font-size: 14px;
    max-height: 80px;
    background: var(--af-surface);
    color: var(--af-surface-text);
  }
  .input-row button {
    border: none;
    border-radius: 8px;
    background: var(--af-primary-color);
    color: white;
    padding: 0 14px;
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }
  .input-row button:disabled { opacity: 0.5; cursor: not-allowed; }
  .mic-button {
    flex-shrink: 0;
    width: 36px;
    height: 36px;
    padding: 0;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .mic-button.recording {
    background: #dc2626;
    animation: af-mic-pulse 1.4s ease-in-out infinite;
  }
  .mic-button.processing { opacity: 0.6; cursor: wait; }
  @keyframes af-mic-pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.5); }
    50% { box-shadow: 0 0 0 6px rgba(220, 38, 38, 0); }
  }
  .waveform-row {
    display: none;
    align-items: center;
    padding: 0 10px 10px;
    flex-shrink: 0;
  }
  .waveform-row.active { display: flex; }
  .waveform {
    width: 100%;
    height: 32px;
    display: block;
  }
`;

interface AnonymousSession {
  conversationId: string;
  accessToken: string;
}

const WAVEFORM_BAR_COUNT = 32;

function wsUrlFor(apiUrl: string, assistantId: string, voiceSessionId: string): string {
  const wsProtocol = apiUrl.startsWith("https://") ? "wss://" : "ws://";
  const httpStripped = apiUrl.replace(/^https?:\/\//, "");
  return `${wsProtocol}${httpStripped}/public/assistants/${assistantId}/voice-sessions/${voiceSessionId}/audio`;
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

  const waveformRow = document.createElement("div");
  waveformRow.className = "waveform-row";
  const waveformCanvas = document.createElement("canvas");
  waveformCanvas.className = "waveform";
  waveformCanvas.width = 300;
  waveformCanvas.height = 32;
  waveformRow.appendChild(waveformCanvas);
  panel.appendChild(waveformRow);
  const waveformCtx = waveformCanvas.getContext("2d");
  const waveformLevels: number[] = new Array(WAVEFORM_BAR_COUNT).fill(0);
  // Canvas 2D fillStyle can't resolve a CSS custom property reference
  // the way a real DOM element's own style can -- var(--af-primary-
  // color) as a literal string is not a valid canvas color. Resolve
  // the REAL, current value once via getComputedStyle instead; by this
  // point launcher.ts has already called host.style.setProperty(...)
  // for it, so the real value is already active and inherited into
  // this shadow tree.
  const waveformColor =
    getComputedStyle(panel).getPropertyValue("--af-primary-color").trim() || "#4f46e5";

  const inputRow = document.createElement("div");
  inputRow.className = "input-row";
  const textarea = document.createElement("textarea");
  textarea.placeholder = "Send a message…";
  textarea.rows = 1;
  const micButton = document.createElement("button");
  micButton.type = "button";
  micButton.className = "mic-button";
  micButton.setAttribute("aria-label", "Start voice input");
  micButton.innerHTML =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">' +
    '<path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3z"/>' +
    '<path d="M19 11a1 1 0 1 0-2 0 5 5 0 0 1-10 0 1 1 0 1 0-2 0 7 7 0 0 0 6 6.92V20H9a1 1 0 1 0 0 2h6a1 1 0 1 0 0-2h-2v-2.08A7 7 0 0 0 19 11z"/>' +
    "</svg>";
  const sendButton = document.createElement("button");
  sendButton.type = "button";
  sendButton.textContent = "Send";
  inputRow.appendChild(textarea);
  inputRow.appendChild(micButton);
  inputRow.appendChild(sendButton);
  panel.appendChild(inputRow);

  let session: AnonymousSession | null = null;
  let messages: ChatMessage[] = [];
  let nextLocalId = 0;
  let sending = false;

  let voiceSession: VoiceSession | null = null;
  let voiceSessionId: string | null = null;
  let voiceState: "idle" | "connecting" | "recording" | "processing" = "idle";
  let audioChunks: ArrayBuffer[] = [];
  let playbackAudio: HTMLAudioElement | null = null;
  let playbackObjectUrl: string | null = null;

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
        // relies on. A real voice reply has no content_html at all
        // (the websocket's own {"type":"reply",...} carries only
        // plain text) and falls through to the same textContent path
        // a pending/streaming text message already uses.
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
    updateControlsDisabled();
  }

  function updateControlsDisabled(): void {
    const busy = sending || voiceState === "connecting" || voiceState === "processing";
    sendButton.disabled = busy;
    textarea.disabled = busy;
    micButton.disabled = busy;
  }

  async function ensureSession(): Promise<AnonymousSession> {
    if (session) {
      return session;
    }
    const conversation = await createAnonymousConversation(config.apiUrl, config.assistantId);
    session = {
      conversationId: conversation.conversation_id,
      accessToken: conversation.access_token,
    };
    return session;
  }

  function drawWaveform(): void {
    if (!waveformCtx) {
      return;
    }
    const { width, height } = waveformCanvas;
    waveformCtx.clearRect(0, 0, width, height);
    waveformCtx.fillStyle = waveformColor;
    const barWidth = width / WAVEFORM_BAR_COUNT;
    waveformLevels.forEach((level, index) => {
      const barHeight = Math.max(2, level * height);
      const x = index * barWidth;
      const y = (height - barHeight) / 2;
      waveformCtx.fillRect(x + 1, y, Math.max(1, barWidth - 2), barHeight);
    });
  }

  function pushWaveformLevel(level: number): void {
    waveformLevels.shift();
    waveformLevels.push(level);
    drawWaveform();
  }

  function resetWaveform(): void {
    waveformLevels.fill(0);
    drawWaveform();
  }

  function stopPlayback(): void {
    if (playbackAudio) {
      playbackAudio.pause();
      playbackAudio.currentTime = 0;
    }
    if (playbackObjectUrl) {
      URL.revokeObjectURL(playbackObjectUrl);
      playbackObjectUrl = null;
    }
    audioChunks = [];
  }

  function appendMessage(
    role: "user" | "assistant",
    content: string,
    citations?: CitationRead[],
  ): void {
    messages = [...messages, { id: `local-${nextLocalId++}`, role, content, citations }];
    renderMessages();
  }

  async function startVoiceTurn(): Promise<void> {
    stopPlayback();
    voiceState = "connecting";
    micButton.classList.add("processing");
    updateControlsDisabled();
    try {
      const activeSession = await ensureSession();
      if (voiceSession === null) {
        const info = await startVoiceSession(
          config.apiUrl,
          config.assistantId,
          activeSession.conversationId,
          activeSession.accessToken,
        );
        voiceSessionId = info.id;
        const wsUrl = wsUrlFor(config.apiUrl, config.assistantId, info.id);
        voiceSession = new VoiceSession(wsUrl, activeSession.accessToken, {
          onLevel: pushWaveformLevel,
          onTranscript: (text) => appendMessage("user", text),
          onReply: (text, citations) => appendMessage("assistant", text, citations),
          onAudioChunk: (chunk) => audioChunks.push(chunk),
          onSynthesisDone: (contentType) => {
            if (audioChunks.length === 0) {
              return;
            }
            const blob = new Blob(audioChunks, { type: contentType });
            playbackObjectUrl = URL.createObjectURL(blob);
            audioChunks = [];
            playbackAudio ??= new Audio();
            playbackAudio.src = playbackObjectUrl;
            void playbackAudio.play().catch(() => {
              // A real, honest no-op -- autoplay can be blocked by the
              // host page's own browser policy; the widget still works,
              // the reply is already visible as a real text bubble.
            });
          },
          onInterrupted: stopPlayback,
          onError: (message) => appendMessage("assistant", message),
          onClose: () => {
            voiceSession = null;
            voiceSessionId = null;
            voiceState = "idle";
            micButton.classList.remove("recording", "processing");
            waveformRow.classList.remove("active");
            resetWaveform();
            updateControlsDisabled();
          },
        });
        await voiceSession.connect();
      } else {
        voiceSession.interrupt();
      }
      voiceState = "recording";
      micButton.classList.remove("processing");
      micButton.classList.add("recording");
      micButton.setAttribute("aria-label", "Stop recording");
      waveformRow.classList.add("active");
      updateControlsDisabled();
      await voiceSession.startRecording();
    } catch (error) {
      console.error(error);
      voiceState = "idle";
      micButton.classList.remove("recording", "processing");
      micButton.setAttribute("aria-label", "Start voice input");
      waveformRow.classList.remove("active");
      updateControlsDisabled();
    }
  }

  function stopVoiceTurn(): void {
    voiceSession?.stopRecording();
    voiceState = "processing";
    micButton.classList.remove("recording");
    micButton.classList.add("processing");
    micButton.setAttribute("aria-label", "Start voice input");
    waveformRow.classList.remove("active");
    resetWaveform();
    updateControlsDisabled();
  }

  micButton.addEventListener("click", () => {
    if (voiceState === "recording") {
      stopVoiceTurn();
    } else if (voiceState === "idle") {
      void startVoiceTurn();
    }
  });

  window.addEventListener("beforeunload", () => {
    if (voiceSession && voiceSessionId && session) {
      endVoiceSession(
        config.apiUrl,
        config.assistantId,
        session.conversationId,
        voiceSessionId,
        session.accessToken,
      );
    }
  });

  async function handleSend(): Promise<void> {
    const content = textarea.value.trim();
    if (!content || sending) {
      return;
    }
    textarea.value = "";
    setSending(true);

    let activeSession: AnonymousSession;
    try {
      activeSession = await ensureSession();
    } catch (error) {
      console.error(error);
      setSending(false);
      return;
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
      activeSession.conversationId,
      activeSession.accessToken,
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
