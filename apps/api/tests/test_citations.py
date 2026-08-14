"""Tests for citations.py (roadmap step 127) -- pure function tests,
no DB/HTTP needed (same reasoning test_retrieval_fusion.py/
test_context_builder.py already established for their own pure
algorithmic modules).
"""

import uuid

import pytest

from citations import Citation, DocumentInfo, build_citations
from context_builder import ContextChunk


def _chunk(*, text: str, document_id: uuid.UUID | None = None) -> ContextChunk:
    return ContextChunk(id=uuid.uuid4(), document_id=document_id or uuid.uuid4(), text=text)


def test_citation_carries_the_real_document_and_knowledge_base_names() -> None:
    document_id = uuid.uuid4()
    chunk = _chunk(text="Our refund policy allows returns.", document_id=document_id)
    info = {document_id: DocumentInfo(title="Refund Policy.pdf", knowledge_base_name="Support KB")}

    citations = build_citations([chunk], document_info=info)

    assert citations == [
        Citation(
            chunk_id=chunk.id,
            document_id=document_id,
            document_title="Refund Policy.pdf",
            knowledge_base_name="Support KB",
            section=None,
        )
    ]


def test_section_is_extracted_from_a_leading_markdown_heading() -> None:
    document_id = uuid.uuid4()
    chunk = _chunk(
        text="## Refund Policy\n\nReturns are accepted within thirty days.",
        document_id=document_id,
    )
    info = {document_id: DocumentInfo(title="doc.md", knowledge_base_name="KB")}

    citations = build_citations([chunk], document_info=info)

    assert citations[0].section == "Refund Policy"


def test_section_is_none_when_the_chunk_has_no_leading_heading() -> None:
    document_id = uuid.uuid4()
    chunk = _chunk(text="Just a plain paragraph with no heading at all.", document_id=document_id)
    info = {document_id: DocumentInfo(title="doc.md", knowledge_base_name="KB")}

    citations = build_citations([chunk], document_info=info)

    assert citations[0].section is None


def test_a_heading_that_is_not_the_first_line_is_not_treated_as_the_section() -> None:
    """chunking_markdown_heading.py's own documented limitation: only a
    section's FIRST resulting chunk keeps the heading text at all, so a
    heading appearing mid-chunk (not at position 0) isn't this chunk's
    own section -- it belongs to a different, later piece."""
    document_id = uuid.uuid4()
    chunk = _chunk(
        text="Some leading prose.\n\n## A Heading Later On\n\nMore text.", document_id=document_id
    )
    info = {document_id: DocumentInfo(title="doc.md", knowledge_base_name="KB")}

    citations = build_citations([chunk], document_info=info)

    assert citations[0].section is None


def test_citation_has_no_page_field() -> None:
    """AGENTS.md's own "page references where available" -- never
    honestly available in this codebase, so it's not a field at all."""
    assert not hasattr(Citation(uuid.uuid4(), uuid.uuid4(), "t", "k", None), "page")


def test_a_chunk_missing_from_the_lookup_raises_rather_than_fabricating_a_placeholder() -> None:
    chunk = _chunk(text="orphaned chunk")

    with pytest.raises(KeyError):
        build_citations([chunk], document_info={})


def test_multiple_chunks_each_get_their_own_citation() -> None:
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    chunk_a = _chunk(text="from doc a", document_id=doc_a)
    chunk_b = _chunk(text="from doc b", document_id=doc_b)
    info = {
        doc_a: DocumentInfo(title="A.pdf", knowledge_base_name="KB1"),
        doc_b: DocumentInfo(title="B.pdf", knowledge_base_name="KB2"),
    }

    citations = build_citations([chunk_a, chunk_b], document_info=info)

    assert [c.document_title for c in citations] == ["A.pdf", "B.pdf"]


def test_empty_input_returns_empty_output() -> None:
    assert build_citations([], document_info={}) == []
