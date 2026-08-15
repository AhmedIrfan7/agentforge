// Cross-app TypeScript contracts shared between apps/web and apps/widget.
//
// As of roadmap step 205, this is real: both apps' anonymous-chat
// wire-format types and API-calling logic live here (types.ts/api.ts),
// promoted out of apps/web once apps/widget became a second real
// consumer. Once apps/api grows an OpenAPI schema (a future
// milestone), prefer generating types from it here over hand-
// maintaining types.ts's own mirrors — see docs/ARCHITECTURE.md.

export const SHARED_PACKAGE_VERSION = "0.1.0";

export * from "./api";
export * from "./types";
