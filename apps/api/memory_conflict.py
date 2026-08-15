"""Memory conflict-resolution logic (roadmap step 173, AGENTS.md's own
"MEMORY LIFECYCLE" section: "Conflict resolution.").

No embedding-based semantic similarity here: `models/memory.py:Memory`
has no embedding column, and adding one (plus computing/storing an
embedding for every memory write) is real new infrastructure this
step's own wording doesn't ask for. A real, deterministic text-overlap
heuristic is the honest, minimal equivalent -- the same "real
heuristic, not fake ML" discipline `agents/planning.py:PlanningAgent`
and `agents/memory.py:MemoryAgent` already established for their own
decisions.

`find_conflicting_memory` treats two memories as conflicting when
their content shares enough words (`OVERLAP_THRESHOLD`, a normalized
word-set Jaccard similarity) to very likely be about the same thing --
not necessarily an outright contradiction (this codebase has no way to
tell "prefers email" contradicts "prefers phone calls" from "prefers
email" merely duplicating "prefers email, thanks" without real
semantic understanding), but a real, useful signal that keeping both
would be redundant.

The real policy: the higher-`importance_score` memory wins. A caller
(`memory_summarization.py`) that finds a conflict compares scores
itself and either calls `repositories/memory.py:MemoryRepository.
update_content` (173's own reason that method exists at all -- nothing
updated an existing `Memory` row before this step) or leaves the
existing memory alone and logs the new content as `"ignored"` via
`memory_observability.py:log_memory_event` (172) -- `find_conflicting_memory`
itself makes no DB calls and decides nothing beyond "do these two
pieces of content conflict," keeping it a pure, easily-tested function.
"""

import re
from collections.abc import Sequence

from models.memory import Memory

OVERLAP_THRESHOLD = 0.5

# Strips every non-alphanumeric character, not just leading/trailing
# punctuation -- an edge-only strip leaves an internal apostrophe
# ("Jordan's") intact, so it would never match its unpunctuated form
# ("jordans") even though they're clearly the same word for this
# heuristic's purposes.
_NON_ALNUM = re.compile(r"[^\w]")


def _word_set(text: str) -> set[str]:
    return {_NON_ALNUM.sub("", word).lower() for word in text.split()} - {""}


def content_overlap_ratio(a: str, b: str) -> float:
    words_a, words_b = _word_set(a), _word_set(b)
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def find_conflicting_memory(candidates: Sequence[Memory], new_content: str) -> Memory | None:
    for candidate in candidates:
        if content_overlap_ratio(candidate.content, new_content) >= OVERLAP_THRESHOLD:
            return candidate
    return None
