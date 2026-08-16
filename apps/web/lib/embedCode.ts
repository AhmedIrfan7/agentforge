// Embed-code generator (roadmap step 207, AGENTS.md's own "EMBEDDABLE
// WIDGET"/"EMBEDDABLE CHATBOT" sections: "customer copies one script,
// pastes it into their website, done").
//
// No dashboard exists in apps/web yet to call this from -- Milestone
// 9's own "Scaffold dashboard shell (auth-gated layout, nav)" is step
// 233, well after this one, the same "no dashboard auth UI yet"
// constraint steps 194/196/197/203 already hit for the chat surface.
// Unlike those steps, an embed-code generator has no honest anonymous-
// flow equivalent to fall back on -- generating a snippet is an admin
// action tied to a specific, owned assistant, not something a pre-auth
// visitor should ever be able to do. This is the same situation
// memory_retrieval.py (166) was in before step 193 gave it a real
// caller: real, tested logic with no UI wired to it yet, honestly
// acknowledged rather than either skipped or faked behind a premature
// dashboard page. Step 233's real dashboard is this function's real
// future caller.
//
// `widgetScriptUrl` is a required parameter, not a hardcoded default --
// there is no deployed widget CDN URL yet either (step 209, also
// later); a real caller supplies whatever's actually true for its own
// environment rather than this function guessing a domain.
//
// Attribute names match apps/widget/src/config.ts's own real
// `loadWidgetConfig` verbatim -- this is the one place generating text
// FOR that consumer, so drifting from its exact attribute names would
// silently produce a broken embed snippet.
//
// Real gap found+fixed while writing docs/embedding.md (215): this
// module predates config.ts's own `colorScheme` addition (211) and had
// silently never been updated to emit `data-color-scheme` -- caught
// while cross-checking this file's attribute list against config.ts's
// real, current one before documenting it as a customer-facing option.

export interface EmbedTheme {
  primaryColor?: string;
  fontFamily?: string;
  logoUrl?: string;
  position?: "bottom-right" | "bottom-left";
  colorScheme?: "auto" | "light" | "dark";
}

export interface EmbedCodeOptions {
  assistantId: string;
  widgetScriptUrl: string;
  apiUrl?: string;
  theme?: EmbedTheme;
}

function escapeAttribute(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function attribute(name: string, value: string | undefined): string | null {
  return value ? `${name}="${escapeAttribute(value)}"` : null;
}

export function generateEmbedCode(options: EmbedCodeOptions): string {
  const attributes = [
    attribute("data-assistant-id", options.assistantId),
    attribute("data-api-url", options.apiUrl),
    attribute("data-primary-color", options.theme?.primaryColor),
    attribute("data-font-family", options.theme?.fontFamily),
    attribute("data-logo-url", options.theme?.logoUrl),
    attribute("data-position", options.theme?.position),
    attribute("data-color-scheme", options.theme?.colorScheme),
    attribute("src", options.widgetScriptUrl),
  ].filter((value): value is string => value !== null);

  return `<script ${attributes.join(" ")}></script>`;
}
