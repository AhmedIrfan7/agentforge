"""OpenAI embedding provider (roadmap step 107) -- the first real
EmbeddingProvider (base.py). Speaks OpenAI's REST API directly over httpx,
same reasoning `auth/oauth.py:GoogleOAuthProvider` already established for
this project's other provider adapters: it's a direct, authenticated
server-to-server call, so a vendor SDK buys nothing a raw HTTP client
doesn't already give for one endpoint.

No `PROVIDERS` registry here, unlike `auth/oauth.py` -- that registry only
earned its keep at OAuth's step 077 once a SECOND real provider existed to
prove the abstraction was real. Nothing later in this roadmap ever adds a
second embedding provider (150-152/216-218 are LLM/speech providers, a
different interface entirely), so a registry here would be machinery with
no second entry to ever hold -- the same "don't build it before there's
something real to put in it" call step 106 already made about this
package's `__init__.py`. Step 108's dispatcher imports this class
directly.

`text-embedding-3-small` chosen as the default model: cheapest current
OpenAI embedding model, 1536 native dimensions (verified against OpenAI's
own API docs before writing this) -- no `dimensions` truncation parameter
is sent, since 1536 already IS this model's native output size, and
`EmbeddingProvider.dimensions` must equal what `embed()` actually returns.
"""

import httpx

from config import settings


class EmbeddingProviderError(Exception):
    """Raised for any embedding-provider failure -- auth, rate limit,
    network, or a malformed response. A single type so step 108's
    dispatcher can catch one thing regardless of which provider is
    behind `EmbeddingProvider`, the same reason `errors.py`'s `AppError`
    gives every HTTP-facing error one shared base; this one isn't an
    `AppError` itself since it's raised from a Celery task, not a FastAPI
    request/response cycle -- there's no HTTP status code to carry."""


class OpenAIEmbeddingProvider:
    name = "openai"
    dimensions = 1536

    _EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
    _MODEL = "text-embedding-3-small"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    self._EMBEDDINGS_URL,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json={"model": self._MODEL, "input": texts},
                )
                response.raise_for_status()
                payload = response.json()

                # Sort by `index` rather than trust list order -- cheap,
                # and the one thing worth not just assuming from docs.
                rows = sorted(payload["data"], key=lambda row: row["index"])
                return [row["embedding"] for row in rows]
            except (httpx.HTTPError, KeyError) as exc:
                raise EmbeddingProviderError("OpenAI embedding request failed.") from exc
