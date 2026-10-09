"""Incident state machine.

The state machine is deliberately strict: every transition goes through
:func:`transition`, which rejects illegal moves. Handlers are expected to fail
closed, because the alternative (a silent illegal transition) is how an
unsafe remediation reaches production.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, FrozenSet, Optional

from pydantic import BaseModel, Field


class IncidentState(str, Enum):
    HEALTHY = "HEALTHY"
    SUSPECTED = "SUSPECTED"
    INVESTIGATING = "INVESTIGATING"
    PROPOSED = "PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RECOVERED = "RECOVERED"
    ESCALATED = "ESCALATED"


#: Legal transitions. A denied or expired approval leads to ESCALATED rather
#: than to a distinct state, so "no action was taken" is always visible.
LEGAL_TRANSITIONS: Dict[IncidentState, FrozenSet[IncidentState]] = {
    IncidentState.HEALTHY: frozenset({IncidentState.SUSPECTED}),
    IncidentState.SUSPECTED: frozenset({IncidentState.INVESTIGATING, IncidentState.HEALTHY}),
    IncidentState.INVESTIGATING: frozenset(
        {IncidentState.PROPOSED, IncidentState.HEALTHY, IncidentState.ESCALATED}
    ),
    IncidentState.PROPOSED: frozenset(
        {IncidentState.AWAITING_APPROVAL, IncidentState.ESCALATED}
    ),
    IncidentState.AWAITING_APPROVAL: frozenset(
        {IncidentState.EXECUTING, IncidentState.ESCALATED}
    ),
    # A rollback may fail; that is an escalation, never a silent return to HEALTHY.
    IncidentState.EXECUTING: frozenset({IncidentState.VERIFYING, IncidentState.ESCALATED}),
    IncidentState.VERIFYING: frozenset(
        {IncidentState.RECOVERED, IncidentState.ESCALATED}
    ),
    # Terminal states. A recovered incident may reopen if a new regression is
    # detected; an escalated incident must be resolved by a human.
    IncidentState.RECOVERED: frozenset({IncidentState.SUSPECTED}),
    IncidentState.ESCALATED: frozenset({IncidentState.INVESTIGATING}),
}

TERMINAL_STATES: FrozenSet[IncidentState] = frozenset(
    {IncidentState.RECOVERED, IncidentState.ESCALATED}
)


class IllegalTransition(RuntimeError):
    """Raised when a transition is not allowed by the state machine."""

    def __init__(self, current: IncidentState, target: IncidentState) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"illegal incident transition: {current.value} -> {target.value}; "
            f"allowed: {sorted(s.value for s in LEGAL_TRANSITIONS[current])}"
        )


def can_transition(current: IncidentState, target: IncidentState) -> bool:
    return target in LEGAL_TRANSITIONS.get(current, frozenset())


def transition(current: IncidentState, target: IncidentState) -> IncidentState:
    """Return ``target`` if the move is legal, otherwise raise."""
    if not can_transition(current, target):
        raise IllegalTransition(current, target)
    return target


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TransitionRecord(BaseModel):
    """One auditable state change."""

    at: datetime = Field(default_factory=utcnow)
    from_state: IncidentState
    to_state: IncidentState
    actor: str = "system"
    reason: str = ""
    context: Dict[str, str] = Field(default_factory=dict)


class Incident(BaseModel):
    """Minimal incident record; the SQLite store keeps the durable copy."""

    id: str
    release_id: str
    environment: str = "demo"
    state: IncidentState = IncidentState.HEALTHY
    severity: str = "sev3"
    detected_at: Optional[datetime] = None
    baseline_ref: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)
    history: list[TransitionRecord] = Field(default_factory=list)

    def apply(
        self,
        target: IncidentState,
        *,
        actor: str = "system",
        reason: str = "",
        at: Optional[datetime] = None,
        context: Optional[Dict[str, str]] = None,
    ) -> "Incident":
        """Validate and apply a transition, recording it in the history."""
        new_state = transition(self.state, target)
        self.history.append(
            TransitionRecord(
                at=at or utcnow(),
                from_state=self.state,
                to_state=new_state,
                actor=actor,
                reason=reason,
                context=context or {},
            )
        )
        self.state = new_state
        return self
