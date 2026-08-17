"""Confirms every real API route uses strict Pydantic schema validation
(roadmap step 252) -- no request/response body typed as a raw, unnamed
dict/Any bypassing real model validation. A genuine regression test,
not just a one-time audit: the entire real OpenAPI surface (71 paths)
was audited once by hand for this step and only one real gap was
found -- main.py's own `/health` returning `dict[str, str]`, fixed the
same step. This test locks that "zero gaps" state in going forward; a
future route accidentally typed `-> dict[str, str]` (exactly what
/health itself was) fails here immediately.

Checks the real, public OpenAPI schema (app.openapi()), not FastAPI's
own internal routing objects -- those differ across FastAPI versions in
ways this test shouldn't be coupled to; the generated schema is the
stable, documented surface every real API consumer already relies on.
A route's request/response is "strictly typed" if its JSON schema
resolves to a real named component (a $ref, directly or nested inside
anyOf/oneOf for a Union response, e.g. auth/login's real
TokenResponse | MfaRequiredResponse) -- FastAPI only ever generates a
$ref from a real Pydantic model, never from a bare dict/Any.

Legitimate exceptions are each keyed by exact (method, path), not a
blanket allowlist, so a NEW non-JSON route doesn't silently inherit an
exemption it was never actually granted:
- multipart/form-data request bodies (real file uploads -- FastAPI
  validates these via UploadFile/File(), just not via a JSON schema)
- endpoints returning a raw Response/StreamingResponse (SSE streams,
  an OAuth redirect, a multi-format file download) -- none of these
  are JSON at all, so response_model doesn't apply
- 204 No Content responses (nothing to validate) are handled generically,
  not via this exception list.
"""

from typing import Any

from main import app

_MULTIPART_REQUEST_EXCEPTIONS = {
    (
        "post",
        "/organizations/{organization_id}/workspaces/{workspace_id}"
        "/knowledge-bases/{knowledge_base_id}/documents",
    ),
    (
        "post",
        "/organizations/{organization_id}/workspaces/{workspace_id}"
        "/knowledge-bases/{knowledge_base_id}/documents/{document_id}/versions",
    ),
}

_NON_JSON_RESPONSE_EXCEPTIONS = {
    ("get", "/auth/{provider}/login"),  # real 302 redirect, no body
    (
        "get",
        "/organizations/{organization_id}/workspaces/{workspace_id}"
        "/knowledge-bases/{knowledge_base_id}/assistants/{assistant_id}"
        "/conversations/{conversation_id}/export",
    ),  # real multi-format (json/markdown) download
    (
        "post",
        "/organizations/{organization_id}/workspaces/{workspace_id}"
        "/knowledge-bases/{knowledge_base_id}/assistants/{assistant_id}"
        "/conversations/{conversation_id}/messages/stream",
    ),  # real SSE stream
    ("post", "/public/assistants/{assistant_id}/conversations/{conversation_id}/messages/stream"),
}

_HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def _resolves_to_a_real_named_schema(schema: dict[str, Any]) -> bool:
    if "$ref" in schema:
        return True
    for key in ("anyOf", "oneOf", "allOf"):
        variants = schema.get(key)
        if isinstance(variants, list) and all(
            isinstance(variant, dict) and _resolves_to_a_real_named_schema(variant)
            for variant in variants
        ):
            return True
    # A real `list[SomeModel]` response_model (e.g. routers/retrieval.py:
    # dense_search) -- each array item is still validated against a real
    # named model, just wrapped in `type: array` rather than being a bare
    # top-level $ref itself.
    if schema.get("type") == "array":
        items = schema.get("items")
        return isinstance(items, dict) and _resolves_to_a_real_named_schema(items)
    return False


def test_every_json_request_body_is_a_real_pydantic_model() -> None:
    schema = app.openapi()
    for path, methods in schema["paths"].items():
        for method, details in methods.items():
            if method not in _HTTP_METHODS:
                continue
            request_body = details.get("requestBody")
            if not request_body:
                continue
            content = request_body.get("content", {})
            if "application/json" not in content:
                assert (method, path) in _MULTIPART_REQUEST_EXCEPTIONS, (
                    f"{method.upper()} {path} has a non-JSON request body not in the "
                    "documented multipart exceptions -- confirm it's a real file upload, "
                    "then add it there, or give it a real JSON request schema."
                )
                continue
            body_schema = content["application/json"].get("schema", {})
            assert _resolves_to_a_real_named_schema(body_schema), (
                f"{method.upper()} {path} has a request body with no real named Pydantic "
                f"schema: {body_schema!r}"
            )


def test_every_json_success_response_is_a_real_pydantic_model() -> None:
    schema = app.openapi()
    for path, methods in schema["paths"].items():
        for method, details in methods.items():
            if method not in _HTTP_METHODS:
                continue
            for code, response in details.get("responses", {}).items():
                if not code.startswith("2"):
                    continue
                if (method, path) in _NON_JSON_RESPONSE_EXCEPTIONS:
                    continue
                content = response.get("content")
                if content is None:
                    assert code == "204", (
                        f"{method.upper()} {path} ({code}) has no response body and isn't a "
                        "204 or a documented non-JSON exception."
                    )
                    continue
                response_schema = content.get("application/json", {}).get("schema", {})
                assert _resolves_to_a_real_named_schema(response_schema), (
                    f"{method.upper()} {path} ({code}) has a response with no real named "
                    f"Pydantic schema: {response_schema!r}"
                )
