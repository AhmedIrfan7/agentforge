"""LLM providers (roadmap step 150). base.py's LLMProvider is built
interface-first, same reasoning embeddings/base.py:EmbeddingProvider
(106) and vectorstore/base.py:VectorStore (118) already established --
the roadmap explicitly sequences the abstraction (150) before either
concrete implementation (151 OpenAI, 152 Anthropic), so there's no
earlier single-implementation step to generalize away from.

No PROVIDERS registry here yet -- unlike those two precedents, this
package DOES already know from the roadmap's own sequencing that a
second real provider (152) is coming, so a registry will genuinely
earn its keep once it lands (the same "don't build machinery before
there's a second real entry to put in it" discipline auth/oauth.py's
own PROVIDERS dict followed, appearing at step 077 once a second real
OAuth provider existed). Step 152 is the right place to add it, not
150 -- there is exactly one real implementation until then.
"""
