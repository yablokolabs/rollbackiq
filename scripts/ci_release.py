#!/usr/bin/env python3
"""Release control for the GitLab CI deploy jobs.

The deployment itself is a `docker run` of a pinned image, so the thing a
rollback changes is an image identity rather than a build. Everything the
workload needs about itself — release label, commit sha, pipeline id, image
digest, and any injected fault — arrives as environment variables, which is
what makes "roll back to the previous release" a change of deployment inputs.

This script is the single place the deploy jobs shell out to, so the same
commands run in a GitLab job and on a developer's machine.

Subcommands:

    digest --image IMG
    deploy --image IMG --release v1 --container NAME [--network NET] [...]
    stop   --container NAME
    probe  --target host:port [--in-container IMG --network NET] --out PATH
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
PROBE_SCRIPT = REPO_ROOT / "scripts" / "ci_probe.py"
DEFAULT_NETWORK = "rollbackiq-ci"

#: Environment variables forwarded into the release container when present.
#: Secrets are not in this list, and none of these are credentials.
PASSTHROUGH = (
    "OTEL_ENABLED",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_SERVICE_NAME",
    "CI_PROJECT_ID",
    "CI_PROJECT_NAME",
    "CI_ENVIRONMENT_NAME",
    "CI_PIPELINE_ID",
    "CI_JOB_ID",
    "FAULT_SEED",
    "BASE_LATENCY_MS",
)


def run(cmd: List[str], *, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    printable = " ".join(shlex.quote(part) for part in cmd)
    # The trace goes to stderr, not stdout: ``ci_release.py digest`` is read into
    # a shell variable, and a trace on stdout silently becomes part of the value
    # it returns -- which then fails the digest check for a reason that looks
    # nothing like the cause. GitLab captures both streams, so job logs are
    # unaffected.
    print(f"+ {printable}", file=sys.stderr, flush=True)
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def image_digest(image: str) -> str:
    """Resolve the immutable identity of an image reference."""
    result = run(["docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}", image], check=False)
    digest = (result.stdout or "").strip()
    if result.returncode == 0 and "@sha256:" in digest:
        return digest.split("@", 1)[1]
    # A locally built image that was never pushed has no RepoDigest; the image
    # id is still a stable identity for that build, so report it as such rather
    # than pretending a digest exists.
    fallback = run(["docker", "image", "inspect", "--format", "{{.Id}}", image], check=False)
    return (fallback.stdout or "").strip()


def ensure_network(network: str) -> None:
    inspect = run(["docker", "network", "inspect", network], check=False)
    if inspect.returncode != 0:
        run(["docker", "network", "create", network])


def _container_release(container: str) -> Optional[str]:
    """Ask the container about itself from inside it.

    The job process is not attached to the release network, so the container's
    own address does not resolve here — in CI the job and the docker-in-docker
    daemon are separate containers too. Reading ``/release`` over ``docker exec``
    works in both places and is a stronger check anyway, because it is the
    service answering about itself.
    """
    result = run(
        [
            "docker", "exec", container, "python", "-c",
            "import urllib.request;"
            "print(urllib.request.urlopen('http://127.0.0.1:8000/release', timeout=2).read().decode())",
        ],
        check=False,
    )
    if result.returncode != 0:
        return None
    for line in reversed((result.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return str(json.loads(line).get("release"))
            except json.JSONDecodeError:
                return None
    return None


def wait_for_release(container: str, release: str, timeout: float) -> None:
    deadline = time.time() + timeout
    last = "no response"
    while time.time() < deadline:
        seen = _container_release(container)
        if seen == release:
            return
        last = f"serving {seen!r}" if seen else "not answering yet"
        time.sleep(0.3)
    raise SystemExit(
        f"release {release!r} did not become healthy inside container {container!r} "
        f"within {timeout}s (last: {last})"
    )


def cmd_digest(args: argparse.Namespace) -> int:
    print(image_digest(args.image))
    return 0


def cmd_deploy(args: argparse.Namespace) -> int:
    if args.network:
        ensure_network(args.network)

    run(["docker", "rm", "-f", args.container], check=False)

    cmd = ["docker", "run", "-d", "--name", args.container]
    if args.network:
        cmd += ["--network", args.network, "--network-alias", args.container]
    for key in PASSTHROUGH:
        if os.environ.get(key):
            cmd += ["-e", key]
    cmd += [
        "-e", f"RELEASE_VERSION={args.release}",
        "-e", f"RELEASE_COMMIT_SHA={args.commit_sha}",
        "-e", f"RELEASE_PIPELINE_ID={args.pipeline_id}",
        "-e", f"RELEASE_IMAGE_DIGEST={args.digest}",
        "-e", f"DEPLOY_ENV={args.environment}",
        "-e", f"FAULT_LATENCY_MS={args.fault_latency}",
        "-e", f"FAULT_ERROR_RATE={args.fault_error_rate}",
        args.image,
    ]
    run(cmd)

    wait_for_release(args.container, args.release, args.health_timeout)
    print(f"deployed {args.release} as container {args.container!r} (image digest {args.digest})")

    record = {
        "action": "deploy",
        "release": args.release,
        "environment": args.environment,
        "container": args.container,
        "image": args.image,
        "image_digest": args.digest,
        "commit_sha": args.commit_sha,
        "pipeline_id": args.pipeline_id,
        "fault_latency_ms": args.fault_latency,
        "fault_error_rate": args.fault_error_rate,
        "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record, indent=2) + "\n")
        print(f"written: {out}")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    result = run(["docker", "rm", "-f", args.container], check=False)
    # Stopping an already-absent container is a no-op, not a failure: the
    # jobs must be safe to re-run.
    print("stopped" if result.returncode == 0 else "container was not running")
    return 0


def _probe_arguments(args: argparse.Namespace, *, machine_readable: bool) -> List[str]:
    probe_args = [
        "--url", f"http://{args.target}",
        "--samples", str(args.samples),
        "--concurrency", str(args.concurrency),
        "--environment", args.environment,
    ]
    if args.expect_release:
        probe_args += ["--expect-release", args.expect_release]
    if args.expect_healthy:
        probe_args += ["--expect-healthy", "--max-error-rate", str(args.max_error_rate)]
    if getattr(args, "min_duration", 0):
        probe_args += ["--min-duration", str(args.min_duration)]
    if machine_readable:
        probe_args.append("--json")
    return probe_args


def _write_evidence(out: str, body: str) -> None:
    target = Path(out)
    if not target.is_absolute():
        target = REPO_ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body)
    print(f"written: {target}")


def cmd_probe(args: argparse.Namespace) -> int:
    if args.in_container:
        # The probe runs inside a container on the same docker network as the
        # workload, so nothing depends on how a runner surfaces published
        # ports. A bind mount is deliberately not used: under dind a mount
        # resolves on the daemon's filesystem, not the job's, so the repo would
        # not be there. Instead the stdlib probe source is passed inline and the
        # window comes back on stdout, which means the code path exercised in CI
        # is the same file a developer runs locally.
        cmd = [
            "docker", "run", "--rm",
            "--network", args.network,
            args.in_container,
            "python", "-c", PROBE_SCRIPT.read_text(),
            *_probe_arguments(args, machine_readable=True),
        ]
        print(
            f"+ docker run --rm --network {args.network} {args.in_container} "
            f"python -c <{PROBE_SCRIPT.name}> ...",
            flush=True,
        )
        completed = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        window_json = ""
        for line in (completed.stdout or "").splitlines():
            if line.lstrip().startswith("{"):
                window_json = line.strip()
            elif line.strip():
                print(line)
        if (completed.stderr or "").strip():
            print((completed.stderr or "").strip(), file=sys.stderr)
        # The probe prints the window before applying its expectations, so a
        # non-zero exit still carries the measurement that caused it.
        if args.out and window_json:
            _write_evidence(args.out, window_json + "\n")
        if not window_json:
            print("the probe produced no window", file=sys.stderr)
            return completed.returncode or 1
        return completed.returncode

    cmd = [sys.executable, str(PROBE_SCRIPT), *_probe_arguments(args, machine_readable=False)]
    if args.out and not Path(args.out).is_absolute():
        args.out = str(REPO_ROOT / args.out)
    if args.out:
        cmd += ["--out", args.out]
    return run(cmd, check=False).returncode


def cmd_verify(args: argparse.Namespace) -> int:
    """Independent recovery verification over a *new* post-rollback window.

    This is a separate job from the rollback on purpose: a deployment job that
    reports its own success is not evidence, so the verdict is computed here
    from a window measured after the rollback ran.
    """
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.models.metrics import Baseline, MetricWindow  # noqa: PLC0415
    from app.services.verifier import VerificationThresholds, verify_recovery  # noqa: PLC0415

    def load(path: str):
        return json.loads(Path(path if Path(path).is_absolute() else REPO_ROOT / path).read_text())

    def write(payload: object) -> None:
        target = Path(args.out)
        if not target.is_absolute():
            target = REPO_ROOT / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"written: {target}")

    # The baseline artifact is the raw healthy *window* the deploy job measured,
    # so the reference is built from it here rather than trusted as a label.
    baseline = Baseline.from_window(
        MetricWindow(**load(args.baseline)),
        min_samples=args.baseline_min_samples,
        max_error_rate=args.baseline_max_error_rate,
    )
    if not baseline.verified:
        # Fail closed: an unverified baseline cannot certify a recovery, so this
        # refuses rather than comparing against a reference that is not sound.
        print(
            f"refusing to verify: the baseline window is not trustworthy "
            f"(samples={baseline.sample_count}, error_rate={baseline.window.error_rate:.3%}); "
            "recovery cannot be certified against an unverified baseline",
            file=sys.stderr,
        )
        return 1

    after = MetricWindow(**load(args.after))
    executed_at = None
    if args.executed_at:
        executed_at = datetime.fromisoformat(args.executed_at.replace("Z", "+00:00"))
    elif args.rollback_evidence:
        evidence = load(args.rollback_evidence)
        raw = evidence.get("executed_at")
        executed_at = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None

    result = verify_recovery(
        expected_release=args.expected_release,
        after=after,
        baseline=baseline,
        executed_at=executed_at,
        thresholds=VerificationThresholds(
            p95_tolerance_multiplier=args.p95_tolerance,
            max_error_rate=args.max_error_rate,
            min_samples=args.min_samples,
            stabilization_seconds=args.stabilization_seconds,
        ),
    )
    payload = {
        "verified_with": "scripts/ci_release.py verify",
        "baseline_source": args.baseline,
        "window_source": args.after,
        "executed_at": executed_at.isoformat() if executed_at else None,
        "result": result.model_dump(mode="json"),
    }
    write(payload)
    print(f"recovered={result.recovered} independent={result.independent} reasons={result.reasons}")
    if not result.recovered:
        print("RECOVERY NOT VERIFIED: the pipeline must not report success", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RollbackIQ CI release control")
    sub = parser.add_subparsers(dest="command", required=True)

    p_digest = sub.add_parser("digest", help="print the immutable identity of an image")
    p_digest.add_argument("--image", required=True)
    p_digest.set_defaults(func=cmd_digest)

    p_deploy = sub.add_parser("deploy", help="start a release as a container")
    p_deploy.add_argument("--image", required=True)
    p_deploy.add_argument("--release", required=True)
    p_deploy.add_argument("--container", required=True)
    p_deploy.add_argument("--network", default=DEFAULT_NETWORK)
    p_deploy.add_argument("--environment", default="demo-staging")
    p_deploy.add_argument("--commit-sha", default="local")
    p_deploy.add_argument("--pipeline-id", default="local")
    p_deploy.add_argument("--digest", default="unknown")
    p_deploy.add_argument("--fault-latency", default="0")
    p_deploy.add_argument("--fault-error-rate", default="0")
    p_deploy.add_argument("--health-timeout", type=float, default=45.0)
    p_deploy.add_argument("--out", default="")
    p_deploy.set_defaults(func=cmd_deploy)

    p_stop = sub.add_parser("stop", help="remove a release container")
    p_stop.add_argument("--container", required=True)
    p_stop.set_defaults(func=cmd_stop)

    p_probe = sub.add_parser("probe", help="independently measure a running release")
    p_probe.add_argument("--target", required=True, help="host:port reachable from here or from the probe container")
    p_probe.add_argument("--samples", type=int, default=120)
    p_probe.add_argument("--concurrency", type=int, default=8)
    p_probe.add_argument("--environment", default="demo-staging")
    p_probe.add_argument("--expect-release", default="")
    p_probe.add_argument("--expect-healthy", action="store_true")
    p_probe.add_argument("--max-error-rate", type=float, default=0.05)
    p_probe.add_argument(
        "--min-duration",
        type=float,
        default=0.0,
        help="pace the requests so the window spans at least this many seconds",
    )
    p_probe.add_argument("--in-container", default="", help="image to run the probe inside (used in CI)")
    p_probe.add_argument("--network", default=DEFAULT_NETWORK)
    p_probe.add_argument("--out", default="")
    p_probe.set_defaults(func=cmd_probe)

    p_verify = sub.add_parser("verify", help="independently verify recovery from a new window")
    p_verify.add_argument("--baseline", required=True, help="healthy baseline window JSON")
    p_verify.add_argument("--after", required=True, help="new post-rollback window JSON")
    p_verify.add_argument("--expected-release", required=True)
    p_verify.add_argument("--executed-at", default="", help="ISO timestamp of the rollback")
    p_verify.add_argument("--rollback-evidence", default="", help="rollback evidence JSON to read the timestamp from")
    p_verify.add_argument("--p95-tolerance", type=float, default=1.5)
    p_verify.add_argument("--max-error-rate", type=float, default=0.02)
    p_verify.add_argument("--min-samples", type=int, default=30)
    p_verify.add_argument("--stabilization-seconds", type=float, default=3.0)
    p_verify.add_argument("--baseline-min-samples", type=int, default=30)
    p_verify.add_argument("--baseline-max-error-rate", type=float, default=0.05)
    p_verify.add_argument("--out", default="evidence/verification.json")
    p_verify.set_defaults(func=cmd_verify)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
