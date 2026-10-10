#!/usr/bin/env python3
"""Gated rollback executor for the GitLab CI rollback job.

This script is the only thing that changes a deployment's release, and it
refuses far more often than it acts. Before it touches anything it runs the
control plane's real :class:`SafetyGate` against the incident bundle, so the
rules that protect the rollback are the same rules the test suite exercises —
the CI job does not get its own, weaker copy.

Order of operations, all fail-closed:

1. Load the incident bundle (proposal, approval, current and target release).
2. Evaluate the safety gate. Any veto refuses the rollback.
3. Resolve the *actual* image identity and require it to match the digest the
   target release was recorded with, so the release that gets deployed is the
   artifact that was verified and approved, not merely the tag that was named.
4. Deploy, measure, and verify recovery from new observations.

``--dry-run`` stops after step 2 and changes nothing, which is how an operator
can inspect the verdict before authorizing the real run.

Honest limitation: the single-flight idempotency ledger is a JSON file next to
the evidence. That makes a re-run inside one pipeline refuse, but it is not a
distributed lock. The gate's contract is unchanged either way, because a
duplicate key is a veto regardless of where the ledger lives.

    python scripts/ci_rollback.py --bundle incident-bundle.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from pydantic import BaseModel, Field  # noqa: E402

from app.models.approval import Approval, RecoveryProposal  # noqa: E402
from app.models.incident import utcnow  # noqa: E402
from app.models.metrics import Baseline, MetricWindow  # noqa: E402
from app.models.release import Release  # noqa: E402
from app.services.safety import SafetyGate, SafetyPolicy  # noqa: E402
from app.services.verifier import VerificationThresholds, verify_recovery  # noqa: E402

#: Exit codes, so the pipeline can tell an unsafe refusal from a broken run.
EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_FAILED = 3


class IncidentBundle(BaseModel):
    """Everything the rollback decision depends on, as one reviewable artifact."""

    incident_id: str
    environment: str
    proposal: RecoveryProposal
    approval: Optional[Approval] = None
    current_release: Optional[Release] = None
    target_release: Optional[Release] = None
    baseline: Optional[Baseline] = None
    before: Optional[MetricWindow] = None
    idempotency_key: str = ""


class RollbackDecision(BaseModel):
    """The gate's verdict plus the two checks that happen around it."""

    allowed: bool
    stage: str
    detail: str
    veto_codes: List[str] = Field(default_factory=list)
    checks: List[Dict[str, object]] = Field(default_factory=list)
    proposal_hash: str = ""
    target_release: Optional[str] = None


def load_bundle(path: Path) -> IncidentBundle:
    return IncidentBundle.model_validate(json.loads(Path(path).read_text()))


def evaluate_gate(
    bundle: IncidentBundle,
    *,
    idempotency_key: str,
    executed_idempotency_keys: Set[str],
    environment: Optional[str] = None,
    allowed_environments: Optional[frozenset] = None,
    protected_environments: Optional[frozenset] = None,
    now: Optional[datetime] = None,
) -> tuple[RollbackDecision, object]:
    """Run the real safety gate.

    Returns the decision and the raw verdict. The decision is deliberately a
    plain summary so it can be written to evidence, while the verdict keeps the
    full per-check detail for an operator.
    """
    environment = environment or bundle.environment
    policy = SafetyPolicy(
        allowed_environments=allowed_environments or frozenset({"demo-staging"}),
        protected_environments=protected_environments or frozenset({"demo-staging"}),
    )
    verdict = SafetyGate(policy).check(
        proposal=bundle.proposal,
        approval=bundle.approval,
        current_release=bundle.current_release,
        target_release=bundle.target_release,
        environment=environment,
        idempotency_key=idempotency_key,
        executed_idempotency_keys=executed_idempotency_keys,
        now=now,
    )
    decision = RollbackDecision(
        allowed=verdict.allowed,
        stage="safety_gate",
        detail=(
            "safety gate allowed the rollback"
            if verdict.allowed
            else "safety gate refused the rollback: " + ", ".join(c.code for c in verdict.vetoes)
        ),
        veto_codes=[c.code for c in verdict.vetoes],
        checks=[{"code": c.code, "passed": c.passed, "detail": c.detail} for c in verdict.checks],
        proposal_hash=verdict.proposal_hash,
        target_release=verdict.target_release,
    )
    return decision, verdict


def verify_target_identity(bundle: IncidentBundle, resolved_digest: str) -> Optional[str]:
    """Require the artifact about to be deployed to be the approved target.

    Returns a refusal reason, or ``None`` when the identity matches. An unknown
    digest on either side is refused rather than assumed equal: this check
    exists precisely because a tag can move.
    """
    target = bundle.target_release
    if target is None:
        return "no target release in the bundle"
    recorded = (target.image_digest or "").strip()
    if not recorded or recorded == "unknown":
        return (
            f"target release {target.id!r} has no recorded image digest, so the artifact "
            "about to be deployed cannot be proven to be the one that was verified"
        )
    if not resolved_digest or resolved_digest == "unknown":
        return "the image being deployed has no resolvable digest, so target identity is unknown"
    if recorded != resolved_digest:
        return (
            f"resolved image digest {resolved_digest!r} does not match the digest recorded for "
            f"target release {target.id!r} ({recorded!r})"
        )
    return None


def load_state(path: Path) -> Dict[str, object]:
    if not Path(path).exists():
        return {"executed_idempotency_keys": []}
    try:
        state = json.loads(Path(path).read_text())
    except json.JSONDecodeError:
        # A corrupt ledger must not become a licence to execute.
        raise SystemExit(
            f"refusing to execute: the idempotency ledger at {path} is unreadable, so a "
            "duplicate rollback cannot be ruled out"
        )
    state.setdefault("executed_idempotency_keys", [])
    return state


def save_state(path: Path, state: Dict[str, object]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(state, indent=2) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RollbackIQ gated rollback")
    parser.add_argument("--bundle", required=True, help="incident bundle JSON")
    parser.add_argument("--idempotency-key", default="", help="overrides the bundle's key")
    parser.add_argument("--environment", default="")
    parser.add_argument("--allowed-environments", default="demo-staging")
    parser.add_argument("--protected-environments", default="demo-staging")
    parser.add_argument("--state", default="evidence/rollback-state.json")
    parser.add_argument("--out", default="evidence/rollback-execution.json")
    parser.add_argument("--image", default="", help="image reference to deploy (required to execute)")
    parser.add_argument("--container", default="rollbackiq-workload")
    parser.add_argument("--network", default="rollbackiq-ci")
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument(
        "--post-min-duration",
        type=float,
        default=6.0,
        help=(
            "pace the post-rollback window so it spans at least this many seconds; a burst "
            "that finishes in a second is not a stabilization window and the verifier will "
            "correctly refuse it"
        ),
    )
    parser.add_argument("--post-window-out", default="evidence/rollback-post-window.json")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    bundle_path = _resolve(args.bundle)
    if not bundle_path.exists():
        print(f"no incident bundle at {bundle_path}", file=sys.stderr)
        return EXIT_FAILED

    bundle = load_bundle(bundle_path)
    idempotency_key = args.idempotency_key or bundle.idempotency_key
    state_path = _resolve(args.state)
    state = load_state(state_path)
    executed: Set[str] = set(state["executed_idempotency_keys"])  # type: ignore[arg-type]

    decision, verdict = evaluate_gate(
        bundle,
        idempotency_key=idempotency_key,
        executed_idempotency_keys=executed,
        environment=args.environment or None,
        allowed_environments=frozenset(filter(None, args.allowed_environments.split(","))),
        protected_environments=frozenset(filter(None, args.protected_environments.split(","))),
    )

    record: Dict[str, object] = {
        "incident_id": bundle.incident_id,
        "environment": args.environment or bundle.environment,
        "idempotency_key": idempotency_key,
        "dry_run": bool(args.dry_run),
        "decision": decision.model_dump(mode="json"),
        "safety_verdict": verdict.model_dump(mode="json"),  # type: ignore[attr-defined]
        "evaluated_at": utcnow().isoformat(),
    }

    print(json.dumps(decision.model_dump(mode="json"), indent=2))
    for check in decision.checks:
        mark = "pass" if check["passed"] else "VETO"
        print(f"  [{mark}] {check['code']}: {check['detail']}")

    if not decision.allowed:
        record["outcome"] = "refused"
        _write(args.out, record)
        print("\nREFUSED: no deployment change was made.", file=sys.stderr)
        return EXIT_REFUSED

    if args.dry_run:
        record["outcome"] = "dry_run_allowed"
        _write(args.out, record)
        print("\nDRY RUN: gate allows the rollback; nothing was changed.")
        return EXIT_OK

    if not args.image:
        record["outcome"] = "failed"
        record["failure"] = "no --image supplied, so there is no artifact to deploy"
        _write(args.out, record)
        print("cannot execute: no --image supplied", file=sys.stderr)
        return EXIT_FAILED

    # Imported here so the refusal path never needs docker on PATH.
    import ci_release  # type: ignore[import-not-found]

    resolved = ci_release.image_digest(args.image)
    mismatch = verify_target_identity(bundle, resolved)
    record["resolved_image_digest"] = resolved
    record["approved_target_digest"] = (bundle.target_release.image_digest if bundle.target_release else None)
    if mismatch:
        record["outcome"] = "refused"
        record["failure"] = mismatch
        _write(args.out, record)
        print(f"\nREFUSED: {mismatch}", file=sys.stderr)
        return EXIT_REFUSED

    executed_at = utcnow()
    record["executed_at"] = executed_at.isoformat()

    deploy_code = ci_release.cmd_deploy(
        argparse.Namespace(
            image=args.image,
            release=(bundle.target_release.id if bundle.target_release else "unknown"),
            container=args.container,
            network=args.network,
            environment=args.environment or bundle.environment,
            commit_sha=(bundle.target_release.commit_sha if bundle.target_release else "unknown"),
            pipeline_id=(bundle.target_release.pipeline_id if bundle.target_release else "unknown"),
            digest=resolved,
            fault_latency="0",
            fault_error_rate="0",
            health_timeout=60.0,
            out="",
        )
    )
    if deploy_code != 0:
        record["outcome"] = "failed"
        record["failure"] = "deploying the target release failed; the incident must escalate"
        _write(args.out, record)
        return EXIT_FAILED

    post = _resolve(args.post_window_out)
    probe_code = ci_release.cmd_probe(
        argparse.Namespace(
            target=f"{args.container}:8000",
            samples=args.samples,
            concurrency=args.concurrency,
            environment=args.environment or bundle.environment,
            expect_release=(bundle.target_release.id if bundle.target_release else ""),
            expect_healthy=False,
            max_error_rate=0.05,
            min_duration=args.post_min_duration,
            in_container=args.image,
            network=args.network,
            out=post,
        )
    )

    verification = None
    if bundle.baseline is not None and post.exists():
        after = MetricWindow(**json.loads(post.read_text()))
        verification = verify_recovery(
            expected_release=(bundle.target_release.id if bundle.target_release else "unknown"),
            after=after,
            baseline=bundle.baseline,
            executed_at=executed_at,
            before=bundle.before,
            thresholds=VerificationThresholds(
                p95_tolerance_multiplier=1.5,
                max_error_rate=0.02,
                min_samples=30,
                stabilization_seconds=3.0,
            ),
        )
        record["verification"] = verification.model_dump(mode="json")
        record["post_rollback_window"] = after.model_dump(mode="json")

    # Only a rollback that actually ran consumes its key.
    state["executed_idempotency_keys"].append(idempotency_key)  # type: ignore[union-attr]
    save_state(state_path, state)

    record["outcome"] = "executed"
    record["probe_exit_code"] = probe_code
    _write(args.out, record)

    if verification is not None:
        print(f"\nverification: recovered={verification.recovered} reasons={verification.reasons}")
        if not verification.recovered:
            print(
                "rollback executed but recovery is NOT verified; the incident must not be "
                "closed by this job",
                file=sys.stderr,
            )
            return EXIT_OK  # the dedicated verify job owns the failure verdict

    print("\nexecuted: the rollback ran and its evidence is recorded.")
    return EXIT_OK


def _write(path: str, record: Dict[str, object]) -> None:
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2) + "\n")
    try:
        shown: Path = target.relative_to(REPO_ROOT)
    except ValueError:
        shown = target
    print(f"written: {shown}")


if __name__ == "__main__":
    sys.exit(main())
