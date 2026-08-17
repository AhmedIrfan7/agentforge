// Assembles the GitHub Pages deploy artifact with real, permanent
// per-version URLs (roadmap step 210, "pinned script version") and
// real Subresource Integrity hashes for each (roadmap step 275, "CDN
// config for widget assets").
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
//
// SRI hashes matter specifically here because GitHub Pages has no
// configuration surface for its own Cache-Control headers -- confirmed
// live (curl -I against the real deployed URL): every file gets a
// fixed `max-age=600` from GitHub's own edge, whether it's the mutable
// `widget.js` (which SHOULD revalidate often) or an immutable pinned
// `v{version}/widget.js` (which never changes once published, but gets
// the identical short-lived cache treatment anyway -- a real platform
// limitation, not something this project's own config controls). A
// customer who embeds a PINNED version with a real `integrity="sha384-
// ..."` attribute lets the browser itself cache and skip re-validating
// that exact, unchanging resource far more aggressively than the
// origin's own Cache-Control alone would ever allow -- the real,
// addable CDN hardening available within GitHub Pages' actual
// constraints, matching AGENTS.md's own "CDN EMBED ARCHITECTURE"
// section: "Widget loads securely through the CDN" / "Cache friendly."
//
// versions.json's own shape changes here from a flat array of version
// strings to {version: integrityHash} -- the only real consumer of its
// previous shape is this same script's own read path below (grepped
// the repo to confirm), so this is a safe, self-contained evolution,
// not a breaking change to any other real caller.

import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";

const PAGES_URL = "https://ahmedirfan7.github.io/agentforge";
const OUTPUT_DIR = "pages-root";

const packageJson = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf-8"));
const version = packageJson.version;

function sriHash(content) {
  return `sha384-${createHash("sha384").update(content).digest("base64")}`;
}

async function fetchText(url) {
  const response = await fetch(url);
  if (!response.ok) {
    return null;
  }
  return response.text();
}

async function fetchBuffer(url) {
  // Raw bytes, not .text() -- an SRI hash must be computed over the
  // EXACT bytes that get written back out and served, and a
  // fetch-as-text-then-rewrite round trip risks a transcoding mismatch
  // (unlikely for plain ASCII/UTF-8 JS output, but a wrong SRI hash
  // silently breaks every real customer embed using `integrity=`, high
  // enough real stakes to not risk it on a "probably fine" assumption).
  const response = await fetch(url);
  if (!response.ok) {
    return null;
  }
  return Buffer.from(await response.arrayBuffer());
}

async function main() {
  mkdirSync(OUTPUT_DIR, { recursive: true });

  const existingManifestText = await fetchText(`${PAGES_URL}/versions.json`);
  const existingManifest = existingManifestText ? JSON.parse(existingManifestText) : {};
  // Backward-compatible with the pre-step-275 flat-array shape
  // (["0.2.0", ...]) -- confirmed live that the real currently-deployed
  // versions.json is still that old shape, so this script must keep
  // reading it correctly during the migration deploy, not just once
  // the new shape is already live everywhere.
  const previousVersions = Array.isArray(existingManifest)
    ? existingManifest
    : Object.keys(existingManifest);

  const manifest = {};

  for (const existingVersion of previousVersions) {
    if (existingVersion === version) {
      continue;
    }
    const bundleBuffer = await fetchBuffer(`${PAGES_URL}/v${existingVersion}/widget.js`);
    if (bundleBuffer === null) {
      console.warn(`Could not fetch previously-published version ${existingVersion}, skipping.`);
      continue;
    }
    mkdirSync(`${OUTPUT_DIR}/v${existingVersion}`, { recursive: true });
    writeFileSync(`${OUTPUT_DIR}/v${existingVersion}/widget.js`, bundleBuffer);
    // Always computed from the actually-fetched bytes, never trusted
    // from a previously-stored value (the old manifest shape had none
    // to trust anyway) -- the real content is the only source of truth
    // for its own hash.
    manifest[existingVersion] = sriHash(bundleBuffer);
  }

  const bundle = readFileSync("dist/widget.js");
  manifest[version] = sriHash(bundle);
  mkdirSync(`${OUTPUT_DIR}/v${version}`, { recursive: true });
  copyFileSync("dist/widget.js", `${OUTPUT_DIR}/v${version}/widget.js`);
  copyFileSync("dist/widget.js", `${OUTPUT_DIR}/widget.js`);

  const sortedManifest = Object.fromEntries(
    Object.entries(manifest).sort(([a], [b]) => a.localeCompare(b)),
  );
  writeFileSync(`${OUTPUT_DIR}/versions.json`, JSON.stringify(sortedManifest, null, 2));

  console.log(`Assembled Pages artifact with versions: ${Object.keys(sortedManifest).join(", ")}`);
}

await main();
