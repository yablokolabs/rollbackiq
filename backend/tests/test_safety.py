"""Safety gate tests: the rollback path must refuse everything unsafe."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.approval import (
    Approval,
    ApprovalDecision,
    ProposedAction,
    RecoveryProposal,
)
from app.models.release import Release
from app.services.safety import SafetyGate

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
ENV = "demo-staging"


def proposal(**overrides) -> RecoveryProposal:
    data = {
        "incident_id": "inc-1",
        "action": ProposedAction.ROLLBACK,
        "target_release": "v1",
        "environment": ENV,
    }
    data.update(overrides)
    return RecoveryProposal(**data)


def approval_for(p: RecoveryProposal, **overrides) -> Approval:
    data = {
        "id": "appr-1",
        "incident_id": p.incident_id,
        "proposal_hash": p.proposal_hash,
        "actor": "sre@example.com",
        "decision": ApprovalDecision.APPROVED,
        "environment": ENV,
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=10),
    }
    data.update(overrides)
    return Approval(**data)


def current_release() -> Release:
    return Release(id="v2", environment=ENV, commit_sha="aaa111", known_good=False)


def target_release(**overrides) -> Release:
    data = {"id": "v1", "environment": ENV, "commit_sha": "bbb222", "known_good": True}
    data.update(overrides)
    return Release(**data)


#: Sentinel so that "argument omitted" (use the happy-path default) is
#: distinguishable from "explicitly no approval / no release".
UNSET = object()


def run_gate(
    *,
    p: RecoveryProposal | None = None,
    a=UNSET,
    current=UNSET,
    target=UNSET,
    environment: str = ENV,
    idempotency_key: str | None = "rollback-inc-1-v1",
    executed: set[str] | None = None,
    now: datetime = NOW,
):
    p = p or proposal()
    gate = SafetyGate()
    return gate.check(
        proposal=p,
        approval=approval_for(p) if a is UNSET else a,
        current_release=current_release() if current is UNSET else current,
        target_release=target_release() if target is UNSET else target,
        environment=environment,
        idempotency_key=idempotency_key,
        executed_idempotency_keys=executed or set(),
        now=now,
    )


def codes(verdict) -> list[str]:
    return [c.code for c in verdict.vetoes]


def test_fully_authorized_rollback_is_allowed():
    verdict = run_gate()
    assert verdict.allowed is True, codes(verdict)
    assert verdict.vetoes == []
    assert verdict.target_release == "v1"


def test_missing_approval_is_refused():
    verdict = run_gate(a=None)
    assert verdict.allowed is False
    assert "APPROVAL_PRESENT" in codes(verdict)


def test_denied_approval_is_refused():
    p = proposal()
    verdict = run_gate(p=p, a=approval_for(p, decision=ApprovalDecision.DENIED))
    assert "APPROVAL_GRANTED" in codes(verdict)


def test_expired_approval_is_refused():
    p = proposal()
    expired = approval_for(
        p,
        created_at=NOW - timedelta(minutes=30),
        expires_at=NOW - timedelta(seconds=1),
    )
    verdict = run_gate(p=p, a=expired)
    assert "APPROVAL_NOT_EXPIRED" in codes(verdict)


def test_approval_for_a_different_proposal_is_refused():
    """Approving one action must not authorize a different one."""
    p = proposal()
    stale = approval_for(p)
    changed = proposal(target_release="v0")  # proposal changed after approval
    verdict = run_gate(p=changed, a=stale)
    assert verdict.allowed is False
    assert "APPROVAL_IN_SCOPE" in codes(verdict)
    assert stale.proposal_hash != changed.proposal_hash


def test_approval_over_max_age_is_refused():
    p = proposal()
    long_lived = approval_for(
        p,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=4),
    )
    verdict = run_gate(p=p, a=long_lived)
    assert "APPROVAL_WITHIN_MAX_AGE" in codes(verdict)


def test_non_human_approver_is_refused():
    p = proposal()
    for actor in ("system", "agent", "duo", "RollbackIQ", ""):
        verdict = run_gate(p=p, a=approval_for(p, actor=actor))
        assert "APPROVAL_ACTOR_IS_HUMAN" in codes(verdict), actor


def test_wrong_environment_is_refused():
    verdict = run_gate(environment="production")
    assert verdict.allowed is False
    assert "ENVIRONMENT_ALLOWLISTED" in codes(verdict)


def test_proposal_environment_mismatch_is_refused():
    verdict = run_gate(p=proposal(environment="production"))
    assert "PROPOSAL_ENVIRONMENT_MATCHES" in codes(verdict)


def test_unknown_target_is_refused():
    verdict = run_gate(target=None)
    assert "TARGET_RELEASE_KNOWN" in codes(verdict)


def test_target_that_is_not_known_good_is_refused():
    verdict = run_gate(target=target_release(known_good=False))
    assert "TARGET_IS_KNOWN_GOOD" in codes(verdict)


def test_target_equal_to_current_release_is_refused():
    verdict = run_gate(target=target_release(id="v2"))
    assert "TARGET_DIFFERS_FROM_CURRENT" in codes(verdict)


def test_target_from_another_environment_is_refused():
    verdict = run_gate(target=target_release(environment="production"))
    assert "TARGET_ENVIRONMENT_MATCHES" in codes(verdict)


def test_unknown_current_release_is_refused():
    verdict = run_gate(current=None)
    assert "CURRENT_RELEASE_KNOWN" in codes(verdict)


def test_unsafe_migration_is_refused_and_unknown_is_unsafe():
    p = proposal(requires_migration=True)
    unknown = run_gate(p=p, target=target_release(migration_compatible=None))
    assert "MIGRATION_COMPATIBLE" in codes(unknown)

    incompatible = run_gate(p=p, target=target_release(migration_compatible=False))
    assert "MIGRATION_COMPATIBLE" in codes(incompatible)

    compatible = run_gate(p=p, target=target_release(migration_compatible=True))
    assert compatible.allowed is True, codes(compatible)


def test_missing_idempotency_key_is_refused():
    verdict = run_gate(idempotency_key=None)
    assert "IDEMPOTENCY_KEY_PRESENT" in codes(verdict)


def test_duplicate_rollback_request_is_refused():
    verdict = run_gate(executed={"rollback-inc-1-v1"})
    assert "NOT_ALREADY_EXECUTED" in codes(verdict)


def test_hold_and_escalate_never_execute():
    for action in (ProposedAction.HOLD, ProposedAction.ESCALATE):
        p = proposal(action=action)
        verdict = run_gate(p=p, a=approval_for(p))
        assert verdict.allowed is False
        assert "ACTION_IS_ROLLBACK" in codes(verdict)


def test_verdict_reports_every_veto_not_just_the_first():
    p = proposal(environment="production")
    verdict = run_gate(p=p, a=None, environment="production", idempotency_key=None, target=None)
    assert verdict.allowed is False
    assert len(verdict.vetoes) >= 4
    assert "APPROVAL_PRESENT" in codes(verdict)
    assert "IDEMPOTENCY_KEY_PRESENT" in codes(verdict)
    assert "TARGET_RELEASE_KNOWN" in codes(verdict)
    assert "ENVIRONMENT_ALLOWLISTED" in codes(verdict)


def test_audit_context_contains_veto_codes():
    verdict = run_gate(target=None)
    context = verdict.to_audit_context()
    assert context["allowed"] == "False"
    assert "TARGET_RELEASE_KNOWN" in context["veto_codes"]


def test_a_passing_check_detail_describes_the_passing_outcome():
    """A passing check must not carry its failure wording.

    The verdict is the artifact an operator reads, so a check that passed while
    rendering "actor is not an authorized human identity" contradicts its own
    ``passed`` field. A real Duo investigation of this gate found exactly that
    inversion across several checks, alongside ``passed: true``.
    """
    verdict = run_gate()
    assert verdict.allowed is True
    details = {c.code: c.detail for c in verdict.checks}

    assert details["APPROVAL_ACTOR_IS_HUMAN"] == (
        "approval actor 'sre@example.com' is an authorized human identity"
    )
    assert details["CURRENT_RELEASE_KNOWN"] == "current deployed release is 'v2'"
    assert details["NOT_ALREADY_EXECUTED"] == (
        "idempotency key 'rollback-inc-1-v1' has not been executed"
    )
    assert "was verified healthy" in details["TARGET_IS_KNOWN_GOOD"]
    assert details["APPROVAL_PRESENT"] == "approval 'appr-1' supplied"


def test_a_refused_check_detail_still_reads_as_a_refusal():
    """Fixing the inversion must not soften the refusal path.

    What an operator sees on a veto has to stay the same wording, otherwise the
    audit trail loses the reason the rollback was refused.
    """
    verdict = run_gate(target=None)
    details = {c.code: c.detail for c in verdict.checks}

    assert details["TARGET_RELEASE_KNOWN"] == (
        "rollback target 'v1' is not a release we have observed"
    )
    assert details["TARGET_IS_KNOWN_GOOD"] == (
        "rollback target has not been verified healthy by this system"
    )
    assert details["TARGET_DIFFERS_FROM_CURRENT"] != (
        "rollback target 'v1' differs from the deployed release 'v2'"
    )
