"""Embedding providers (roadmap step 106). base.py's EmbeddingProvider is
built interface-first, unlike auth/oauth.py:OAuthProvider (which stayed
a concrete, interface-free GoogleOAuthProvider through step 076 and only
became a Protocol once a second real provider at step 077 proved the
abstraction was real) -- this roadmap explicitly sequences the
abstraction (106) before any concrete implementation (107's OpenAI
provider), so there's no earlier single-implementation step to
generalize away from. Still no registry here yet, matching this
project's consistent "don't build machinery before there's something
real to put in it" discipline -- step 107 adds PROVIDERS alongside the
first real provider it registers, the same way OAuthProvider's own
PROVIDERS dict didn't appear until step 077 had two real providers
between them.
"""
