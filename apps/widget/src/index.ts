// Embeddable chat/voice widget entry point (roadmap step 201).
//
// Deliberately minimal — this scaffold step proves the TypeScript
// toolchain compiles and lints cleanly for a real, framework-free
// browser bundle. The widget's own real behavior (config loading from
// the embedding script tag, launcher button, chat window UI) arrives
// incrementally at steps 202-206, matching every other app in this
// monorepo's own "scaffold first, real logic layered in by later
// steps" precedent (apps/api's own first step was just a `/health`
// endpoint; apps/web's own first step was the unmodified `create-
// next-app` default).

export const WIDGET_VERSION = "0.1.0";
