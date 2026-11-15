"""Draft state machine (blueprint section 9.6) and the actions each state permits.

Owner: M4.

Deviations from the diagram, all conservative:
- An edit may also move PENDING_REVIEW/APPROVED to BLOCKED or ESCALATED when re-validation
  says so (the diagram only draws the PASS/WARN outcome of "edit -> re-validate").
- ESCALATED drafts are read-only (OPEN-7 default) but may be REJECTED, so a stuck escalated
  draft does not block new drafts for that customer forever.
"""

from __future__ import annotations

from app.core.errors import InvalidStateError
from app.schemas.enums import DraftState, Severity

S = DraftState

TRANSITIONS: dict[DraftState, frozenset[DraftState]] = {
    S.GENERATED: frozenset({S.PENDING_REVIEW, S.BLOCKED, S.ESCALATED}),
    S.PENDING_REVIEW: frozenset({S.PENDING_REVIEW, S.BLOCKED, S.ESCALATED, S.APPROVED, S.REJECTED}),
    S.BLOCKED: frozenset({S.PENDING_REVIEW, S.BLOCKED, S.ESCALATED, S.REJECTED}),
    S.ESCALATED: frozenset({S.REJECTED}),
    S.APPROVED: frozenset(
        {S.PENDING_REVIEW, S.BLOCKED, S.ESCALATED, S.DELIVERED, S.DELIVERY_BLOCKED}
    ),
    S.REJECTED: frozenset(),
    S.DELIVERED: frozenset(),
    S.DELIVERY_BLOCKED: frozenset(),
    S.REFUSED: frozenset(),
}

#: States in which a draft still counts as "open" for duplicate-draft prevention.
OPEN_STATES = frozenset({S.GENERATED, S.PENDING_REVIEW, S.BLOCKED, S.ESCALATED, S.APPROVED})

EDITABLE_STATES = frozenset({S.PENDING_REVIEW, S.BLOCKED, S.APPROVED})
REVALIDATABLE_STATES = frozenset({S.PENDING_REVIEW, S.BLOCKED, S.APPROVED})
REJECTABLE_STATES = frozenset({S.PENDING_REVIEW, S.BLOCKED, S.ESCALATED})
REGENERATABLE_STATES = frozenset({S.PENDING_REVIEW, S.BLOCKED})
APPROVABLE_SEVERITIES = frozenset({Severity.PASS, Severity.WARN})


def ensure_transition(current: DraftState, target: DraftState) -> None:
    """Raise InvalidStateError unless current -> target is allowed."""
    if target not in TRANSITIONS[current]:
        raise InvalidStateError(
            f"Draft cannot move from {current} to {target}.",
            details={"state": str(current), "target": str(target)},
        )


def state_after_validation(severity: Severity) -> DraftState:
    """Review state implied by a validation verdict."""
    if severity == Severity.BLOCK:
        return S.BLOCKED
    if severity == Severity.ESCALATE:
        return S.ESCALATED
    return S.PENDING_REVIEW


def allowed_actions(state: DraftState, validation: Severity) -> list[str]:
    """Actions the reviewer UI may offer. The API enforces the same rules independently."""
    actions: list[str] = []
    if state in EDITABLE_STATES:
        actions.append("EDIT")
    if state in REVALIDATABLE_STATES:
        actions.append("REVALIDATE")
    if state == S.PENDING_REVIEW and validation in APPROVABLE_SEVERITIES:
        actions.append("APPROVE")
    if state in REJECTABLE_STATES:
        actions.append("REJECT")
    if state in REGENERATABLE_STATES:
        actions.append("REGENERATE")
    if state == S.APPROVED:
        actions.append("DELIVER")
    return actions
