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
//
// As of step 206, also resolves theme customization -- AGENTS.md's own
// "EMBEDDABLE WIDGET" section names "colors/fonts/logo/position" among
// its customization examples, and "support future configuration
// through dashboard controls instead of code changes" (the embeddable
// chatbot section) -- all four are real `data-*` attributes here,
// config-driven rather than something a customer edits in CSS/JS.
//
// As of step 211, `colorScheme` adds real dark/light mode. Three
// values, not two: "auto" (the default -- follows the visitor's own
// OS/browser `prefers-color-scheme`, the same real, standard mechanism
// this project's own Artifact-authoring conventions already use
// elsewhere) alongside explicit "light"/"dark" overrides for a
// customer who wants the widget to always match their own site's
// fixed theme regardless of the visitor's system setting.

export interface WidgetTheme {
  primaryColor: string;
  fontFamily: string;
  logoUrl: string | null;
  position: "bottom-right" | "bottom-left";
  colorScheme: "auto" | "light" | "dark";
}

export interface WidgetConfig {
  assistantId: string;
  apiUrl: string;
  theme: WidgetTheme;
}

// Same "default to localhost for local dev, a real deployment
// overrides it" shape apps/web's own lib/api.ts already established
// for NEXT_PUBLIC_API_URL -- no production domain exists yet
// (Milestone 11's own infrastructure/deployment work), so defaulting
// to anything else here would be a guess, not a real default.
const DEFAULT_API_URL = "http://localhost:8000";

const DEFAULT_THEME: WidgetTheme = {
  primaryColor: "#4f46e5",
  fontFamily: "system-ui, sans-serif",
  logoUrl: null,
  position: "bottom-right",
  colorScheme: "auto",
};

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

function resolvePosition(value: string | undefined): WidgetTheme["position"] {
  return value === "bottom-left" ? "bottom-left" : DEFAULT_THEME.position;
}

function resolveColorScheme(value: string | undefined): WidgetTheme["colorScheme"] {
  return value === "light" || value === "dark" ? value : DEFAULT_THEME.colorScheme;
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
    theme: {
      primaryColor: script.dataset.primaryColor ?? DEFAULT_THEME.primaryColor,
      fontFamily: script.dataset.fontFamily ?? DEFAULT_THEME.fontFamily,
      logoUrl: script.dataset.logoUrl ?? DEFAULT_THEME.logoUrl,
      position: resolvePosition(script.dataset.position),
      colorScheme: resolveColorScheme(script.dataset.colorScheme),
    },
  };
}
