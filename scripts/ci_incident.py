#!/usr/bin/env python3
"""Incident artifacts for the CI deploy, approval and rollback jobs.

GitLab CI jobs run on separate, ephemeral runners, so the state that has to
survive from one stage to the next travels as job artifacts rather than as a
live deployment. This script builds those artifacts:

    regress  deploy the regressed release, measure it, and require the real
             detector to fire before an incident bundle is written
    approve  record a human approval for one exact proposal
    combine  merge an approval into a bundle for the rollback job

Two things are deliberate. First, ``regress`` will not invent a regression: if
the detector does not fire on the measured window it exits non-zero and writes
no bundle. Second, the approver identity comes from GitLab's
``GITLAB_USER_LOGIN`` for the user who actually played the manual job, so an
approval names a real person instead of a value this script chose.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from app.models.approval import (  # noqa: E402
    Approval,
    ApprovalDecision,
    ProposedAction,
    RecoveryProposal,
)
from app.models.incident import utcnow  # noqa: E402
from app.models.metrics import Baseline, MetricWindow  # noqa: E402
from app.models.release import Release  # noqa: E402
from app.services.detector import RegressionDetector  # noqa: E402
from ci_rollback import IncidentBundle  # noqa: E402

HEALTHY_RELEASE = "v1"
REGRESSED_RELEASE = "v2"


def _resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def _write(path: str, payload: object) -> None:
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"written: {_display(target)}")


def _display(target: Path) -> Path:
    """Repo-relative when the path is inside the repo, absolute otherwise."""
    try:
        return target.relative_to(REPO_ROOT)
    except ValueError:
        return target


def _window(path: str) -> MetricWindow:
    return MetricWindow(**json.loads(_resolve(path).read_text()))


def cmd_regress(args: argparse.Namespace) -> int:
    import ci_release

    import argparse as ap

    if not args.image:
        print("--image is required", file=sys.stderr)
        return 3

    container = args.container
    ci_release.cmd_deploy(
        ap.Namespace(
            image=args.image,
            release=REGRESSED_RELEASE,
            container=container,
            network=args.network,
            environment=args.environment,
            commit_sha=args.commit_sha,
            pipeline_id=args.pipeline_id,
            digest=args.digest,
            fault_latency=args.fault_latency,
            fault_error_rate=args.fault_error_rate,
            health_timeout=60.0,
            out=args.deploy_out,
        )
    )

    baseline_window = _window(args.baseline)
    baseline = Baseline.from_window(baseline_window, min_samples=args.min_samples, max_error_rate=0.05)

    detector = RegressionDetector()
    windows = []
    decision = None
    # The detector requires a sustained breach, so it is fed consecutive real
    # windows until it fires or the budget runs out.
    for attempt in range(args.max_windows):
        probe_out = str(_resolve(args.workdir) / f"faulty-window-{attempt + 1}.json")
        code = ci_release.cmd_probe(
            ap.Namespace(
                target=f"{container}:8000",
                samples=args.samples,
                concurrency=args.concurrency,
                environment=args.environment,
                expect_release="",
                expect_healthy=False,
                max_error_rate=0.05,
                in_container=args.image,
                network=args.network,
                out=probe_out,
            )
        )
        if code != 0:
            print(f"probe of the regressed release failed (exit {code})", file=sys.stderr)
            return 3
        window = _window(probe_out)
        windows.append(window)
        decision = detector.evaluate(window, baseline)
        print(
            f"window {attempt + 1}: samples={window.request_count} errors={window.error_count} "
            f"error_rate={window.error_rate:.1%} p95={window.p95_ms:.1f}ms "
            f"ratio={decision.p95_ratio} triggered={decision.triggered}"
            + (f" ({decision.suppressed_reason})" if not decision.triggered else "")
        )
        if decision.triggered:
            break

    if decision is None or not decision.triggered:
        # Refusing here is the point: an incident bundle is evidence that a
        # regression was observed, so it must not be written speculatively.
        print(
            "no regression detected on the measured windows; no incident bundle written",
            file=sys.stderr,
        )
        _write(
            args.detection_out,
            {
                "triggered": False,
                "note": "the detector did not fire, so no incident or rollback was proposed",
                "windows": [w.model_dump(mode="json") for w in windows],
                "baseline_release": baseline.release,
            },
        )
        return 1

    incident_id = args.incident_id or f"inc-{REGRESSED_RELEASE}-{decision.evaluated_at:%Y%m%d%H%M%S}"
    proposal = RecoveryProposal(
        incident_id=incident_id,
        action=ProposedAction.ROLLBACK,
        target_release=HEALTHY_RELEASE,
        environment=args.environment,
        requires_migration=False,
        risks=[
            "rolling back the deployment does not restore any data deleted by the regressed release",
            "the regressed release remains in the pipeline history and must not be redeployed unreviewed",
        ],
        evidence_refs=[str(Path(args.deploy_out)), str(Path(args.workdir))],
        expected_recovery=(
            f"p95 latency within {args.baseline} envelope and error rate below the recovery limit"
        ),
    )

    current = Release(
        id=REGRESSED_RELEASE,
        commit_sha=args.commit_sha,
        pipeline_id=args.pipeline_id,
        environment=args.environment,
        image_digest=args.digest,
        known_good=False,
    )
    target = Release(
        id=HEALTHY_RELEASE,
        commit_sha=args.healthy_commit_sha,
        pipeline_id=args.healthy_pipeline_id,
        environment=args.environment,
        image_digest=args.healthy_digest,
        # Set because this release was observed healthy by the deploy job and a
        # baseline was captured from it, not because a caller asserted it.
        known_good=True,
        migration_compatible=True,
    )

    bundle = IncidentBundle(
        incident_id=incident_id,
        environment=args.environment,
        proposal=proposal,
        approval=None,
        current_release=current,
        target_release=target,
        baseline=baseline,
        before=windows[-1],
        idempotency_key=f"rollback-{incident_id}-{HEALTHY_RELEASE}",
    )
    _write(args.out, bundle.model_dump(mode="json"))
    _write(
        args.detection_out,
        {
            "triggered": True,
            "incident_id": incident_id,
            "breaches": decision.breaches,
            "reasons": decision.reasons,
            "confidence": decision.confidence,
            "confidence_note": decision.confidence_note,
            "p95_ratio": decision.p95_ratio,
            "windows": [w.model_dump(mode="json") for w in windows],
            "baseline": baseline.model_dump(mode="json"),
            "proposal_hash": proposal.proposal_hash,
        },
    )
    print(f"\nincident {incident_id}: {', '.join(decision.breaches)}")
    print(f"proposal {proposal.action.value} -> {proposal.target_release} (hash {proposal.proposal_hash})")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    bundle = IncidentBundle.model_validate(json.loads(_resolve(args.bundle).read_text()))
    now = utcnow()
    decision = ApprovalDecision.DENIED if args.deny else ApprovalDecision.APPROVED
    approval = Approval(
        id=args.approval_id or f"appr-{bundle.incident_id}",
        incident_id=bundle.incident_id,
        proposal_hash=bundle.proposal.proposal_hash,
        actor=args.actor,
        decision=decision,
        environment=bundle.environment,
        created_at=now,
        expires_at=now + __import__("datetime").timedelta(seconds=args.ttl),
        scope_note=args.note,
    )
    _write(args.out, approval.model_dump(mode="json"))
    print(f"approval {approval.id}: {decision.value} by {approval.actor!r} for proposal {approval.proposal_hash}")
    return 0


def cmd_combine(args: argparse.Namespace) -> int:
    bundle = IncidentBundle.model_validate(json.loads(_resolve(args.bundle).read_text()))
    approval = Approval.model_validate(json.loads(_resolve(args.approval).read_text()))
    bundle.approval = approval
    _write(args.out, bundle.model_dump(mode="json"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RollbackIQ CI incident artifacts")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("regress", help="deploy the regressed release and require a real detection")
    p.add_argument("--image", required=True)
    p.add_argument("--container", default="rollbackiq-workload-v2")
    p.add_argument("--network", default="rollbackiq-ci")
    p.add_argument("--environment", default="demo-staging")
    p.add_argument("--commit-sha", default="unknown")
    p.add_argument("--pipeline-id", default="unknown")
    p.add_argument("--digest", default="unknown")
    p.add_argument("--healthy-commit-sha", default="unknown")
    p.add_argument("--healthy-pipeline-id", default="unknown")
    p.add_argument("--healthy-digest", default="unknown")
    p.add_argument("--baseline", default="evidence/baseline-window.json")
    p.add_argument("--workdir", default="evidence")
    p.add_argument("--samples", type=int, default=120)
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--min-samples", type=int, default=20)
    p.add_argument("--max-windows", type=int, default=4)
    p.add_argument("--fault-latency", default="180")
    p.add_argument("--fault-error-rate", default="0.10")
    p.add_argument("--incident-id", default="")
    p.add_argument("--deploy-out", default="evidence/deploy-regressed.json")
    p.add_argument("--detection-out", default="evidence/ci-detection.json")
    p.add_argument("--out", default="evidence/incident-bundle.json")
    p.set_defaults(func=cmd_regress)

    p = sub.add_parser("approve", help="record a human approval for one exact proposal")
    p.add_argument("--bundle", default="evidence/incident-bundle.json")
    p.add_argument("--actor", required=True, help="approver identity, from GITLAB_USER_LOGIN")
    p.add_argument("--approval-id", default="")
    p.add_argument("--ttl", type=float, default=900.0, help="validity window in seconds")
    p.add_argument("--note", default="")
    p.add_argument("--deny", action="store_true", help="record a denial instead of an approval")
    p.add_argument("--out", default="evidence/approval.json")
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("combine", help="merge an approval into a bundle")
    p.add_argument("--bundle", default="evidence/incident-bundle.json")
    p.add_argument("--approval", default="evidence/approval.json")
    p.add_argument("--out", default="evidence/incident-bundle-approved.json")
    p.set_defaults(func=cmd_combine)

    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
