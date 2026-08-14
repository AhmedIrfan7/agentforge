"""Reranking providers (roadmap step 125, AGENTS.md SECTION "RERANKING":
"Design reranking as an independent stage"). base.py's RerankerProvider
is built interface-first, same reasoning embeddings/base.py:
EmbeddingProvider and vectorstore/base.py:VectorStore already
established for this project's other provider interfaces -- the
roadmap names this step "(abstracted provider)" explicitly. No
registry here, same "don't build machinery before there's a second
real thing to put in it" discipline as embeddings/__init__.py: this
roadmap never adds a second reranker (checked the full 125-300 range
before writing this), so lexical.py's LexicalReranker is expected to
stay the only real implementation, the same way pgvector stayed the
only real VectorStore.
"""
