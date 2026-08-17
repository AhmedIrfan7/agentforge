"""Cross-conversation aggregate analytics (roadmap step 242, AGENTS.md's
own "ANALYTICS AGENT" section). A top-level package, not nested under
agents/ -- the same "distinct subsystem gets its own top-level home"
precedent voice/ already established: AnalyticsAgent computes tenant-
wide aggregates across many conversations/documents/agent runs, not a
single conversation turn, so it doesn't participate in orchestrator.py's
per-turn agent pipeline the way retriever/citation/planning/etc. do.
"""
