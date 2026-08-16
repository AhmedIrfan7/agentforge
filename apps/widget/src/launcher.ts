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
//
// As of step 206, color/font are real CSS custom properties
// (`--af-primary-color`/`--af-font-family`), given their real,
// per-embed values via `host.style.setProperty()` (a safe way to set
// an arbitrary customer-supplied value -- unlike concatenating it into
// a <style> textContent string, the CSSOM property-value API can't be
// used to break out into new CSS rules or markup). `filter:
// brightness()` derives a real hover shade from whatever color was
// supplied, rather than requiring a second "hover color" the customer
// would also have to configure. Position (bottom-right/bottom-left)
// toggles which CSS rule set applies via a class, since which
// property (`left` vs `right`) is even in play can't be expressed as
// a single custom property's value. A custom logo replaces the
// default chat-bubble icon in the CLOSED state only -- the close (X)
// icon always shows once open, regardless of branding, so "click to
// close" stays unambiguous.
//
// As of step 211, "structural" colors (panel/bubble/border surfaces --
// never the customer's own brand `--af-primary-color`, which stays
// identical in both modes) are real CSS custom properties with two
// palettes: a light one on `:host` as the default, and a dark one
// applied two ways -- inside `@media (prefers-color-scheme: dark)`
// (real, automatic, follows the visitor's own OS/browser setting,
// guarded so an explicit `data-af-theme="light"` override still wins),
// and again on `:host([data-af-theme="dark"])` (an explicit override
// always applies regardless of system preference). `mountLauncher`
// only ever sets the `data-af-theme` attribute for an EXPLICIT
// "light"/"dark" config value -- leaving it unset for "auto" (the
// default) is what lets the media query alone decide.
//
// Real bug found live, not by inspection: the functional
// `:host(<compound-selector>)` form is required to add a condition ON
// the host element itself -- a bare `:host:not([data-af-theme="light"])`
// chain parses without error but never actually matches (confirmed with
// a real isolated probe stylesheet, comparing it side-by-side against
// the working `:host(:not(...))` form). The dark-mode rule below uses
// the functional form specifically because of this.
//
// As of step 212, the panel switches to a real full-screen layout
// under a mobile-width viewport (`max-width: 480px`, a common phone
// breakpoint -- the fixed 360px-wide corner panel would either
// overflow a real phone viewport or leave awkward margins on one).
// Full-screen-on-mobile is also the standard real pattern this class
// of product already uses (Intercom, Drift, etc.), not just an
// overflow fix. The launcher button stays visible and in its normal
// corner position even while the panel is full-screen -- it's still
// the real close affordance, same toggle behavior as desktop.

import { renderChatWindow } from "./chat-window";
import type { WidgetConfig } from "./config";

const CHAT_ICON =
  '<svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor" aria-hidden="true"><path d="M4 4h16v12H7l-3 3V4z"/></svg>';
const CLOSE_ICON =
  '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';

const STYLES = `
  :host {
    all: initial;
    --af-primary-color: #4f46e5;
    --af-font-family: system-ui, sans-serif;
    --af-surface: #ffffff;
    --af-surface-text: #111827;
    --af-assistant-bubble-bg: #f3f4f6;
    --af-assistant-bubble-text: #111827;
    --af-border: #e5e7eb;
    --af-citation-bg: #e5e7eb;
    --af-citation-text: #374151;
    --af-input-border: #d1d5db;
  }
  @media (prefers-color-scheme: dark) {
    :host(:not([data-af-theme="light"])) {
      --af-surface: #1f2937;
      --af-surface-text: #f3f4f6;
      --af-assistant-bubble-bg: #374151;
      --af-assistant-bubble-text: #f3f4f6;
      --af-border: #374151;
      --af-citation-bg: #374151;
      --af-citation-text: #d1d5db;
      --af-input-border: #4b5563;
    }
  }
  :host([data-af-theme="dark"]) {
    --af-surface: #1f2937;
    --af-surface-text: #f3f4f6;
    --af-assistant-bubble-bg: #374151;
    --af-assistant-bubble-text: #f3f4f6;
    --af-border: #374151;
    --af-citation-bg: #374151;
    --af-citation-text: #d1d5db;
    --af-input-border: #4b5563;
  }
  .launcher {
    position: fixed;
    bottom: 20px;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    border: none;
    background: var(--af-primary-color);
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    z-index: 2147483647;
    font-family: var(--af-font-family);
    overflow: hidden;
  }
  .launcher:hover { filter: brightness(90%); }
  .launcher img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .panel {
    position: fixed;
    bottom: 88px;
    width: 360px;
    height: 480px;
    background: var(--af-surface);
    color: var(--af-surface-text);
    border-radius: 12px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
    z-index: 2147483646;
    display: none;
    overflow: hidden;
    font-family: var(--af-font-family);
  }
  .position-right { right: 20px; left: auto; }
  .position-left { left: 20px; right: auto; }

  @media (max-width: 480px) {
    .panel {
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      width: 100%;
      height: 100%;
      border-radius: 0;
    }
  }
`;

export function mountLauncher(config: WidgetConfig): void {
  const host = document.createElement("div");
  host.id = "agentforge-widget-root";
  host.style.setProperty("--af-primary-color", config.theme.primaryColor);
  host.style.setProperty("--af-font-family", config.theme.fontFamily);
  if (config.theme.colorScheme !== "auto") {
    host.dataset.afTheme = config.theme.colorScheme;
  }
  document.body.appendChild(host);

  const shadow = host.attachShadow({ mode: "open" });

  const style = document.createElement("style");
  style.textContent = STYLES;
  shadow.appendChild(style);

  const positionClass = `position-${config.theme.position === "bottom-left" ? "left" : "right"}`;

  const panel = document.createElement("div");
  panel.className = `panel ${positionClass}`;
  shadow.appendChild(panel);
  renderChatWindow(shadow, panel, config);

  const button = document.createElement("button");
  button.type = "button";
  button.className = `launcher ${positionClass}`;
  button.setAttribute("aria-label", "Open chat");
  setClosedIcon(button, config.theme.logoUrl);
  shadow.appendChild(button);

  let isOpen = false;
  button.addEventListener("click", () => {
    isOpen = !isOpen;
    panel.classList.toggle("open", isOpen);
    if (isOpen) {
      button.innerHTML = CLOSE_ICON;
    } else {
      setClosedIcon(button, config.theme.logoUrl);
    }
    button.setAttribute("aria-label", isOpen ? "Close chat" : "Open chat");
  });
}

function setClosedIcon(button: HTMLButtonElement, logoUrl: string | null): void {
  if (!logoUrl) {
    button.innerHTML = CHAT_ICON;
    return;
  }
  const img = document.createElement("img");
  img.src = logoUrl;
  img.alt = "";
  // A broken/unreachable logo URL shouldn't leave the launcher blank --
  // fall back to the default icon the same way a missing config value
  // already does elsewhere in this app.
  img.addEventListener("error", () => {
    button.innerHTML = CHAT_ICON;
  });
  button.innerHTML = "";
  button.appendChild(img);
}
