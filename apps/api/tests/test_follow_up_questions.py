"""Tests for follow_up_questions.py (roadmap step 190). Covers the
real "no key configured" failure path against the actual
api.openai.com endpoint (same discipline test_openai_llm_provider.py/
test_memory_summarization.py already established), plus a real
success path using httpx.MockTransport.
"""

import httpx
import pytest

from follow_up_questions import _strip_list_marker, generate_follow_up_questions
from llm.base import LLMProviderError


def _client_factory(handler: httpx.MockTransport) -> type[httpx.AsyncClient]:
    class _PatchedClient(httpx.AsyncClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = handler
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    return _PatchedClient


def _mock_completion_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


def test_strip_list_marker_removes_numbering() -> None:
    assert _strip_list_marker("1. What is the deadline?") == "What is the deadline?"
    assert _strip_list_marker("2) Any exceptions?") == "Any exceptions?"


def test_strip_list_marker_removes_bullets() -> None:
    assert _strip_list_marker("- Anything else?") == "Anything else?"
    assert _strip_list_marker("* How does this work?") == "How does this work?"
    assert _strip_list_marker("• What about edge cases?") == "What about edge cases?"


def test_strip_list_marker_leaves_a_plain_line_unchanged() -> None:
    assert _strip_list_marker("What is the refund window?") == "What is the refund window?"


@pytest.mark.anyio
async def test_raises_the_real_provider_error_against_the_live_api_with_no_key() -> None:
    with pytest.raises(LLMProviderError):
        await generate_follow_up_questions("What is your refund policy?", "30 days.")


@pytest.mark.anyio
async def test_generates_and_parses_real_suggestions(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = "1. What about exchanges?\n2. Is there a restocking fee?\n- Can I get store credit?"

    def handler(request: httpx.Request) -> httpx.Response:
        return _mock_completion_response(raw)

    monkeypatch.setattr(
        "llm.openai.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )

    questions = await generate_follow_up_questions("What is your refund policy?", "30 days.")
    assert questions == [
        "What about exchanges?",
        "Is there a restocking fee?",
        "Can I get store credit?",
    ]


@pytest.mark.anyio
async def test_blank_lines_in_the_response_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = "1. What about exchanges?\n\n\n2. Any other questions?"

    def handler(request: httpx.Request) -> httpx.Response:
        return _mock_completion_response(raw)

    monkeypatch.setattr(
        "llm.openai.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )

    questions = await generate_follow_up_questions("What is your refund policy?", "30 days.")
    assert questions == ["What about exchanges?", "Any other questions?"]
