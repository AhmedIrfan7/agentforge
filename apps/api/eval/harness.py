"""RAG evaluation harness (roadmap step 128) -- seeds a real fixture
corpus into real Postgres, then scores a caller-supplied search
function against the labeled relevance judgments (eval/fixtures.py).

Seeding and scoring are two separate functions on purpose:
`seed_fixture_set()` returns the real ids (`tenant_id`/
`knowledge_base_id`/`key_to_document_id`) a caller needs to build its
OWN search closure first (e.g. binding a `ChunkRepository` to a real
session and `tenant_id`, or an `agents.retriever.RetrieverAgent` call)
-- `run_eval()` can't build that closure itself without depending on
whichever retrieval mechanism a caller wants evaluated, which would
break the same layering rule established for rerankers/base.py,
context_builder.py, and eval/metrics.py (this package has no business
depending on agents/ or repositories/). `search` is therefore a plain
`query -> list[document_id]` callable -- the caller has already bound
everything mechanism-specific into it by the time it's passed in.

Each fixture document becomes exactly one real Chunk, so document-level
and chunk-level relevance coincide here -- this harness scores at
document granularity, the natural unit for "is this the right source"
when there are no separate per-chunk relevance judgments.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from statistics import mean

from db import get_session, set_tenant_context
from eval.fixtures import EvalFixtureSet
from eval.metrics import precision_at_k, recall_at_k
from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.workspace import Workspace


@dataclass(frozen=True)
class SeededFixtureSet:
    tenant_id: uuid.UUID
    knowledge_base_id: uuid.UUID
    key_to_document_id: dict[str, uuid.UUID]


@dataclass(frozen=True)
class EvalCaseResult:
    query: str
    precision: float
    recall: float


@dataclass(frozen=True)
class EvalReport:
    case_results: list[EvalCaseResult]
    mean_precision: float
    mean_recall: float


async def seed_fixture_set(fixture_set: EvalFixtureSet, *, slug_prefix: str) -> SeededFixtureSet:
    async with get_session() as session:
        org = Organization(name="RAG Eval Org", slug=f"{slug_prefix}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="RAG Eval WS", slug=f"{slug_prefix}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id,
            workspace_id=workspace.id,
            name="RAG Eval KB",
            slug=f"{slug_prefix}-kb",
        )
        session.add(knowledge_base)
        await session.flush()

        key_to_document_id: dict[str, uuid.UUID] = {}
        for eval_document in fixture_set.documents:
            document = Document(
                tenant_id=org.id,
                knowledge_base_id=knowledge_base.id,
                title=f"{eval_document.key}.txt",
                storage_key=f"{slug_prefix}/{eval_document.key}.txt",
                content_type="text/plain",
                size_bytes=len(eval_document.text),
            )
            session.add(document)
            await session.flush()
            session.add(
                Chunk(
                    tenant_id=org.id,
                    document_id=document.id,
                    text=eval_document.text,
                    start=0,
                    end=len(eval_document.text),
                    index=0,
                )
            )
            key_to_document_id[eval_document.key] = document.id

        await session.commit()
        return SeededFixtureSet(
            tenant_id=org.id,
            knowledge_base_id=knowledge_base.id,
            key_to_document_id=key_to_document_id,
        )


async def run_eval(
    fixture_set: EvalFixtureSet,
    seeded: SeededFixtureSet,
    search: Callable[[str], Awaitable[list[uuid.UUID]]],
    *,
    k: int = 5,
) -> EvalReport:
    case_results: list[EvalCaseResult] = []
    for case in fixture_set.cases:
        relevant_ids = {seeded.key_to_document_id[key] for key in case.relevant_document_keys}
        retrieved_ids = await search(case.query)
        case_results.append(
            EvalCaseResult(
                query=case.query,
                precision=precision_at_k(retrieved_ids, relevant_ids, k),
                recall=recall_at_k(retrieved_ids, relevant_ids, k),
            )
        )

    return EvalReport(
        case_results=case_results,
        mean_precision=mean(r.precision for r in case_results),
        mean_recall=mean(r.recall for r in case_results),
    )
