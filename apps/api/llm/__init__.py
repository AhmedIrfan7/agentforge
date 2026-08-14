"""LLM providers (roadmap step 150). base.py's LLMProvider is built
interface-first, same reasoning embeddings/base.py:EmbeddingProvider
(106) and vectorstore/base.py:VectorStore (118) already established --
the roadmap explicitly sequences the abstraction (150) before either
concrete implementation (151 OpenAI, 152 Anthropic), so there's no
earlier single-implementation step to generalize away from.

PROVIDERS below lands at 152, not 150 -- the same "don't build
machinery before there's a second real entry to put in it" discipline
auth/oauth.py's own PROVIDERS dict followed, appearing at step 077 once
a second real OAuth provider existed. There is no router/caller keyed
on provider name yet (every agent that would call an LLM, steps
144-148, is still an honestly-unimplemented skeleton) -- this dict
exists as tested infrastructure ready for that caller, the same way
`agents/registry.py:AgentRegistry` started empty by design at 139.
"""

from llm.anthropic import AnthropicProvider
from llm.base import LLMProvider
from llm.openai import OpenAIProvider

PROVIDERS: dict[str, LLMProvider] = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
}
