"""End-to-end detection chain against the real demo workload.

These tests exercise the actual :mod:`demo.service.app` FastAPI application
through HTTP requests handled by ASGI, so the detector, collector and verifier
are driven by real request timings and real 5xx responses rather than by
hand-written windows.

The verification thresholds here use a one-second stabilization window so the
test stays fast; the production default remains five seconds.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from app.models.incident import utcnow
from app.models.metrics import Baseline
from app.services.collector import collect_window_sync
from app.services.detector import RegressionDetector
from app.services.verifier import VerificationThresholds, verify_recovery

ENV = "demo-staging"
DEMO_APP_PATH = Path(__file__).resolve().parents[2] / "demo" / "service" / "app.py"


@pytest.fixture()
def workload():
    spec = importlib.util.spec_from_file_location("rollbackiq_demo_workload", DEMO_APP_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # The module must be registered before execution: dataclasses resolves
    # annotations through sys.modules during class creation.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    module.WINDOW.reset()
    return module


def configure(module, release: str, *, fault_latency_ms: float, fault_error_rate: float):
    module.SETTINGS = module.Settings(
        release=release,
        environment=ENV,
        commit_sha=f"sha-{release}",
        pipeline_id=f"pipeline-{release}",
        base_latency_ms=20.0,
        fault_latency_ms=fault_latency_ms,
        fault_error_rate=fault_error_rate,
        fault_seed=7,
    )
    module.WINDOW.reset()


def probe(module, *, samples: int = 60, concurrency: int = 8):
    transport = httpx.ASGITransport(app=module.app)
    return collect_window_sync(
        "http://demo.local",
        sample_count=samples,
        concurrency=concurrency,
        transport=transport,
    )


def test_healthy_release_then_faulty_release_is_detected_then_verified(workload):
    module = workload

    # 1. Healthy v1 establishes the baseline from real measurements.
    configure(module, "v1", fault_latency_ms=0.0, fault_error_rate=0.0)
    baseline_window = probe(module, samples=60, concurrency=2)
    baseline = Baseline.from_window(baseline_window, min_samples=30, max_error_rate=0.02)
    assert baseline.verified is True, baseline_window
    assert baseline_window.request_count == 60
    assert baseline_window.error_count == 0

    # 2. Faulty v2 regresses for real: more latency and a real error rate.
    configure(module, "v2", fault_latency_ms=180.0, fault_error_rate=0.10)
    detector = RegressionDetector()
    first = probe(module, samples=60, concurrency=8)
    second = probe(module, samples=60, concurrency=8)

    assert first.release == "v2"
    assert first.p95_ms > baseline_window.p95_ms * 3, (
        f"expected a real latency regression: v1 p95={baseline_window.p95_ms:.1f}ms "
        f"v2 p95={first.p95_ms:.1f}ms"
    )
    assert first.error_count > 0, "fault injection produced no errors"

    # 3. Detection requires the breach to persist across two windows.
    detector.evaluate(first, baseline, now=first.ended_at)
    decision = detector.evaluate(second, baseline, now=second.ended_at + timedelta(milliseconds=1))
    assert decision.triggered is True, decision.suppressed_reason
    assert "P95_LATENCY" in decision.breaches

    # 4. Roll back to v1 and verify with NEW observations only.
    configure(module, "v1", fault_latency_ms=0.0, fault_error_rate=0.0)
    executed_at = utcnow()
    after = probe(module, samples=60, concurrency=1)

    verification = verify_recovery(
        expected_release="v1",
        after=after,
        baseline=baseline,
        executed_at=executed_at,
        before=second,
        thresholds=VerificationThresholds(
            p95_tolerance_multiplier=1.5,
            max_error_rate=0.02,
            min_samples=30,
            stabilization_seconds=1.0,
        ),
    )
    assert verification.independent is True
    assert verification.recovered is True, verification.reasons
    assert verification.improved_vs_faulty is True
    assert after.p95_ms < second.p95_ms


def test_faulty_release_without_rollback_fails_verification(workload):
    """Verification must refuse to declare success while v2 is still running."""
    module = workload
    configure(module, "v1", fault_latency_ms=0.0, fault_error_rate=0.0)
    baseline = Baseline.from_window(
        probe(module, samples=60, concurrency=2), min_samples=30, max_error_rate=0.02
    )

    configure(module, "v2", fault_latency_ms=180.0, fault_error_rate=0.10)
    executed_at = utcnow()
    after = probe(module, samples=60, concurrency=1)

    verification = verify_recovery(
        expected_release="v1",
        after=after,
        baseline=baseline,
        executed_at=executed_at,
        thresholds=VerificationThresholds(stabilization_seconds=1.0),
    )
    assert verification.recovered is False
    assert any("is not the expected release" in r for r in verification.reasons)
