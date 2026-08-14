"""Vector store providers (roadmap step 118). base.py's VectorStore is
built interface-first, matching embeddings/base.py:EmbeddingProvider's
own step-106 precedent (and unlike auth/oauth.py:OAuthProvider, which
stayed a concrete, interface-free GoogleOAuthProvider through step 076
and only became a Protocol once a second real provider at step 077
proved the abstraction was real) -- this roadmap sequences the
abstraction (118) before any concrete implementation (119's pgvector
adapter), so there's no earlier single-implementation step to
generalize away from.

No PROVIDERS registry here, and unlike EmbeddingProvider's own package
this one is never expected to grow one: checked the full roadmap for a
second vector-store step and there isn't one anywhere (ADR-0001 already
locked pgvector in as this project's one and only vector store) -- a
registry would be permanent machinery with nothing to ever hold, the
same call already made for embeddings/openai.py at step 107.
"""
