"""RAG evaluation harness (roadmap step 128, AGENTS.md "RAG EVALUATION"
-- "Do not assume retrieval quality is good. Measure it."). Scoped to
this step's own concrete ask, "precision/recall on labeled fixtures",
not AGENTS.md's full aspirational metric list for this section
(citation accuracy, groundedness, answer quality, user satisfaction,
etc. all need a real response/chat step to even exist -- that's steps
150+, the same gap already documented at step 127).

metrics.py is pure (precision_at_k/recall_at_k, standard IR formulas,
no DB). fixtures.py is a real, small, hardcoded labeled dataset --
documents with distinct enough topics that retrieval must actually
discriminate between them, not just return everything. harness.py is
the one part of this package that touches real Postgres (seeding the
fixture documents/chunks, matching this codebase's consistent "no
mocks for infrastructure this project owns" discipline) -- unlike
retrieval_fusion.py/context_builder.py/citations.py, a harness whose
whole job is running real retrieval against a real seeded corpus can't
honestly be a pure module.
"""
