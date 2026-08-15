// Widget config loader (roadmap step 203, AGENTS.md's own "EMBEDDABLE
// CHATBOT" section: "the widget should automatically connect to the
// correct organization, assistant..."). `data-assistant-id` is the
// one identifier a real embed script tag carries -- the exact
// attribute name apps/api's own public router already anticipated
// (routers/public_conversation.py's own docstring: "the one identifier
// a real embeddable widget script tag can carry (`<script data-
// assistant-id="...">`...)"). No org/workspace/knowledge-base
// attributes: assistant_id alone already resolves those server-side
// (repositories/assistant.py:get_public_assistant_by_id, step 192),
// so asking the embedding site to also know and supply them would be
// redundant, error-prone configuration this platform's own backend
// design already made unnecessary.

export interface WidgetConfig {
  assistantId: string;
  apiUrl: string;
}

// Same "default to localhost for local dev, a real deployment
// overrides it" shape apps/web's own lib/api.ts already established
// for NEXT_PUBLIC_API_URL -- no production domain exists yet
// (Milestone 11's own infrastructure/deployment work), so defaulting
// to anything else here would be a guess, not a real default.
const DEFAULT_API_URL = "http://localhost:8000";

function findScriptTag(): HTMLScriptElement | null {
  // document.currentScript is the reliable case: it's set for the
  // duration of a synchronously-executing <script>, which is how a
  // real embed snippet is used. It's null for async/deferred scripts
  // or once the script has finished running -- falling back to the
  // one real element this whole platform requires to carry the embed
  // config (data-assistant-id) is the honest recovery, not a fragile
  // assumption about script-loading timing.
  if (document.currentScript instanceof HTMLScriptElement) {
    return document.currentScript;
  }
  return document.querySelector<HTMLScriptElement>("script[data-assistant-id]");
}

export function loadWidgetConfig(): WidgetConfig {
  const script = findScriptTag();
  const assistantId = script?.dataset.assistantId;
  if (!assistantId) {
    throw new Error(
      "AgentForge widget: the embed <script> tag is missing its required data-assistant-id attribute.",
    );
  }
  return {
    assistantId,
    apiUrl: script.dataset.apiUrl ?? DEFAULT_API_URL,
  };
}
