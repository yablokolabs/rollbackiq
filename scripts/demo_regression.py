#!/usr/bin/env python3
"""End-to-end regression demonstration with real measurements.

Runs the actual demo workload over a real TCP socket in three phases:

1. ``v1`` healthy  -> establish a baseline from real probe results.
2. ``v2`` faulty   -> observe a real regression and let the detector decide.
3. ``v1`` restored -> verify recovery from *new* independent observations.

Everything printed here is measured during this run: durations, percentiles,
error counts and elapsed times. The run is deterministic in its fault seed, so
repeating it produces the same class of result, and the raw windows are written
to ``evidence/`` as the record.

    .venv/bin/python scripts/demo_regression.py
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import httpx  # noqa: E402

from app.models.incident import utcnow  # noqa: E402
from app.models.metrics import Baseline  # noqa: E402
from app.services.collector import collect_window_sync  # noqa: E402
from app.services.detector import RegressionDetector  # noqa: E402
from app.services.verifier import VerificationThresholds, verify_recovery  # noqa: E402

BASE_URL = "http://127.0.0.1:8101"
ENVIRONMENT = "demo-staging"
EVIDENCE_DIR = REPO_ROOT / "evidence"

BASE_ENV = {
    "DEPLOY_ENV": ENVIRONMENT,
    "BASE_LATENCY_MS": "20",
    "FAULT_SEED": "1234",
}


def start_release(release: str, *, fault_latency_ms: float, fault_error_rate: float) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(BASE_ENV)
    env.update(
        {
            "RELEASE_VERSION": release,
            "FAULT_LATENCY_MS": str(fault_latency_ms),
            "FAULT_ERROR_RATE": str(fault_error_rate),
            "RELEASE_COMMIT_SHA": f"demo-sha-{release}",
            "RELEASE_PIPELINE_ID": f"demo-pipeline-{release}",
        }
    )
    process = subprocess.Popen(
        [
            str(REPO_ROOT / ".venv" / "bin" / "python"),
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8101",
            "--log-level",
            "warning",
        ],
        cwd=str(REPO_ROOT / "demo" / "service"),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        preexec_fn=os.setsid,
    )
    wait_for_health(process, release)
    return process


def wait_for_health(process: subprocess.Popen, release: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"{release} exited early:\n{output}")
        try:
            response = httpx.get(f"{BASE_URL}/release", timeout=1.0)
            if response.status_code == 200 and response.json().get("release") == release:
                return
        except Exception as exc:  # not ready yet
            last_error = str(exc)
        time.sleep(0.2)
    raise RuntimeError(f"{release} did not become healthy within {timeout}s ({last_error})")


def stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            process.wait(timeout=5)


def main() -> int:
    EVIDENCE_DIR.mkdir(exist_ok=True)
    evidence: dict[str, object] = {
        "environment": ENVIRONMENT,
        "base_url": BASE_URL,
        "probe_config": {
            "detection_samples_per_window": 150,
            "detection_concurrency": 8,
            "verification_samples": 400,
            "verification_concurrency": 2,
        },
        "fault_injection": {"v2_fault_latency_ms": 180, "v2_fault_error_rate": 0.10},
        # Honest labelling: this run restarts the process locally. The GitLab
        # CI/CD rollback job is a later phase and is not what these timings
        # measure. Detection and verification logic are the real ones.
        "rollback_mechanism": "local process restart standing in for the GitLab CI rollback job",
        "verification_thresholds": {
            "p95_tolerance_multiplier": 1.5,
            "max_error_rate": 0.02,
            "min_samples": 30,
            "stabilization_seconds": 3.0,
        },
    }
    current: subprocess.Popen | None = None
    try:
        print("=== phase 1: healthy v1 baseline ===")
        current = start_release("v1", fault_latency_ms=0.0, fault_error_rate=0.0)
        baseline_window = collect_window_sync(
            BASE_URL, sample_count=150, concurrency=8, environment=ENVIRONMENT
        )
        baseline = Baseline.from_window(baseline_window, min_samples=30, max_error_rate=0.02)
        evidence["baseline_window"] = baseline_window.model_dump(mode="json")
        print(
            f"v1  samples={baseline_window.request_count} errors={baseline_window.error_count} "
            f"p50={baseline_window.p50_ms:.1f}ms p95={baseline_window.p95_ms:.1f}ms "
            f"baseline_verified={baseline.verified}"
        )

        print("\n=== phase 2: deploy faulty v2 ===")
        stop(current)
        deployed_v2_at = utcnow()
        current = start_release("v2", fault_latency_ms=180.0, fault_error_rate=0.10)
        detector = RegressionDetector()
        windows = []
        decision = None
        for index in range(3):
            window = collect_window_sync(
                BASE_URL, sample_count=150, concurrency=8, environment=ENVIRONMENT
            )
            windows.append(window)
            decision = detector.evaluate(
                window, baseline, now=window.ended_at + timedelta(milliseconds=index)
            )
            print(
                f"v2 window {index + 1}: samples={window.request_count} "
                f"errors={window.error_count} error_rate={window.error_rate:.1%} "
                f"p95={window.p95_ms:.1f}ms ratio={decision.p95_ratio:.2f}x "
                f"triggered={decision.triggered}"
                + (f" ({decision.suppressed_reason})" if not decision.triggered else "")
            )
            if decision.triggered:
                break

        assert decision is not None
        evidence["faulty_windows"] = [w.model_dump(mode="json") for w in windows]
        evidence["detection"] = decision.model_dump(mode="json")
        if not decision.triggered:
            print("\nDETECTION FAILED: the regression was not detected")
            (EVIDENCE_DIR / "phase1-regression.json").write_text(json.dumps(evidence, indent=2))
            return 1

        detected_at = utcnow()
        time_to_detect = (detected_at - deployed_v2_at).total_seconds()
        evidence["timing"] = {"time_to_detect_seconds": round(time_to_detect, 3)}
        print(f"\ndetected: {', '.join(decision.breaches)} after {time_to_detect:.2f}s")
        print(f"basis: {decision.reasons}")

        print("\n=== phase 3: roll back to v1 and verify independently ===")
        stop(current)
        executed_at = utcnow()
        current = start_release("v1", fault_latency_ms=0.0, fault_error_rate=0.0)
        rollback_seconds = (utcnow() - executed_at).total_seconds()
        # The post-rollback window must span the stabilization period for real,
        # so it is sampled over several seconds rather than bursted.
        after = collect_window_sync(
            BASE_URL, sample_count=400, concurrency=2, environment=ENVIRONMENT
        )
        verification = verify_recovery(
            expected_release="v1",
            after=after,
            baseline=baseline,
            executed_at=executed_at,
            before=windows[-1],
            thresholds=VerificationThresholds(
                p95_tolerance_multiplier=1.5,
                max_error_rate=0.02,
                min_samples=30,
                stabilization_seconds=3.0,
            ),
        )
        verified_at = utcnow()
        time_to_verify = (verified_at - executed_at).total_seconds()
        evidence["post_rollback_window"] = after.model_dump(mode="json")
        evidence["verification"] = verification.model_dump(mode="json")
        evidence["timing"].update(
            {
                "rollback_execution_seconds": round(rollback_seconds, 3),
                "time_to_verify_seconds": round(time_to_verify, 3),
                "total_recovery_seconds": round((verified_at - deployed_v2_at).total_seconds(), 3),
                "detection_to_verification_seconds": round(
                    (verified_at - detected_at).total_seconds(), 3
                ),
            }
        )
        print(
            f"v1  samples={after.request_count} errors={after.error_count} "
            f"p95={after.p95_ms:.1f}ms ratio={verification.p95_ratio_vs_baseline:.2f}x"
        )
        print(
            f"independent={verification.independent} recovered={verification.recovered} "
            f"reasons={verification.reasons}"
        )
        print(f"timing: {json.dumps(evidence['timing'])}")

        out = EVIDENCE_DIR / "phase1-regression.json"
        out.write_text(json.dumps(evidence, indent=2) + "\n")
        print(f"\nraw evidence written to {out.relative_to(REPO_ROOT)}")
        stop(current)
        return 0 if verification.recovered else 1
    finally:
        if current is not None:
            stop(current)


if __name__ == "__main__":
    sys.exit(main())
