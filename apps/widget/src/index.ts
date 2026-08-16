// Embeddable chat/voice widget entry point (roadmap step 201).
//
// As of step 203, resolves its own config from the embed <script>
// tag at module-evaluation time -- this file IS the bundle a
// customer's page loads, so that's the one real moment a widget
// script naturally "starts" (no explicit init() call the embedding
// site has to remember to make, matching AGENTS.md's own "the embed
// process should require minimal effort" line). A missing/invalid
// config fails loudly to the console rather than throwing an
// uncaught error into the host page -- a misconfigured embed
// shouldn't be able to break the customer's own site around it.
//
// As of step 204, a resolved config mounts the real launcher button
// (`launcher.ts`) -- gated behind a successful config load, so a
// misconfigured embed shows nothing rather than a broken, non-
// functional button. Chat window content is step 205's own job.
//
// As of step 210, WIDGET_VERSION comes from a real build-time constant
// (`scripts/build.mjs` injects it from package.json's own "version"
// field via esbuild's `define`) rather than a second, hand-duplicated
// literal here that could silently drift from the real published
// version -- directly relevant now that CDN deploys (209) publish
// real, permanently pinned per-version URLs a customer's embed can
// target.

import { loadWidgetConfig, type WidgetConfig } from "./config";
import { mountLauncher } from "./launcher";

declare const __WIDGET_VERSION__: string;

export const WIDGET_VERSION = __WIDGET_VERSION__;

let config: WidgetConfig | null = null;
try {
  config = loadWidgetConfig();
} catch (error) {
  console.error(error);
}

if (config) {
  mountLauncher(config);
}

export function getConfig(): WidgetConfig | null {
  return config;
}
