"""Tests for llm/__init__.py's PROVIDERS registry (roadmap step 152).

No router or agent is keyed on provider name yet -- this is tested
infrastructure ready for that caller, the same reasoning
test_agent_registry.py already applies to AgentRegistry starting
empty/unconsumed at step 139.
"""

from llm import PROVIDERS
from llm.anthropic import AnthropicProvider
from llm.openai import OpenAIProvider


def test_providers_registers_both_real_providers_by_name() -> None:
    assert set(PROVIDERS) == {"openai", "anthropic"}
    assert isinstance(PROVIDERS["openai"], OpenAIProvider)
    assert isinstance(PROVIDERS["anthropic"], AnthropicProvider)
