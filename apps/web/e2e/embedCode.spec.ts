import { expect, test } from "@playwright/test";
import { generateEmbedCode } from "../lib/embedCode";

// Real, deterministic unit coverage for lib/embedCode.ts (step 207) --
// there's no UI to browser-verify yet (see that module's own docstring
// for why), so this is the honest place for real automated proof
// instead, reusing @playwright/test's own runner (already a real
// dependency since step 198) rather than adding a second test
// framework for one module.

test.describe("generateEmbedCode", () => {
  test("includes only the assistant id and widget script url by default", () => {
    const code = generateEmbedCode({
      assistantId: "abc-123",
      widgetScriptUrl: "https://cdn.example.com/widget.js",
    });
    expect(code).toBe(
      '<script data-assistant-id="abc-123" src="https://cdn.example.com/widget.js"></script>',
    );
  });

  test("includes optional theme/api-url attributes when provided", () => {
    const code = generateEmbedCode({
      assistantId: "abc-123",
      widgetScriptUrl: "https://cdn.example.com/widget.js",
      apiUrl: "https://api.example.com",
      theme: {
        primaryColor: "#16a34a",
        fontFamily: "Georgia, serif",
        logoUrl: "https://example.com/logo.png",
        position: "bottom-left",
        colorScheme: "dark",
      },
    });
    expect(code).toContain('data-api-url="https://api.example.com"');
    expect(code).toContain('data-primary-color="#16a34a"');
    expect(code).toContain('data-font-family="Georgia, serif"');
    expect(code).toContain('data-logo-url="https://example.com/logo.png"');
    expect(code).toContain('data-position="bottom-left"');
    expect(code).toContain('data-color-scheme="dark"');
  });

  test("omits an optional attribute entirely when not provided", () => {
    const code = generateEmbedCode({
      assistantId: "abc-123",
      widgetScriptUrl: "https://cdn.example.com/widget.js",
      theme: { primaryColor: "#16a34a" },
    });
    expect(code).not.toContain("data-font-family");
    expect(code).not.toContain("data-logo-url");
    expect(code).not.toContain("data-position");
    expect(code).not.toContain("data-api-url");
    expect(code).not.toContain("data-color-scheme");
  });

  test("escapes double quotes and ampersands in attribute values", () => {
    const code = generateEmbedCode({
      assistantId: 'weird"id&value',
      widgetScriptUrl: "https://cdn.example.com/widget.js",
    });
    expect(code).toContain('data-assistant-id="weird&quot;id&amp;value"');
  });
});
