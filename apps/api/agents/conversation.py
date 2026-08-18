"""Conversation Agent -- real implementation.

Was a genuine skeleton (AGENTS.md SECTION "CONVERSATION AGENT") since
step 145: no chat/generation model existed anywhere in this codebase to
give `run()` real logic. Both blockers are gone now -- Milestone 6 built
a real conversation/session model, and `llm/openai.py:OpenAIProvider`
gives this a real model to call -- so implementing this for real closes
the actual gap `docs/ARCHITECTURE.md`'s own "honest limitations" section
named: a retrieval hit's "answer" was the raw retrieved chunk text
itself, not a synthesized one, because nothing existed to synthesize it.

Grounded-only prompting, not free generation: the system prompt
explicitly restricts the model to the provided context and tells it to
say so honestly when the context doesn't contain the answer, rather
than answering from its own training data. This is the standard,
correct RAG generation pattern -- retrieval decides what's true for
this tenant's documents, generation only phrases it -- and it directly
gives the honest "does it or doesn't it say X" answer a raw chunk dump
can't: an empty chunk list still gets a real, grounded response
("the context doesn't mention that"), not a bare "No results found."
"""

from dataclasses import dataclass

from agents.base import Agent
from agents.retriever import RetrievedChunk
from llm.base import LLMProvider, LLMResponse, Message

_SYSTEM_PROMPT = (
    "You are a helpful assistant answering questions using ONLY the context "
    "provided below. If the context does not contain enough information to "
    "answer, say so honestly -- never invent an answer or use outside "
    "knowledge not present in the context."
)


@dataclass(frozen=True)
class ConversationInput:
    query: str
    chunks: list[RetrievedChunk]


class ConversationAgent(Agent[ConversationInput, LLMResponse]):
    name = "conversation"

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm_provider = llm_provider

    # Returns the full LLMResponse, not just its .content -- agents/
    # tracing.py:traced_run's own isinstance(output, LLMResponse) check
    # (in place since step 153) picks real prompt_tokens/completion_tokens
    # off of exactly this shape and starts persisting them automatically;
    # returning a bare str would silently keep tracing's token fields
    # None even though a real LLM call just happened.
    async def run(self, input: ConversationInput) -> LLMResponse:
        context = (
            "\n\n---\n\n".join(chunk.text for chunk in input.chunks)
            if input.chunks
            else "(no relevant documents were found for this query)"
        )
        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=f"Context:\n{context}\n\nQuestion: {input.query}"),
        ]
        return await self._llm_provider.complete(messages)
