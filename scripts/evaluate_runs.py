#!/usr/bin/env python3
"""Repeat the local lifecycle and the healthy control, then count what happened.

One green run shows that recovery can be verified; it does not show how often.
This script runs two things several times, with real containers, and summarises
only what the runs wrote to disk:

* **Lifecycle runs** — ``scripts/demo_lifecycle_local.sh``, unchanged: deploy v1,
  baseline, deploy the faulted v2, detect, approve, gated rollback, independent
  verification. A run counts as recovered only when its ``verification.json``
  says ``recovered`` and ``independent``. A run with no verification is a failure.
* **Healthy controls** — the same detection path (``ci_incident.py regress``)
  with both fault inputs set to zero. The detector must stay silent; a detection
  here is a false positive.

    .venv/bin/python scripts/evaluate_runs.py --runs 5 --controls 5

    .venv/bin/python scripts/evaluate_runs.py --summarise-only   # recount existing runs

Each run keeps its own directory under ``--out`` (default ``evidence/evaluation``)
with every artifact and the full console log. Failed runs are kept, not retried.

The approval in a lifecycle run is recorded by this host's user without a wait,
so these timings contain no human approval time.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

IMAGE = "rollbackiq-workload:local"
NETWORK = "rollbackiq-local"
CONTAINER = "rollbackiq-eval-workload"
CONTROL_CONTAINER = "rollbackiq-eval-control"
ENVIRONMENT = "demo-staging"


def _load(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _seconds_between(start: Optional[str], end: Optional[str]) -> Optional[float]:
    if not start or not end:
        return None
    return round((_parse(end) - _parse(start)).total_seconds(), 3)


def _lifecycle_run(run_dir: Path) -> Dict[str, Any]:
    run = _load(run_dir / "run.json") or {}
    detection = _load(run_dir / "ci-detection.json") or {}
    rollback = _load(run_dir / "rollback-execution.json") or {}
    verification = _load(run_dir / "verification.json")
    result = (verification or {}).get("result") or {}
    windows = detection.get("windows") or []

    if verification is None:
        reason: Optional[str] = "verification.json is missing or unreadable"
    elif not result.get("recovered"):
        reason = "verifier refused: " + ("; ".join(result.get("reasons") or []) or "no reason given")
    elif not result.get("independent"):
        reason = "the verification window is not independent of the incident data"
    else:
        reason = None

    return {
        "run": run_dir.name,
        "recovered": reason is None,
        "failure_reason": reason,
        "exit_code": run.get("exit_code"),
        "wall_seconds": run.get("wall_seconds"),
        "detected": detection.get("triggered"),
        "windows_to_detect": len(windows) or None,
        "p95_ratio_at_detection": detection.get("p95_ratio"),
        "first_window_to_detection_seconds": _seconds_between(
            windows[0].get("started_at") if windows else None,
            windows[-1].get("ended_at") if windows else None,
        ),
        "rollback_to_verified_seconds": _seconds_between(
            rollback.get("executed_at"), result.get("verified_at")
        ),
        "verify_p95_ratio_vs_baseline": result.get("p95_ratio_vs_baseline"),
        "verify_error_rate": result.get("error_rate"),
    }


def summarise(root: Path) -> Dict[str, Any]:
    """Count the runs under ``root`` from the artifacts each one wrote."""
    lifecycle = [_lifecycle_run(path) for path in sorted(root.glob("run-*")) if path.is_dir()]
    recovered = sum(1 for run in lifecycle if run["recovered"])

    control_dirs = [path for path in sorted(root.glob("control-*")) if path.is_dir()]
    false_positives: List[str] = []
    inconclusive: List[str] = []
    for path in control_dirs:
        detection = _load(path / "ci-detection.json")
        if detection is None or "triggered" not in detection:
            inconclusive.append(path.name)
        elif detection["triggered"]:
            false_positives.append(path.name)

    return {
        "lifecycle": {
            "runs": len(lifecycle),
            "recovered": recovered,
            "success_rate": recovered / len(lifecycle) if lifecycle else None,
            "failed": [
                {"run": run["run"], "reason": run["failure_reason"]}
                for run in lifecycle
                if not run["recovered"]
            ],
            "per_run": lifecycle,
        },
        "controls": {
            "runs": len(control_dirs),
            "false_positives": len(false_positives),
            "false_positive_runs": false_positives,
            "inconclusive": inconclusive,
        },
    }


def _execute(cmd: List[str], run_dir: Path, env: Optional[Dict[str, str]] = None) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    clock = time.monotonic()
    with (run_dir / "console.log").open("w") as log:
        code = subprocess.run(
            cmd, cwd=REPO_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
        ).returncode
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "command": " ".join(cmd),
                "started_at": started.isoformat(),
                "exit_code": code,
                "wall_seconds": round(time.monotonic() - clock, 2),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"  {run_dir.name}: exit {code}")


def _release(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(PYTHON), "scripts/ci_release.py", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _run_lifecycles(root: Path, count: int) -> None:
    for index in range(1, count + 1):
        run_dir = root / f"run-{index}"
        env = dict(
            os.environ,
            DEMO_WORKDIR=str(run_dir),
            DEMO_CONTAINER=CONTAINER,
            DEMO_NETWORK=NETWORK,
            DEMO_IMAGE=IMAGE,
        )
        _execute(["bash", "scripts/demo_lifecycle_local.sh"], run_dir, env)


def _run_controls(root: Path, count: int) -> None:
    digest = _release("digest", "--image", IMAGE).stdout.strip()
    for index in range(1, count + 1):
        run_dir = root / f"control-{index}"
        run_dir.mkdir(parents=True, exist_ok=True)
        _release(
            "deploy", "--image", IMAGE, "--release", "v1", "--container", CONTAINER,
            "--network", NETWORK, "--environment", ENVIRONMENT, "--digest", digest,
            "--out", str(run_dir / "deploy-healthy.json"),
        )
        _release(
            "probe", "--target", f"{CONTAINER}:8000", "--in-container", IMAGE,
            "--network", NETWORK, "--samples", "150", "--concurrency", "8",
            "--environment", ENVIRONMENT, "--expect-release", "v1", "--expect-healthy",
            "--out", str(run_dir / "baseline-window.json"),
        )
        _execute(
            [
                str(PYTHON), "-u", "scripts/ci_incident.py", "regress",
                "--image", IMAGE, "--network", NETWORK, "--environment", ENVIRONMENT,
                "--container", CONTROL_CONTAINER, "--digest", digest,
                "--fault-latency", "0", "--fault-error-rate", "0",
                "--baseline", str(run_dir / "baseline-window.json"),
                "--workdir", str(run_dir),
                "--deploy-out", str(run_dir / "deploy-control.json"),
                "--detection-out", str(run_dir / "ci-detection.json"),
                "--out", str(run_dir / "incident-bundle.json"),
            ],
            run_dir,
        )


def _stop_containers() -> None:
    for name in (CONTAINER, f"{CONTAINER}-verify", CONTROL_CONTAINER, "rollbackiq-workload-v2"):
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--controls", type=int, default=5)
    parser.add_argument("--out", default="evidence/evaluation")
    parser.add_argument("--summarise-only", action="store_true")
    args = parser.parse_args(argv[1:])

    root = Path(args.out)
    root = root if root.is_absolute() else REPO_ROOT / root

    if not args.summarise_only:
        if any(root.glob("run-*")) or any(root.glob("control-*")):
            print(f"{root} already holds runs; choose another --out or remove them", file=sys.stderr)
            return 2
        root.mkdir(parents=True, exist_ok=True)
        try:
            print(f"lifecycle runs: {args.runs}")
            _run_lifecycles(root, args.runs)
            print(f"healthy controls: {args.controls}")
            _run_controls(root, args.controls)
        finally:
            _stop_containers()

    summary = summarise(root)
    summary["environment"] = {
        "host": platform.platform(),
        "cpus": os.cpu_count(),
        "docker": subprocess.run(
            ["docker", "--version"], capture_output=True, text=True
        ).stdout.strip(),
        "commit": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
        ).stdout.strip(),
        "summarised_at": datetime.now(timezone.utc).isoformat(),
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    lifecycle, controls = summary["lifecycle"], summary["controls"]
    print(f"\nlifecycle: {lifecycle['recovered']}/{lifecycle['runs']} recovered and verified")
    for failure in lifecycle["failed"]:
        print(f"  FAILED {failure['run']}: {failure['reason']}")
    print(
        f"controls:  {controls['false_positives']}/{controls['runs']} false positives"
        + (f", inconclusive: {controls['inconclusive']}" if controls["inconclusive"] else "")
    )
    print(f"written: {(root / 'summary.json').relative_to(REPO_ROOT)}")
    return 0 if not lifecycle["failed"] and not controls["false_positives"] and not controls["inconclusive"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
