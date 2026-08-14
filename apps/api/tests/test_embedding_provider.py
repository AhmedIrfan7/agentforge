"""Tests for embeddings/base.py (roadmap step 106).

Unlike auth/oauth.py:OAuthProvider's own "swap a FakeOAuthProvider into
the real PROVIDERS registry, exercise it through the real router"
methodology (test_google_oauth_endpoints.py), there's no real registry
or dispatcher here yet to swap into -- step 106 is the interface alone,
with no consumer until step 107/108. This proves the narrower thing
that's actually true at this step: a real class implementing exactly
the documented Protocol shape works the way the interface promises,
not just that it type-checks.
"""

from dataclasses import dataclass

import pytest

from embeddings.base import EmbeddingProvider


@dataclass
class _FakeEmbeddingProvider:
    """A real implementation of EmbeddingProvider -- not a mock of one --
    the same reasoning test_google_oauth_endpoints.py:FakeOAuthProvider
    already established for this project's other provider interface."""

    name: str
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] * self.dimensions for text in texts]


def test_fake_provider_satisfies_the_protocol_structurally() -> None:
    provider: EmbeddingProvider = _FakeEmbeddingProvider(name="fake", dimensions=3)
    assert provider.name == "fake"
    assert provider.dimensions == 3


@pytest.mark.anyio
async def test_embed_returns_one_vector_per_input_text() -> None:
    provider = _FakeEmbeddingProvider(name="fake", dimensions=4)
    vectors = await provider.embed(["hello", "a longer piece of text"])
    assert len(vectors) == 2
    assert all(len(vector) == provider.dimensions for vector in vectors)


@pytest.mark.anyio
async def test_embed_on_empty_input_returns_empty_output() -> None:
    provider = _FakeEmbeddingProvider(name="fake", dimensions=4)
    assert await provider.embed([]) == []
