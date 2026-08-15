// Launcher button UI (roadmap step 204). Mounted inside a real Shadow
// DOM root -- the standard, dependency-free technique for genuine CSS
// isolation from an arbitrary host page's own styles. AGENTS.md's own
// "support embedding into: business websites, web applications,
// documentation portals, customer portals, internal dashboards" spans
// genuinely disparate host environments; a widget whose button
// silently inherits a host page's `button { ... }` reset (or bleeds
// its own styles onto the host page) isn't actually "lightweight...
// secure... easy to update" in practice. No CSS-in-JS library or
// bundler CSS pipeline needed for this -- a plain <style> tag inside
// the shadow root is real, standard, and free, keeping this app's own
// "minimal deps" constraint (201) intact.
//
// Toggles a real open/closed state and swaps the icon accordingly.
// As of step 205, the panel's own content is rendered by
// chat-window.ts:renderChatWindow -- launcher.ts still owns the
// panel's shell (position/size/shadow/base visibility), chat-window.ts
// owns what "open" looks like internally (flex layout) and everything
// inside it.

import { renderChatWindow } from "./chat-window";
import type { WidgetConfig } from "./config";

const CHAT_ICON =
  '<svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor" aria-hidden="true"><path d="M4 4h16v12H7l-3 3V4z"/></svg>';
const CLOSE_ICON =
  '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';

const STYLES = `
  :host { all: initial; }
  .launcher {
    position: fixed;
    bottom: 20px;
    right: 20px;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    border: none;
    background: #4f46e5;
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    z-index: 2147483647;
    font-family: system-ui, sans-serif;
  }
  .launcher:hover { background: #4338ca; }
  .panel {
    position: fixed;
    bottom: 88px;
    right: 20px;
    width: 360px;
    height: 480px;
    background: white;
    border-radius: 12px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
    z-index: 2147483646;
    display: none;
    overflow: hidden;
  }
`;

export function mountLauncher(config: WidgetConfig): void {
  const host = document.createElement("div");
  host.id = "agentforge-widget-root";
  document.body.appendChild(host);

  const shadow = host.attachShadow({ mode: "open" });

  const style = document.createElement("style");
  style.textContent = STYLES;
  shadow.appendChild(style);

  const panel = document.createElement("div");
  panel.className = "panel";
  shadow.appendChild(panel);
  renderChatWindow(shadow, panel, config);

  const button = document.createElement("button");
  button.type = "button";
  button.className = "launcher";
  button.setAttribute("aria-label", "Open chat");
  button.innerHTML = CHAT_ICON;
  shadow.appendChild(button);

  let isOpen = false;
  button.addEventListener("click", () => {
    isOpen = !isOpen;
    panel.classList.toggle("open", isOpen);
    button.innerHTML = isOpen ? CLOSE_ICON : CHAT_ICON;
    button.setAttribute("aria-label", isOpen ? "Close chat" : "Open chat");
  });
}
