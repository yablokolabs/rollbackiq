"""Safety gate.

Every rule here exists to make the destructive path refuse, not to make it
convenient. Checks are evaluated independently and *all* of them are reported in
the verdict, so an operator sees every reason a rollback was refused instead of
only the first one.

A rollback executes only when the verdict has no vetoes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, FrozenSet, List, Optional, Set

from pydantic import BaseModel, Field

from ..models.approval import NON_HUMAN_ACTORS, Approval, ApprovalDecision, ProposedAction, RecoveryProposal
from ..models.incident import utcnow
from ..models.release import Release


class CheckOutcome(BaseModel):
    code: str
    passed: bool
    detail: str


class SafetyVerdict(BaseModel):
    allowed: bool
    target_release: Optional[str] = None
    proposal_hash: str
    checks: List[CheckOutcome] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=utcnow)

    @property
    def vetoes(self) -> List[CheckOutcome]:
        return [c for c in self.checks if not c.passed]

    def to_audit_context(self) -> Dict[str, str]:
        return {
            "allowed": str(self.allowed),
            "target_release": str(self.target_release),
            "proposal_hash": self.proposal_hash,
            "veto_codes": ",".join(c.code for c in self.vetoes),
        }


@dataclass(frozen=True)
class SafetyPolicy:
    """Operator-controlled policy inputs for the gate."""

    allowed_environments: FrozenSet[str] = field(default_factory=lambda: frozenset({"demo-staging"}))
    #: Environments whose deployments this controller is permitted to change.
    protected_environments: FrozenSet[str] = field(default_factory=lambda: frozenset({"demo-staging"}))
    max_approval_age_seconds: float = 900.0


class SafetyGate:
    def __init__(self, policy: Optional[SafetyPolicy] = None) -> None:
        self.policy = policy or SafetyPolicy()

    def check(
        self,
        *,
        proposal: RecoveryProposal,
        approval: Optional[Approval],
        current_release: Optional[Release],
        target_release: Optional[Release],
        environment: str,
        idempotency_key: Optional[str],
        executed_idempotency_keys: Set[str],
        now: Optional[datetime] = None,
    ) -> SafetyVerdict:
        now = now or utcnow()
        checks: List[CheckOutcome] = []

        def check(
            code: str,
            passed: bool,
            on_fail: str,
            on_pass: Optional[Callable[[], str]] = None,
        ) -> None:
            """Record one check.

            The detail must describe the outcome that actually occurred. A refusal
            has to stay readable as a refusal, but a passing check must not carry
            its failure wording — otherwise the verdict an operator reads
            contradicts its own ``passed`` field, which is how a passing actor
            check came to be rendered as "actor is not an authorized human
            identity". Phrasing that reads correctly either way is passed once
            and reused.

            ``on_pass`` is a callable rather than a string because it describes
            state that only exists when the check passes: a plain f-string would
            also be evaluated for a failing check and raise on the very object
            whose absence is the failure.
            """
            detail = on_fail
            if passed and on_pass is not None:
                detail = on_pass()
            checks.append(CheckOutcome(code=code, passed=passed, detail=detail))

        # 1. Only a rollback action reaches execution. "hold" and "escalate" are
        #    legitimate proposals that must never trigger a deployment change.
        check(
            "ACTION_IS_ROLLBACK",
            proposal.action is ProposedAction.ROLLBACK,
            f"proposed action is {proposal.action.value!r}; only 'rollback' executes a deployment change",
        )

        # 2. Environment must be one this controller is authorized to touch.
        check(
            "ENVIRONMENT_ALLOWLISTED",
            environment in self.policy.allowed_environments,
            f"environment {environment!r} allowlist={sorted(self.policy.allowed_environments)}",
        )
        check(
            "PHASE1_ENVIRONMENT_ALLOWLISTED",
            environment in self.policy.protected_environments,
            f"environment {environment!r} protected allowlist={sorted(self.policy.protected_environments)}",
        )

        # 3. The proposal must describe the environment we are actually in.
        check(
            "PROPOSAL_ENVIRONMENT_MATCHES",
            proposal.environment == environment,
            f"proposal environment {proposal.environment!r} vs request environment {environment!r}",
        )

        # 4. Current release must be known: without it, target identity and
        #    no-op detection are guesses.
        check(
            "CURRENT_RELEASE_KNOWN",
            current_release is not None,
            "current deployed release is unknown, so rollback effect cannot be predicted",
            lambda: f"current deployed release is {current_release.id!r}",
        )

        # 5. Target must exist, be known-good, and differ from the current release.
        check(
            "TARGET_RELEASE_KNOWN",
            target_release is not None,
            f"rollback target {proposal.target_release!r} is not a release we have observed",
            lambda: f"rollback target {target_release.id!r} is a release we have observed",
        )
        check(
            "TARGET_IS_KNOWN_GOOD",
            bool(target_release and target_release.known_good),
            "rollback target has not been verified healthy by this system",
            lambda: f"rollback target {target_release.id!r} was verified healthy by this system",
        )
        check(
            "TARGET_DIFFERS_FROM_CURRENT",
            bool(
                target_release
                and current_release
                and target_release.id != current_release.id
            ),
            "rollback target is the release that is already deployed",
            lambda: (
                f"rollback target {target_release.id!r} differs from the deployed "
                f"release {current_release.id!r}"
            ),
        )
        check(
            "TARGET_ENVIRONMENT_MATCHES",
            bool(target_release and target_release.environment == environment),
            f"target release environment {getattr(target_release, 'environment', None)!r} "
            f"vs {environment!r}",
        )

        # 6. Migration compatibility. Unknown is treated as unsafe.
        if proposal.requires_migration and target_release is not None:
            compatible = target_release.migration_compatible is True
            check(
                "MIGRATION_COMPATIBLE",
                compatible,
                "proposal requires a migration and target compatibility is "
                f"{target_release.migration_compatible!r}; unknown is refused",
                lambda: "proposal requires a migration and target compatibility is "
                f"{target_release.migration_compatible!r}",
            )

        # 7. Approval: present, an actual human, in scope, unexpired.
        check(
            "APPROVAL_PRESENT",
            approval is not None,
            "no approval record supplied",
            lambda: f"approval {approval.id!r} supplied",
        )
        if approval is not None:
            check(
                "APPROVAL_ACTOR_IS_HUMAN",
                approval.actor.strip().lower() not in NON_HUMAN_ACTORS,
                f"approval actor {approval.actor!r} is not an authorized human identity",
                lambda: f"approval actor {approval.actor!r} is an authorized human identity",
            )
            check(
                "APPROVAL_GRANTED",
                approval.decision is ApprovalDecision.APPROVED,
                f"approval decision is {approval.decision.value}",
            )
            check(
                "APPROVAL_IN_SCOPE",
                approval.proposal_hash == proposal.proposal_hash,
                "approval was granted for a different proposal; the proposal changed after approval",
                lambda: f"approval matches proposal {proposal.proposal_hash}",
            )
            check(
                "APPROVAL_ENVIRONMENT_MATCHES",
                approval.environment == environment,
                f"approval environment {approval.environment!r} vs {environment!r}",
            )
            check(
                "APPROVAL_NOT_EXPIRED",
                not approval.is_expired(now),
                f"approval expires_at={approval.expires_at.isoformat() if approval.expires_at else None}",
            )
            if approval.expires_at is not None:
                age = (approval.expires_at - approval.created_at).total_seconds()
                check(
                    "APPROVAL_WITHIN_MAX_AGE",
                    age <= self.policy.max_approval_age_seconds,
                    f"approval validity window {age:.0f}s exceeds "
                    f"{self.policy.max_approval_age_seconds:.0f}s",
                    lambda: f"approval validity window {age:.0f}s is within "
                    f"{self.policy.max_approval_age_seconds:.0f}s",
                )

        # 8. Idempotency: a single-flight key must be present and unused.
        check(
            "IDEMPOTENCY_KEY_PRESENT",
            bool(idempotency_key and idempotency_key.strip()),
            "rollback requires an idempotency key",
            lambda: f"idempotency key {idempotency_key!r} present",
        )
        check(
            "NOT_ALREADY_EXECUTED",
            not (idempotency_key and idempotency_key in executed_idempotency_keys),
            f"idempotency key {idempotency_key!r} has already been executed",
            lambda: f"idempotency key {idempotency_key!r} has not been executed",
        )

        allowed = all(c.passed for c in checks)
        return SafetyVerdict(
            allowed=allowed,
            target_release=proposal.target_release,
            proposal_hash=proposal.proposal_hash,
            checks=checks,
            checked_at=now,
        )
