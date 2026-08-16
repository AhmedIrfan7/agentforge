// Assembles the GitHub Pages deploy artifact with real, permanent
// per-version URLs (roadmap step 210, "pinned script version").
//
// GitHub Pages deployments (widget-deploy.yml, step 209) fully REPLACE
// the site's content on every deploy -- there is no incremental
// "add-only" publish the way a git branch with keep_files or an S3
// bucket's own per-key writes would give. Left alone, a second deploy
// would silently delete every previously-published version's URL, the
// exact opposite of what "pinned" means. This fetches (by explicit,
// known URL -- Pages serves no directory listing to crawl) every
// version this deploy's own manifest (versions.json) already knows
// about, re-adds them to the new artifact unchanged, then adds this
// build's own version alongside them. `widget.js` at the root always
// points to the LATEST version (auto-update, the default a customer
// gets with no extra configuration); `v{version}/widget.js` is that
// exact version, permanent once published, for a customer who
// explicitly wants to pin against a future breaking change.

import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";

const PAGES_URL = "https://ahmedirfan7.github.io/agentforge";
const OUTPUT_DIR = "pages-root";

const packageJson = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf-8"));
const version = packageJson.version;

async function fetchText(url) {
  const response = await fetch(url);
  if (!response.ok) {
    return null;
  }
  return response.text();
}

async function main() {
  mkdirSync(OUTPUT_DIR, { recursive: true });

  const existingManifestText = await fetchText(`${PAGES_URL}/versions.json`);
  const versions = new Set(existingManifestText ? JSON.parse(existingManifestText) : []);

  for (const existingVersion of versions) {
    if (existingVersion === version) {
      continue;
    }
    const bundleText = await fetchText(`${PAGES_URL}/v${existingVersion}/widget.js`);
    if (bundleText === null) {
      console.warn(`Could not fetch previously-published version ${existingVersion}, skipping.`);
      continue;
    }
    mkdirSync(`${OUTPUT_DIR}/v${existingVersion}`, { recursive: true });
    writeFileSync(`${OUTPUT_DIR}/v${existingVersion}/widget.js`, bundleText);
  }

  versions.add(version);
  mkdirSync(`${OUTPUT_DIR}/v${version}`, { recursive: true });
  copyFileSync("dist/widget.js", `${OUTPUT_DIR}/v${version}/widget.js`);
  copyFileSync("dist/widget.js", `${OUTPUT_DIR}/widget.js`);
  writeFileSync(`${OUTPUT_DIR}/versions.json`, JSON.stringify([...versions].sort(), null, 2));

  console.log(`Assembled Pages artifact with versions: ${[...versions].sort().join(", ")}`);
}

await main();
