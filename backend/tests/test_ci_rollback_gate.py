"""Tests for the CI rollback path.

The CI job is the only thing that changes a deployment, so the interesting
assertions here are the refusals. Each test names one way a rollback must not
happen and proves the gate stops it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
BACKEND = REPO_ROOT / "backend"
for path in (str(BACKEND), str(SCRIPTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.models.approval import (  # noqa: E402
    Approval,
    ApprovalDecision,
    ProposedAction,
    RecoveryProposal,
)
from app.models.incident import utcnow  # noqa: E402
from app.models.metrics import Baseline, MetricWindow  # noqa: E402
from app.models.release import Release  # noqa: E402


def _load(name: str):
    """Import a repo script by path, so the tests exercise the shipped file."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ci_rollback = _load("ci_rollback")
ci_incident = _load("ci_incident")

ENVIRONMENT = "demo-staging"
HEALTHY_DIGEST = "sha256:" + "a" * 64


def _window(release: str, *, samples: int = 60, p95: float = 22.0, error_rate: float = 0.0) -> MetricWindow:
    started = utcnow()
    return MetricWindow(
        release=release,
        environment=ENVIRONMENT,
        started_at=started,
        ended_at=started + timedelta(seconds=10),
        request_count=samples,
        error_count=int(samples * error_rate),
        error_rate=error_rate,
        p95_ms=p95,
        source="test",
    )


def _bundle(*, approval: Approval | None, target_digest: str = HEALTHY_DIGEST) -> object:
    proposal = RecoveryProposal(
        incident_id="inc-1",
        action=ProposedAction.ROLLBACK,
        target_release="v1",
        environment=ENVIRONMENT,
    )
    baseline_window = _window("v1")
    return ci_rollback.IncidentBundle(
        incident_id="inc-1",
        environment=ENVIRONMENT,
        proposal=proposal,
        approval=approval,
        current_release=Release(
            id="v2", environment=ENVIRONMENT, image_digest="sha256:" + "b" * 64, known_good=False
        ),
        target_release=Release(
            id="v1", environment=ENVIRONMENT, image_digest=target_digest, known_good=True
        ),
        baseline=Baseline.from_window(baseline_window, min_samples=30, max_error_rate=0.05),
        before=_window("v2", p95=170.0, error_rate=0.10),
        idempotency_key="rollback-inc-1-v1",
    )


def _approval(*, actor: str = "an-operator", decision: ApprovalDecision = ApprovalDecision.APPROVED,
              proposal_hash: str = "", expires_in: float = 600.0) -> Approval:
    now = utcnow()
    bundle = _bundle(approval=None)
    return Approval(
        id="appr-1",
        incident_id="inc-1",
        proposal_hash=proposal_hash or bundle.proposal.proposal_hash,
        actor=actor,
        decision=decision,
        environment=ENVIRONMENT,
        created_at=now,
        expires_at=now + timedelta(seconds=expires_in),
    )


def _evaluate(bundle, *, key: str = "rollback-inc-1-v1", executed=None, environment=None):
    decision, _ = ci_rollback.evaluate_gate(
        bundle,
        idempotency_key=key,
        executed_idempotency_keys=executed or set(),
        environment=environment,
        allowed_environments=frozenset({ENVIRONMENT}),
        protected_environments=frozenset({ENVIRONMENT}),
    )
    return decision


# --- the allowed path ------------------------------------------------------


def test_a_fully_authorized_rollback_is_allowed():
    decision = _evaluate(_bundle(approval=_approval()))
    assert decision.allowed is True
    assert decision.veto_codes == []
    assert decision.target_release == "v1"


# --- refusals -------------------------------------------------------------


def test_rollback_without_any_approval_is_refused():
    decision = _evaluate(_bundle(approval=None))
    assert decision.allowed is False
    assert "APPROVAL_PRESENT" in decision.veto_codes


def test_a_denied_approval_is_refused():
    decision = _evaluate(_bundle(approval=_approval(decision=ApprovalDecision.DENIED)))
    assert decision.allowed is False
    assert "APPROVAL_GRANTED" in decision.veto_codes


def test_an_agent_cannot_approve_its_own_rollback():
    """The gate must not accept a non-human actor as the approver."""
    for actor in ("duo", "agent", "system", "rollbackiq", "automation", ""):
        decision = _evaluate(_bundle(approval=_approval(actor=actor)))
        assert decision.allowed is False, f"actor {actor!r} was allowed to approve"
        assert "APPROVAL_ACTOR_IS_HUMAN" in decision.veto_codes


def test_an_approval_for_a_different_proposal_is_refused():
    """A changed proposal invalidates the approval that covered the old one."""
    decision = _evaluate(_bundle(approval=_approval(proposal_hash="deadbeefdeadbeef")))
    assert decision.allowed is False
    assert "APPROVAL_IN_SCOPE" in decision.veto_codes


def test_an_expired_approval_is_refused():
    decision = _evaluate(_bundle(approval=_approval(expires_in=-60.0)))
    assert decision.allowed is False
    assert "APPROVAL_NOT_EXPIRED" in decision.veto_codes


def test_an_environment_outside_the_allowlist_is_refused():
    decision = _evaluate(_bundle(approval=_approval()), environment="production")
    assert decision.allowed is False
    assert "ENVIRONMENT_ALLOWLISTED" in decision.veto_codes


def test_a_duplicate_idempotency_key_is_refused():
    decision = _evaluate(
        _bundle(approval=_approval()), executed={"rollback-inc-1-v1"}
    )
    assert decision.allowed is False
    assert "NOT_ALREADY_EXECUTED" in decision.veto_codes


def test_a_missing_idempotency_key_is_refused():
    decision = _evaluate(_bundle(approval=_approval()), key="")
    assert decision.allowed is False
    assert "IDEMPOTENCY_KEY_PRESENT" in decision.veto_codes


def test_a_target_that_was_never_verified_healthy_is_refused():
    bundle = _bundle(approval=_approval())
    bundle.target_release.known_good = False
    decision = _evaluate(bundle)
    assert decision.allowed is False
    assert "TARGET_IS_KNOWN_GOOD" in decision.veto_codes


# --- target identity -------------------------------------------------------


def test_target_identity_matches_when_the_digest_is_the_approved_one():
    assert ci_rollback.verify_target_identity(_bundle(approval=_approval()), HEALTHY_DIGEST) is None


def test_target_identity_is_refused_when_the_digest_differs():
    """A moved tag must not become a different artifact under the same name."""
    reason = ci_rollback.verify_target_identity(
        _bundle(approval=_approval()), "sha256:" + "c" * 64
    )
    assert reason is not None and "does not match the digest recorded" in reason


def test_target_identity_is_refused_when_the_target_has_no_recorded_digest():
    reason = ci_rollback.verify_target_identity(
        _bundle(approval=_approval(), target_digest="unknown"), HEALTHY_DIGEST
    )
    assert reason is not None and "no recorded image digest" in reason


def test_target_identity_is_refused_when_the_deployed_artifact_has_no_digest():
    reason = ci_rollback.verify_target_identity(_bundle(approval=_approval()), "")
    assert reason is not None and "no resolvable digest" in reason


# --- the idempotency ledger ------------------------------------------------


def test_a_corrupt_ledger_refuses_rather_than_allowing_a_duplicate(tmp_path):
    ledger = tmp_path / "rollback-state.json"
    ledger.write_text("{ this is not json")
    with pytest.raises(SystemExit):
        ci_rollback.load_state(ledger)


def test_the_ledger_records_executed_keys(tmp_path):
    ledger = tmp_path / "rollback-state.json"
    state = ci_rollback.load_state(ledger)
    assert state["executed_idempotency_keys"] == []
    state["executed_idempotency_keys"].append("rollback-inc-1-v1")
    ci_rollback.save_state(ledger, state)
    assert ci_rollback.load_state(ledger)["executed_idempotency_keys"] == ["rollback-inc-1-v1"]


# --- the approval artifact -------------------------------------------------


def _write_bundle(tmp_path: Path) -> Path:
    bundle = _bundle(approval=None)
    path = tmp_path / "incident-bundle.json"
    path.write_text(json.dumps(bundle.model_dump(mode="json")))
    return path


def test_recorded_approval_is_scoped_to_the_proposal_and_names_the_actor(tmp_path):
    bundle_path = _write_bundle(tmp_path)
    out = tmp_path / "approval.json"
    code = ci_incident.main(
        [
            "approve",
            "--bundle", str(bundle_path),
            "--actor", "yablokolabs",
            "--ttl", "900",
            "--out", str(out),
        ]
    )
    assert code == 0
    approval = Approval(**json.loads(out.read_text()))
    bundle = _bundle(approval=None)
    assert approval.actor == "yablokolabs"
    assert approval.proposal_hash == bundle.proposal.proposal_hash
    assert approval.decision is ApprovalDecision.APPROVED
    assert approval.environment == ENVIRONMENT


def test_a_recorded_approval_makes_the_gate_allow_the_rollback(tmp_path):
    """End to end through the artifacts the CI jobs actually exchange."""
    bundle_path = _write_bundle(tmp_path)
    approval_path = tmp_path / "approval.json"
    ci_incident.main(
        [
            "approve",
            "--bundle", str(bundle_path),
            "--actor", "yablokolabs",
            "--out", str(approval_path),
        ]
    )
    combined_path = tmp_path / "approved.json"
    assert ci_incident.main(
        ["combine", "--bundle", str(bundle_path), "--approval", str(approval_path), "--out", str(combined_path)]
    ) == 0

    combined = ci_rollback.load_bundle(combined_path)
    assert _evaluate(combined).allowed is True


def test_a_denial_artifact_leaves_the_gate_refusing(tmp_path):
    bundle_path = _write_bundle(tmp_path)
    approval_path = tmp_path / "approval.json"
    ci_incident.main(
        [
            "approve",
            "--bundle", str(bundle_path),
            "--actor", "yablokolabs",
            "--deny",
            "--out", str(approval_path),
        ]
    )
    combined_path = tmp_path / "denied.json"
    ci_incident.main(
        ["combine", "--bundle", str(bundle_path), "--approval", str(approval_path), "--out", str(combined_path)]
    )
    decision = _evaluate(ci_rollback.load_bundle(combined_path))
    assert decision.allowed is False
    assert "APPROVAL_GRANTED" in decision.veto_codes
