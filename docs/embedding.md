# Embedding the AgentForge widget

A real chat launcher and window your customer support visitors can talk to, added to any site with one `<script>` tag. This is a practical how-to guide for the person pasting that tag into a page. For how the widget is built internally, see [`docs/ARCHITECTURE.md`](ARCHITECTURE.md#embeddable-widget).

## Quick start

Paste this before your page's closing `</body>` tag:

```html
<script
  src="https://ahmedirfan7.github.io/agentforge/widget.js"
  data-assistant-id="YOUR_ASSISTANT_ID"
></script>
```

That's it. A launcher button appears in the bottom-right corner; clicking it opens a real chat window backed by that assistant's knowledge base.

## Getting your assistant ID

Create the assistant through the dashboard (an organization's knowledge base → Assistants → create), open it, and set **Public** on — this is a real, deliberate security boundary: an assistant stays private (`is_public: false` by default) until an org admin opts it in. **Only public assistants are embeddable.**

Once it's public and saved, the assistant's own page has a **Get embed code** panel with the exact snippet below, pre-filled with the real assistant id, ready to copy. `apps/web/lib/embedCode.ts:generateEmbedCode` is what builds it (tested, `e2e/embedCode.spec.ts`).

## Configuration reference

All configuration is real `data-*` attributes on the embed `<script>` tag — no separate config file, no JS API to call.

| Attribute | Required | Default | Description |
| --- | --- | --- | --- |
| `data-assistant-id` | Yes | — | The public assistant to connect to. The one identifier the widget needs — org/workspace/knowledge base are all resolved server-side from this. |
| `data-api-url` | No | `http://localhost:8000` | Your AgentForge API's base URL. Real production deployments must set this explicitly — the default is a local-dev convenience, not a real domain. |
| `data-primary-color` | No | `#4f46e5` | Brand color — launcher button, user message bubbles, send button. Hover state is automatically derived (`brightness(90%)`), not separately configurable. |
| `data-font-family` | No | `system-ui, sans-serif` | Any valid CSS `font-family` value. |
| `data-logo-url` | No | none (default chat-bubble icon) | Replaces the launcher's **closed**-state icon only — the close (X) icon always shows once open, regardless of branding. An unreachable/broken URL falls back to the default icon automatically. |
| `data-position` | No | `bottom-right` | `bottom-right` or `bottom-left`. |
| `data-color-scheme` | No | `auto` | `auto` (follows the visitor's own OS/browser `prefers-color-scheme`), `light`, or `dark` — an explicit value always wins over the visitor's system setting. Only structural surfaces (panel/bubbles/borders) change between light and dark; your `data-primary-color` stays identical in both. |

### Example: a fully customized embed

```html
<script
  src="https://ahmedirfan7.github.io/agentforge/widget.js"
  data-assistant-id="a1b2c3d4-..."
  data-api-url="https://api.yourcompany.com"
  data-primary-color="#16a34a"
  data-font-family="Georgia, serif"
  data-logo-url="https://yourcompany.com/logo.png"
  data-position="bottom-left"
  data-color-scheme="dark"
></script>
```

## Restricting which domains can embed your assistant

Org admins/owners can set an allow-list of domains via `PATCH /organizations/{id}/security-settings` (`allowed_domains`, empty by default — no restriction). A domain matches exactly or as a subdomain (`example.com` also allows `chat.example.com`).

**Honest limitation:** this is enforced at the application layer against the request's `Origin` header, not through browser CORS policy — a request with no `Origin` header at all (e.g. a server-side or `curl` call, not a real browser page load) is allowed through regardless of the restriction. This constrains *browser-based embedding* specifically; it is not a general API firewall.

## Mobile behavior

Below a 480px-wide viewport, the chat window switches to a real full-screen layout automatically (no configuration needed) — the same pattern products like Intercom/Drift use, since the widget's normal fixed-size corner panel would overflow or leave awkward margins on a real phone screen.

## Pinning a specific widget version

`https://ahmedirfan7.github.io/agentforge/widget.js` always serves the latest release and updates automatically. If you'd rather pin an exact version (e.g. to control exactly when you pick up a change), every published version stays permanently available at `https://ahmedirfan7.github.io/agentforge/v{version}/widget.js` (e.g. `v0.2.0/widget.js`) — see [`versions.json`](https://ahmedirfan7.github.io/agentforge/versions.json) for the full list of published versions and each one's real [Subresource Integrity](https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity) hash.

**Recommended for a pinned version**: add the real `integrity` attribute from `versions.json`. GitHub Pages (this widget's CDN) has no configuration surface for its own cache headers — every file gets a fixed, short `Cache-Control: max-age=600` regardless of whether it can ever change, confirmed live against the real deployed site. A pinned version's content never changes once published, so a real `integrity` hash lets the browser itself cache and skip re-fetching it far more aggressively than the origin's own headers alone allow — and it's a real security hardening on top of that (the browser refuses to execute the script at all if the fetched bytes ever don't match):

```html
<script
  src="https://ahmedirfan7.github.io/agentforge/v0.2.0/widget.js"
  integrity="sha384-..."
  crossorigin="anonymous"
  data-assistant-id="YOUR_ASSISTANT_ID"
></script>
```

`crossorigin="anonymous"` is required alongside `integrity` — browsers refuse to apply SRI to a cross-origin script fetched without it. The root `widget.js` (auto-updating, no version pin) can't use `integrity` at all, by definition — the whole point of SRI is verifying the fetched bytes never change, which directly conflicts with "always serves the latest release."

## What the widget does not do yet

Honest, tracked gaps — not silently worked around:

- **No custom greeting message, animation customization, i18n/language selection, or arbitrary custom CSS** — AGENTS.md's own customization list names all of these; only theme (color/font/logo/position/color-scheme) is implemented so far.

## Where this is implemented

- `apps/widget/src/config.ts` — reads every `data-*` attribute above.
- `apps/widget/src/launcher.ts` — Shadow DOM mount, theming, mobile layout.
- `apps/widget/src/chat-window.ts` — message list, streaming, citations.
- `apps/web/lib/embedCode.ts` — generates the snippet (not yet wired to a UI).
- `apps/api/routers/public_conversation.py` / `apps/api/routers/security_settings.py` — the backend endpoints above.
