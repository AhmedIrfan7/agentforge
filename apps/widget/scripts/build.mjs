// Widget build script (roadmap step 210). A plain Node script rather
// than esbuild's own CLI invocation directly in package.json's "build"
// -- injecting the real package.json version as a build-time constant
// (__WIDGET_VERSION__, read by src/index.ts) needs shell-independent
// access to that value, and $npm_package_version's substitution syntax
// differs between the POSIX shell this monorepo's CI uses and the
// Windows shell this project is also developed on locally. Reading
// package.json directly via Node's own fs module sidesteps that
// entirely, instead of adding a dependency like cross-env just for one
// value -- this app's own "minimal deps" constraint (201) stays real.

import { readFileSync } from "node:fs";
import { build } from "esbuild";

const packageJson = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf-8"));

await build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  minify: true,
  format: "iife",
  globalName: "AgentForgeWidget",
  outfile: "dist/widget.js",
  define: {
    __WIDGET_VERSION__: JSON.stringify(packageJson.version),
  },
});
