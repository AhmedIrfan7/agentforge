"""Conversation state machine (roadmap step 181, Milestone 6) -- real
transition validation for `models/conversation.py:Conversation.status`,
not just a bare string column (that's `Memory.scope`'s own "convention,
not a hard constraint" choice; the roadmap's own literal wording here
asks for a "state machine", which means real, checkable transition
rules, not a value dressed up as one).

Six states, the exact set the roadmap step itself names: `new` (just
created, no messages yet), `active` (a real exchange has happened),
`waiting`, `processing`, `completed`, `archived`. Only `new` -> `active`
has a real caller today (`routers/conversation.py`, on the first
message sent into a conversation) -- see `models/conversation.py`'s
own docstring for exactly why `waiting`/`processing`/`completed` stay
real, legal, but currently unreached states rather than something this
step fakes a trigger for. `archived` is reachable from any non-
archived state (step 184's own future archive endpoint's job to call
this), consistent with a real product being archivable from wherever
it currently sits, but not un-archivable within this module's own
scope -- no roadmap step through 200 asks for restoring an archived
conversation.

`VALID_TRANSITIONS` is the actual state machine: a plain dict graph,
not a state-machine library -- six states and one real automatic
transition today doesn't justify a new dependency (same "don't reach
for a library before the problem's real shape justifies one"
discipline `agents/resilience.py`'s own hand-rolled retry/fallback
already established over a retry library).
"""

from models.conversation import Conversation

VALID_TRANSITIONS: dict[str, set[str]] = {
    "new": {"active", "archived"},
    "active": {"processing", "waiting", "completed", "archived"},
    "processing": {"active", "waiting", "archived"},
    "waiting": {"active", "processing", "completed", "archived"},
    "completed": {"archived"},
    "archived": set(),
}


class InvalidTransitionError(Exception):
    pass


def transition(conversation: Conversation, new_status: str) -> None:
    current = conversation.status
    if new_status not in VALID_TRANSITIONS.get(current, set()):
        raise InvalidTransitionError(
            f"cannot transition a conversation from {current!r} to {new_status!r}"
        )
    conversation.status = new_status
