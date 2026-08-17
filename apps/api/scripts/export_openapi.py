"""Exports the live FastAPI app's OpenAPI schema to docs/openapi.json at
the repo root, for a static, browsable API reference that doesn't
require a running server (see docs/api-reference.md). Regenerate after
any router/schema change: `make api-openapi-export`.

Importing main.py is enough to get the real schema -- app.openapi()
walks every registered route/response model, the same introspection
FastAPI itself uses to serve /openapi.json from a running process.
Nothing here starts a server or touches the network; every integration
main.py wires up (Sentry, OTel, Prometheus) is inert with no endpoint
configured, matching local dev's own default .env.

Usage: uv run python -m scripts.export_openapi  (from apps/api)
"""

import json
from pathlib import Path

from main import app

OUTPUT_PATH = Path(__file__).resolve().parents[3] / "docs" / "openapi.json"


def export_openapi() -> None:
    schema = app.openapi()
    OUTPUT_PATH.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote OpenAPI schema ({len(schema.get('paths', {}))} paths) to {OUTPUT_PATH}")


if __name__ == "__main__":
    export_openapi()
