"""Unit tests for conversation_state.py (roadmap step 181). Pure
function tests, no DB needed -- transition() only ever mutates the
in-memory Conversation object's status attribute, same "test the pure
decision function directly" precedent agents/memory.py:MemoryAgent's
own test_memory_agent.py already established.
"""

import uuid

import pytest

from conversation_state import VALID_TRANSITIONS, InvalidTransitionError, transition
from models.conversation import Conversation


def _new_conversation(status: str) -> Conversation:
    conversation = Conversation(tenant_id=uuid.uuid4(), assistant_id=uuid.uuid4(), status=status)
    return conversation


def test_new_can_transition_to_active() -> None:
    conversation = _new_conversation("new")
    transition(conversation, "active")
    assert conversation.status == "active"


def test_new_can_transition_directly_to_archived() -> None:
    conversation = _new_conversation("new")
    transition(conversation, "archived")
    assert conversation.status == "archived"


def test_archived_is_terminal_and_rejects_every_transition() -> None:
    conversation = _new_conversation("archived")
    for target in ("new", "active", "waiting", "processing", "completed"):
        with pytest.raises(InvalidTransitionError):
            transition(conversation, target)
    assert conversation.status == "archived"


def test_new_cannot_skip_straight_to_processing() -> None:
    conversation = _new_conversation("new")
    with pytest.raises(InvalidTransitionError):
        transition(conversation, "processing")
    # A rejected transition leaves the status untouched.
    assert conversation.status == "new"


def test_completed_can_only_move_to_archived() -> None:
    conversation = _new_conversation("completed")
    for target in ("new", "active", "waiting", "processing"):
        with pytest.raises(InvalidTransitionError):
            transition(conversation, target)
    transition(conversation, "archived")
    assert conversation.status == "archived"


def test_every_state_has_a_defined_transition_set() -> None:
    # Guards against a future new status value being added to the
    # roadmap's own six-state list without a corresponding entry here.
    assert set(VALID_TRANSITIONS) == {
        "new",
        "active",
        "waiting",
        "processing",
        "completed",
        "archived",
    }


def test_processing_can_return_to_active_or_move_to_waiting() -> None:
    conversation = _new_conversation("processing")
    transition(conversation, "active")
    assert conversation.status == "active"

    conversation = _new_conversation("processing")
    transition(conversation, "waiting")
    assert conversation.status == "waiting"
