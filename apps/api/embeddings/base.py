"""EmbeddingProvider (roadmap step 106) -- a structural Protocol, same
reasoning as auth/oauth.py:OAuthProvider: nothing here needs inheritance
or shared state between providers, each is a self-contained adapter
around one external API's specific request/response shape. Whatever
eventually dispatches embedding generation (step 108, "background task:
batched embedding generation") talks only to this interface, so adding
a second real provider later (Cohere, a local model, etc.) means
writing one new class, not touching the dispatcher.

embed() is batch-shaped (list[str] -> list[list[float]]) from the
start, not single-text -- step 108's own name already commits to
batching being how this pipeline actually calls a provider, and
retrofitting a single-text interface into a batch one later would mean
changing every provider's signature instead of just adding one.

dimensions is a real, necessary interface property, not speculative:
step 109 ("Add pgvector column + index on Chunk") needs a fixed vector
size at table-creation time -- pgvector columns are dimensioned, e.g.
Vector(1536), not variable-length -- so whatever ends up calling that
migration needs to know a chosen provider's output size in advance.
Known from this roadmap's own sequencing, not guessed at from nothing.

No error-handling contract specified beyond "async, can raise" -- a
provider's own failure modes (rate limits, auth failures, network
errors) are exactly the kind of implementation detail step 107's real
OpenAI adapter should translate into whatever's actually useful to a
caller, not something this abstract interface should predict before a
real provider exists to prove out what's actually needed.
"""

from typing import Protocol


class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
