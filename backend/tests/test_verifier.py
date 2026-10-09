"""Recovery verification tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.metrics import Baseline, MetricWindow
from app.services.verifier import VerificationThresholds, verify_recovery

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
ENV = "demo-staging"
THRESHOLDS = VerificationThresholds(
    p95_tolerance_multiplier=1.5,
    max_error_rate=0.02,
    min_samples=30,
    stabilization_seconds=5.0,
)


def window(
    release: str,
    *,
    p95_ms: float,
    samples: int = 60,
    errors: int = 0,
    start: datetime = NOW,
    seconds: float = 10.0,
    environment: str = ENV,
) -> MetricWindow:
    return MetricWindow(
        release=release,
        environment=environment,
        started_at=start,
        ended_at=start + timedelta(seconds=seconds),
        request_count=samples,
        error_count=errors,
        error_rate=(errors / samples) if samples else 0.0,
        availability=((samples - errors) / samples) if samples else 0.0,
        p50_ms=p95_ms * 0.5,
        p95_ms=p95_ms,
        p99_ms=p95_ms * 1.1,
        mean_ms=p95_ms * 0.7,
        max_ms=p95_ms * 1.2,
        source="test",
    )


def healthy_baseline() -> Baseline:
    return Baseline.from_window(
        window("v1", p95_ms=10.0), min_samples=30, max_error_rate=0.02
    )


def test_recovery_verified_only_with_independent_healthy_window():
    result = verify_recovery(
        expected_release="v1",
        after=window("v1", p95_ms=11.0, start=NOW + timedelta(seconds=1)),
        baseline=healthy_baseline(),
        executed_at=NOW,
        before=window("v2", p95_ms=60.0),
        thresholds=THRESHOLDS,
    )
    assert result.recovered is True
    assert result.reasons == []
    assert result.independent is True
    assert result.improved_vs_faulty is True
    assert result.p95_ratio_vs_baseline == 1.1


def test_passing_rollback_without_observations_is_not_recovery():
    result = verify_recovery(
        expected_release="v1",
        after=window("v1", p95_ms=0.0, samples=0, start=NOW + timedelta(seconds=1)),
        baseline=healthy_baseline(),
        executed_at=NOW,
        thresholds=THRESHOLDS,
    )
    assert result.recovered is False
    assert "no post-rollback observations" in result.reasons[0]


def test_unknown_rollback_time_cannot_be_verified():
    result = verify_recovery(
        expected_release="v1",
        after=window("v1", p95_ms=11.0, start=NOW + timedelta(seconds=1)),
        baseline=healthy_baseline(),
        executed_at=None,
        thresholds=THRESHOLDS,
    )
    assert result.recovered is False
    assert result.independent is False
    assert any("cannot be proven independent" in r for r in result.reasons)


def test_reusing_incident_data_is_rejected():
    """The window that triggered the incident must not close it."""
    result = verify_recovery(
        expected_release="v1",
        after=window("v1", p95_ms=11.0, start=NOW - timedelta(seconds=30), seconds=10.0),
        baseline=healthy_baseline(),
        executed_at=NOW,
        thresholds=THRESHOLDS,
    )
    assert result.recovered is False
    assert result.independent is False
    assert any("starts before the rollback executed" in r for r in result.reasons)


def test_wrong_running_release_is_rejected():
    result = verify_recovery(
        expected_release="v1",
        after=window("v2", p95_ms=11.0, start=NOW + timedelta(seconds=1)),
        baseline=healthy_baseline(),
        executed_at=NOW,
        thresholds=THRESHOLDS,
    )
    assert result.recovered is False
    assert any("is not the expected release" in r for r in result.reasons)


def test_insufficient_samples_are_rejected():
    result = verify_recovery(
        expected_release="v1",
        after=window("v1", p95_ms=11.0, samples=10, start=NOW + timedelta(seconds=1)),
        baseline=healthy_baseline(),
        executed_at=NOW,
        thresholds=THRESHOLDS,
    )
    assert result.recovered is False
    assert any("insufficient post-rollback samples" in r for r in result.reasons)


def test_short_stabilization_window_is_rejected():
    result = verify_recovery(
        expected_release="v1",
        after=window("v1", p95_ms=11.0, start=NOW + timedelta(seconds=1), seconds=1.0),
        baseline=healthy_baseline(),
        executed_at=NOW,
        thresholds=THRESHOLDS,
    )
    assert result.recovered is False
    assert any("stabilization window" in r for r in result.reasons)


def test_latency_still_degraded_is_rejected():
    result = verify_recovery(
        expected_release="v1",
        after=window("v1", p95_ms=18.0, start=NOW + timedelta(seconds=1)),
        baseline=healthy_baseline(),
        executed_at=NOW,
        thresholds=THRESHOLDS,
    )
    assert result.recovered is False
    assert any("is 1.80x the healthy baseline" in r for r in result.reasons)


def test_error_rate_still_high_is_rejected():
    result = verify_recovery(
        expected_release="v1",
        after=window("v1", p95_ms=11.0, errors=6, start=NOW + timedelta(seconds=1)),
        baseline=healthy_baseline(),
        executed_at=NOW,
        thresholds=THRESHOLDS,
    )
    assert result.recovered is False
    assert any("error rate" in r for r in result.reasons)


def test_recovery_never_reported_when_any_check_fails():
    """Multiple simultaneous problems must all be reported, never averaged away."""
    result = verify_recovery(
        expected_release="v1",
        after=window(
            "v2", p95_ms=99.0, errors=9, samples=10, start=NOW - timedelta(seconds=5)
        ),
        baseline=healthy_baseline(),
        executed_at=NOW,
        thresholds=THRESHOLDS,
    )
    assert result.recovered is False
    assert len(result.reasons) >= 4
