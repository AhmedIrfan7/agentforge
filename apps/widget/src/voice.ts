// Real browser voice I/O (roadmap step 229). Microphone capture via
// MediaRecorder, a real-time level signal for the waveform indicator
// via a Web Audio AnalyserNode, and the real websocket protocol
// (221-228) that already exists server-side -- this module is purely
// the CLIENT half of infrastructure this project already built and
// tested end to end. No new dependency: MediaRecorder/AudioContext/
// WebSocket are all real, standard browser APIs, matching this app's
// own "minimal deps" constraint (201).
//
// One voice session, one open connection for the whole widget's own
// lifetime once started -- matches VoiceSession's own server-side
// design (219), "one session, potentially many real turns," not a new
// connection per recording. `stopRecording` sends a real `end_turn`
// control message itself (a deliberate "push to talk" UX: a user
// clicking stop wants an immediate answer, not to wait out the
// server's own silence-timeout fallback) -- listens for MediaRecorder's
// own `stop` event before sending it, since `.stop()` flushes one
// final `dataavailable` event BEFORE `stop` fires, so the last real
// audio chunk is already queued by the time `end_turn` goes out.
//
// `mime_type` is a fixed `"audio/webm"` -- the one format every real
// Chromium/Firefox `MediaRecorder` supports without an explicit
// `mimeType` codec string breaking (Safari's own real gap, needing
// `"audio/mp4"`, is a known, honest limitation not handled here; no
// roadmap step through 232 asks for cross-browser codec negotiation).

import type { CitationRead } from "@agentforge/shared";

export interface VoiceCallbacks {
  onLevel: (level: number) => void;
  onTranscript: (text: string, language: string | null) => void;
  onReply: (text: string, citations: CitationRead[]) => void;
  onAudioChunk: (chunk: ArrayBuffer) => void;
  onSynthesisDone: (contentType: string) => void;
  onInterrupted: () => void;
  onError: (message: string) => void;
  onClose: () => void;
}

const MIME_TYPE = "audio/webm";
const RECORDER_TIMESLICE_MS = 250;

export interface VoiceSessionInfo {
  id: string;
  conversationId: string;
}

export async function startVoiceSession(
  apiUrl: string,
  assistantId: string,
  conversationId: string,
  accessToken: string,
): Promise<VoiceSessionInfo> {
  const response = await fetch(
    `${apiUrl}/public/assistants/${assistantId}/conversations/${conversationId}/voice-sessions`,
    { method: "POST", headers: { Authorization: `Bearer ${accessToken}` } },
  );
  if (!response.ok) {
    throw new Error(`Failed to start voice session (status ${response.status}).`);
  }
  const body = (await response.json()) as { id: string; conversation_id: string };
  return { id: body.id, conversationId: body.conversation_id };
}

export function endVoiceSession(
  apiUrl: string,
  assistantId: string,
  conversationId: string,
  voiceSessionId: string,
  accessToken: string,
): void {
  // Best-effort, not awaited -- real callers are UI teardown paths
  // (widget close, page unload) that can't wait on a network round
  // trip. `keepalive: true` is what actually lets this real request
  // complete even after the page starts unloading, the same real
  // mechanism `navigator.sendBeacon` relies on -- used here instead of
  // sendBeacon itself specifically because sendBeacon can't carry a
  // real Authorization header, and this endpoint's whole auth model is
  // the anonymous session Bearer token, not a cookie.
  void fetch(
    `${apiUrl}/public/assistants/${assistantId}/conversations/${conversationId}` +
      `/voice-sessions/${voiceSessionId}/end`,
    { method: "POST", headers: { Authorization: `Bearer ${accessToken}` }, keepalive: true },
  ).catch(() => {
    // Real, honest no-op -- there is no UI left to report this to once
    // the widget is tearing down.
  });
}

export class VoiceSession {
  private socket: WebSocket | null = null;
  private mediaRecorder: MediaRecorder | null = null;
  private mediaStream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private levelLoopHandle: number | null = null;
  private ready = false;

  constructor(
    private readonly wsUrl: string,
    private readonly accessToken: string,
    private readonly callbacks: VoiceCallbacks,
  ) {}

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(this.wsUrl);
      socket.binaryType = "arraybuffer";
      this.socket = socket;

      socket.addEventListener("open", () => {
        socket.send(JSON.stringify({ token: this.accessToken, mime_type: MIME_TYPE }));
      });

      socket.addEventListener("message", (event: MessageEvent<unknown>) => {
        if (typeof event.data !== "string") {
          this.callbacks.onAudioChunk(event.data as ArrayBuffer);
          return;
        }
        this.handleTextMessage(event.data, resolve);
      });

      socket.addEventListener("error", () => {
        reject(new Error("Voice connection failed."));
      });

      socket.addEventListener("close", () => {
        this.ready = false;
        this.callbacks.onClose();
      });
    });
  }

  private handleTextMessage(raw: string, onReady: () => void): void {
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return;
    }
    switch (message.type) {
      case "ready":
        this.ready = true;
        onReady();
        break;
      case "transcript":
        this.callbacks.onTranscript(
          message.text as string,
          (message.language as string | null | undefined) ?? null,
        );
        break;
      case "reply":
        this.callbacks.onReply(
          message.text as string,
          (message.citations as CitationRead[] | undefined) ?? [],
        );
        break;
      case "synthesis_done":
        this.callbacks.onSynthesisDone(message.content_type as string);
        break;
      case "interrupted":
        this.callbacks.onInterrupted();
        break;
      case "error":
        this.callbacks.onError(message.message as string);
        break;
    }
  }

  async startRecording(): Promise<void> {
    if (!this.ready || this.socket === null) {
      throw new Error("Voice session is not connected yet.");
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.mediaStream = stream;
    this.startLevelLoop(stream);

    const recorder = new MediaRecorder(stream, { mimeType: MIME_TYPE });
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size === 0 || this.socket?.readyState !== WebSocket.OPEN) {
        return;
      }
      const socket = this.socket;
      void event.data.arrayBuffer().then((buffer) => {
        socket.send(buffer);
      });
    });
    recorder.addEventListener(
      "stop",
      () => {
        if (this.socket?.readyState === WebSocket.OPEN) {
          this.socket.send(JSON.stringify({ type: "end_turn" }));
        }
      },
      { once: true },
    );
    recorder.start(RECORDER_TIMESLICE_MS);
    this.mediaRecorder = recorder;
  }

  stopRecording(): void {
    if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
      this.mediaRecorder.stop();
    }
    this.mediaRecorder = null;
    this.mediaStream?.getTracks().forEach((track) => track.stop());
    this.mediaStream = null;
    this.stopLevelLoop();
    void this.audioContext?.close();
    this.audioContext = null;
    this.analyser = null;
  }

  interrupt(): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: "interrupt" }));
    }
  }

  close(): void {
    this.stopRecording();
    this.socket?.close();
    this.socket = null;
  }

  private startLevelLoop(stream: MediaStream): void {
    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    this.audioContext = audioContext;
    this.analyser = analyser;

    const data = new Uint8Array(analyser.frequencyBinCount);
    const tick = (): void => {
      analyser.getByteTimeDomainData(data);
      let sumSquares = 0;
      for (const value of data) {
        const normalized = (value - 128) / 128;
        sumSquares += normalized * normalized;
      }
      const rms = Math.sqrt(sumSquares / data.length);
      this.callbacks.onLevel(Math.min(1, rms * 4));
      this.levelLoopHandle = requestAnimationFrame(tick);
    };
    this.levelLoopHandle = requestAnimationFrame(tick);
  }

  private stopLevelLoop(): void {
    if (this.levelLoopHandle !== null) {
      cancelAnimationFrame(this.levelLoopHandle);
      this.levelLoopHandle = null;
    }
  }
}
