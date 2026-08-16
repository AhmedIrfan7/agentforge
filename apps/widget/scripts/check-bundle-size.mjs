import { statSync } from "node:fs";

// Roadmap step 213. A plain Node script, same reasoning as build.mjs
// (202/210): avoids shell-specific size-check syntax (`stat -c%s` vs
// `stat -f%z` vs PowerShell's `.Length`) differing between this
// monorepo's POSIX CI and Windows local dev.
//
// 30 KB (raw, minified, un-gzipped) is the budget -- the bundle this
// script checks against is what actually gets served byte-for-byte
// from the CDN (widget-deploy.yml), not a gzip-assumed figure, since
// this project doesn't control or verify the CDN's compression
// behavior. At the time this check was added the real bundle was
// ~10 KB, so 30 KB is real headroom for genuine future growth (e.g.
// step 214's smoke-test-driven fixes, further theming), not a budget
// picked to just barely pass today.
const BUDGET_BYTES = 30 * 1024;
const BUNDLE_PATH = new URL("../dist/widget.js", import.meta.url);

const { size } = statSync(BUNDLE_PATH);
const sizeKb = (size / 1024).toFixed(2);
const budgetKb = (BUDGET_BYTES / 1024).toFixed(0);

if (size > BUDGET_BYTES) {
  console.error(
    `widget.js is ${sizeKb} KB, over the ${budgetKb} KB budget. ` +
      "Either trim the bundle or, if the growth is real and justified, raise BUDGET_BYTES in this script deliberately.",
  );
  process.exit(1);
}

console.log(`widget.js is ${sizeKb} KB (budget: ${budgetKb} KB) -- OK.`);
