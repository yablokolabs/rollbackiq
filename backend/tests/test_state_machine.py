"""Incident state machine tests."""

from __future__ import annotations

import pytest

from app.models.incident import (
    IllegalTransition,
    Incident,
    IncidentState,
    can_transition,
    transition,
)


def test_happy_path_reaches_recovered():
    state = IncidentState.HEALTHY
    for target in (
        IncidentState.SUSPECTED,
        IncidentState.INVESTIGATING,
        IncidentState.PROPOSED,
        IncidentState.AWAITING_APPROVAL,
        IncidentState.EXECUTING,
        IncidentState.VERIFYING,
        IncidentState.RECOVERED,
    ):
        state = transition(state, target)
    assert state is IncidentState.RECOVERED


def test_cannot_skip_approval_and_execute():
    with pytest.raises(IllegalTransition) as excinfo:
        transition(IncidentState.PROPOSED, IncidentState.EXECUTING)
    assert "PROPOSED -> EXECUTING" in str(excinfo.value)


def test_cannot_go_from_healthy_straight_to_executing():
    assert not can_transition(IncidentState.HEALTHY, IncidentState.EXECUTING)
    with pytest.raises(IllegalTransition):
        transition(IncidentState.HEALTHY, IncidentState.EXECUTING)


def test_denied_approval_escalates_rather_than_executing():
    """A denial must never fall through to execution."""
    assert can_transition(IncidentState.AWAITING_APPROVAL, IncidentState.ESCALATED)
    assert not can_transition(IncidentState.AWAITING_APPROVAL, IncidentState.RECOVERED)


def test_failed_verification_cannot_claim_recovery():
    assert can_transition(IncidentState.VERIFYING, IncidentState.ESCALATED)
    with pytest.raises(IllegalTransition):
        transition(IncidentState.EXECUTING, IncidentState.RECOVERED)


def test_incident_records_history_with_actor_and_reason():
    incident = Incident(id="inc-1", release_id="v2")
    incident.apply(
        IncidentState.SUSPECTED,
        actor="detector",
        reason="p95 4.1x baseline",
        context={"incident_id": "inc-1"},
    )
    incident.apply(IncidentState.INVESTIGATING, actor="duo-flow")

    assert incident.state is IncidentState.INVESTIGATING
    assert [r.to_state for r in incident.history] == [
        IncidentState.SUSPECTED,
        IncidentState.INVESTIGATING,
    ]
    assert incident.history[0].actor == "detector"
    assert incident.history[0].context == {"incident_id": "inc-1"}


def test_illegal_apply_leaves_state_and_history_untouched():
    incident = Incident(id="inc-2", release_id="v2")
    with pytest.raises(IllegalTransition):
        incident.apply(IncidentState.VERIFYING)
    assert incident.state is IncidentState.HEALTHY
    assert incident.history == []
