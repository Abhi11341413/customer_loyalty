import pytest

from app.core.errors import InvalidStateError
from app.review.state_machine import (
    TRANSITIONS,
    allowed_actions,
    ensure_transition,
    state_after_validation,
)
from app.schemas.enums import DraftState as S
from app.schemas.enums import Severity


@pytest.mark.parametrize(
    ("severity", "state"),
    [
        (Severity.PASS, S.PENDING_REVIEW),
        (Severity.WARN, S.PENDING_REVIEW),
        (Severity.BLOCK, S.BLOCKED),
        (Severity.ESCALATE, S.ESCALATED),
    ],
)
def test_state_after_validation(severity, state):
    assert state_after_validation(severity) == state


@pytest.mark.parametrize("terminal", [S.REJECTED, S.DELIVERED, S.DELIVERY_BLOCKED, S.REFUSED])
def test_terminal_states_have_no_exit(terminal):
    assert TRANSITIONS[terminal] == frozenset()
    with pytest.raises(InvalidStateError):
        ensure_transition(terminal, S.PENDING_REVIEW)


@pytest.mark.parametrize("source", [s for s in S if s != S.PENDING_REVIEW])
def test_only_pending_review_can_be_approved(source):
    with pytest.raises(InvalidStateError):
        ensure_transition(source, S.APPROVED)


@pytest.mark.parametrize("source", [s for s in S if s != S.APPROVED])
def test_only_approved_can_be_delivered(source):
    with pytest.raises(InvalidStateError):
        ensure_transition(source, S.DELIVERED)


def test_edit_after_approval_returns_to_review():
    ensure_transition(S.APPROVED, S.PENDING_REVIEW)  # does not raise


def test_allowed_actions():
    assert "APPROVE" in allowed_actions(S.PENDING_REVIEW, Severity.PASS)
    assert "APPROVE" in allowed_actions(S.PENDING_REVIEW, Severity.WARN)
    assert "APPROVE" not in allowed_actions(S.BLOCKED, Severity.BLOCK)
    assert allowed_actions(S.ESCALATED, Severity.ESCALATE) == ["REJECT"]
    assert "DELIVER" in allowed_actions(S.APPROVED, Severity.PASS)
    assert "DELIVER" not in allowed_actions(S.PENDING_REVIEW, Severity.PASS)
    assert allowed_actions(S.DELIVERED, Severity.PASS) == []
