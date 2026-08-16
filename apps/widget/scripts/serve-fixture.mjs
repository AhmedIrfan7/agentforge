import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

// Roadmap step 214. A minimal static file server for e2e/fixtures + the
// real built dist/ bundle -- no new dependency (matches this app's own
// "minimal deps" constraint, 201), used only by Playwright's own
// webServer below and never shipped or referenced anywhere in the real
// product.
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const FIXTURES_DIR = join(ROOT, "e2e", "fixtures");
const DIST_DIR = join(ROOT, "dist");
const PORT = 4173;

const CONTENT_TYPES = { ".html": "text/html", ".js": "text/javascript" };

function resolveFilePath(pathname) {
  const requested = pathname === "/" ? "/host-page.html" : pathname;
  // Route on the URL's own forward-slash pathname BEFORE normalizing --
  // node:path's normalize() converts "/widget.js" to "\widget.js" on
  // Windows, so comparing against the normalized form here silently
  // never matched and routed every request to FIXTURES_DIR instead of
  // DIST_DIR (a real bug caught live, not by inspection).
  const dir = requested === "/widget.js" ? DIST_DIR : FIXTURES_DIR;
  // Strip any leading ../ segments after normalizing -- this only ever
  // serves two fixed local directories, but a path-traversal footgun in
  // dev tooling is still a real footgun.
  const safeRelativePath = normalize(requested).replace(/^(\.\.[/\\])+/, "");
  return join(dir, safeRelativePath);
}

const server = createServer((req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  const filePath = resolveFilePath(url.pathname);

  readFile(filePath)
    .then((body) => {
      res.writeHead(200, { "Content-Type": CONTENT_TYPES[extname(filePath)] ?? "text/plain" });
      res.end(body);
    })
    .catch(() => {
      res.writeHead(404);
      res.end("Not found");
    });
});

server.listen(PORT, () => {
  console.log(`Fixture server listening on http://localhost:${PORT}`);
});
