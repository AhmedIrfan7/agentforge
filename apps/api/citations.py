"""Citation tracking (roadmap step 127, AGENTS.md "CITATION SYSTEM" --
document/section/page/chunk/knowledge-source references, "allow users
to verify answers, increase trust"). "Wire citation-tracking through
retrieval->context->response" is read the same way steps 125/126 read
their own roadmap lines: build the real, correct primitive now -- no
response (chat/generation) step exists yet in this codebase to wire
INTO (that's steps 150+), so there's no live endpoint this connects to
today, same "no HTTP endpoint yet, no live-server verification needed"
position as steps 118/125/126.

A standalone pure module, same shape as retrieval_fusion.py/
context_builder.py: no DB access of its own. build_citations() takes
`document_info`, a plain dict[uuid.UUID, DocumentInfo] lookup the
caller already has (or fetches via repositories/document.py:
DocumentRepository.get() and repositories/knowledge_base.py:
KnowledgeBaseRepository.get(), both already exist) -- not a repository
method of its own, since nothing in this codebase calls this yet; the
same "add the capability when the step that needs it lands" discipline
used throughout this pipeline, rather than inventing DB-access
machinery with no real caller today.

Page references, AGENTS.md's own "where available" qualifier, are
genuinely never available in this codebase and are deliberately not a
field on Citation: extraction_pdf.py joins every PDF page into one
continuous markdown string (confirmed by reading it before writing
this module) -- no page boundary is retained anywhere on Document or
Chunk to honestly cite. Section references ARE derivable,
conditionally: chunking_markdown_heading.py's own chunks often start
with their real markdown heading line (its own documented limitation:
only the FIRST piece of an oversized, sub-split section keeps it) --
`_extract_section` parses that leading heading directly out of a
chunk's own real text, the same heading-line pattern agents/
chunking_recommendation.py already uses, so a chunk from any other
strategy, or a headingless leading chunk, honestly gets `section=None`
rather than a fabricated one.

`document_info[chunk.document_id]` is plain dict indexing, not
`.get()` with a placeholder fallback -- a missing entry means the
caller built an incomplete lookup for the chunks it's citing, a real
caller bug, not a legitimate "unknown document" state; failing loud
here matches vectorstore/pgvector.py's own `upsert()` precedent
(raise a clear error rather than silently fabricate a placeholder).
"""

import re
import uuid
from dataclasses import dataclass

from context_builder import ContextChunk

_HEADING_LINE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class DocumentInfo:
    title: str
    knowledge_base_name: str


@dataclass(frozen=True)
class Citation:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    knowledge_base_name: str
    section: str | None


def _extract_section(text: str) -> str | None:
    match = _HEADING_LINE.match(text)
    return match.group(1).strip() if match else None


def build_citations(
    chunks: list[ContextChunk], *, document_info: dict[uuid.UUID, DocumentInfo]
) -> list[Citation]:
    citations: list[Citation] = []
    for chunk in chunks:
        info = document_info[chunk.document_id]
        citations.append(
            Citation(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=info.title,
                knowledge_base_name=info.knowledge_base_name,
                section=_extract_section(chunk.text),
            )
        )
    return citations
