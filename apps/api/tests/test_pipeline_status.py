"""Tests for pipeline_status.py (roadmap step 111) -- pure function, no
DB/HTTP needed, fast unit coverage of every real Document.status value
this codebase actually produces (extraction.py, embeddings_pipeline.py).
"""

from pipeline_status import compute_pipeline_stages


def _stage_map(document_status: str, chunk_count: int) -> dict[str, str]:
    return {s.stage: s.status for s in compute_pipeline_stages(document_status, chunk_count)}


def test_pending_document_has_all_stages_not_started() -> None:
    stages = _stage_map("pending", chunk_count=0)
    assert stages == {
        "extraction": "pending",
        "chunk_generation": "not_applicable",
        "embedding_generation": "not_applicable",
    }


def test_processing_document_shows_extraction_in_progress() -> None:
    stages = _stage_map("processing", chunk_count=0)
    assert stages["extraction"] == "in_progress"
    assert stages["chunk_generation"] == "not_applicable"
    assert stages["embedding_generation"] == "not_applicable"


def test_extraction_failed_marks_extraction_failed_and_rest_not_applicable() -> None:
    stages = _stage_map("extraction_failed", chunk_count=0)
    assert stages["extraction"] == "failed"
    assert stages["chunk_generation"] == "not_applicable"
    assert stages["embedding_generation"] == "not_applicable"


def test_extraction_unsupported_marks_extraction_skipped() -> None:
    stages = _stage_map("extraction_unsupported", chunk_count=0)
    assert stages["extraction"] == "skipped"
    assert stages["chunk_generation"] == "not_applicable"
    assert stages["embedding_generation"] == "not_applicable"


def test_extracted_document_shows_extraction_done_chunking_pending() -> None:
    stages = _stage_map("extracted", chunk_count=0)
    assert stages["extraction"] == "completed"
    assert stages["chunk_generation"] == "pending"
    assert stages["embedding_generation"] == "not_applicable"


def test_embedding_in_progress_before_chunks_exist() -> None:
    stages = _stage_map("embedding", chunk_count=0)
    assert stages["extraction"] == "completed"
    assert stages["chunk_generation"] == "in_progress"
    assert stages["embedding_generation"] == "in_progress"


def test_chunk_count_drives_chunk_generation_completed_regardless_of_status() -> None:
    # A real DB fact (chunks exist) always wins over guessing from status
    # alone -- this is the whole reason chunk_count is a real query, not
    # an inference.
    stages = _stage_map("embedding", chunk_count=12)
    assert stages["chunk_generation"] == "completed"


def test_embedded_document_shows_every_stage_completed() -> None:
    stages = _stage_map("embedded", chunk_count=8)
    assert stages == {
        "extraction": "completed",
        "chunk_generation": "completed",
        "embedding_generation": "completed",
    }


def test_embedding_failed_shows_chunk_generation_and_embedding_both_failed() -> None:
    stages = _stage_map("embedding_failed", chunk_count=0)
    assert stages["extraction"] == "completed"
    assert stages["chunk_generation"] == "failed"
    assert stages["embedding_generation"] == "failed"
