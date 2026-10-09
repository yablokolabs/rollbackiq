"""Regression detector tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.metrics import Baseline, MetricWindow
from app.services.detector import DetectorConfig, RegressionDetector

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
ENV = "demo-staging"


def make_window(
    p95_ms: float,
    *,
    samples: int = 60,
    errors: int = 0,
    release: str = "v2",
    environment: str = ENV,
    start: datetime = T0,
    seconds: float = 10.0,
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


def healthy_baseline(p95_ms: float = 10.0) -> Baseline:
    return Baseline.from_window(
        make_window(p95_ms, release="v1", environment=ENV),
        min_samples=30,
        max_error_rate=0.02,
    )


def test_baseline_requires_enough_samples_and_low_error_rate():
    thin = Baseline.from_window(make_window(10.0, samples=5), min_samples=30, max_error_rate=0.02)
    noisy = Baseline.from_window(
        make_window(10.0, samples=60, errors=10), min_samples=30, max_error_rate=0.02
    )
    assert thin.verified is False
    assert noisy.verified is False
    assert healthy_baseline().verified is True


def test_empty_window_never_triggers():
    detector = RegressionDetector()
    result = detector.evaluate(make_window(50.0, samples=0), healthy_baseline())
    assert result.triggered is False
    assert "no observations" in (result.suppressed_reason or "")


def test_insufficient_samples_never_trigger():
    detector = RegressionDetector()
    result = detector.evaluate(make_window(500.0, samples=5), healthy_baseline())
    assert result.triggered is False
    assert "insufficient samples" in (result.suppressed_reason or "")


def test_missing_baseline_never_triggers():
    detector = RegressionDetector()
    result = detector.evaluate(make_window(500.0), None)
    assert result.triggered is False
    assert result.suppressed_reason == "no verified healthy baseline"


def test_unverified_baseline_never_triggers():
    detector = RegressionDetector()
    unverified = Baseline.from_window(
        make_window(10.0, samples=5, release="v1"), min_samples=30, max_error_rate=0.02
    )
    result = detector.evaluate(make_window(500.0), unverified)
    assert result.triggered is False
    assert result.suppressed_reason == "no verified healthy baseline"


def test_healthy_window_reports_no_breach():
    detector = RegressionDetector()
    result = detector.evaluate(make_window(10.0), healthy_baseline())
    assert result.triggered is False
    assert result.breaches == []
    assert result.suppressed_reason == "no threshold breached"


def test_latency_breach_needs_two_consecutive_windows():
    detector = RegressionDetector()
    baseline = healthy_baseline(10.0)

    first = detector.evaluate(make_window(45.0), baseline, now=T0)
    assert first.triggered is False
    assert first.breaches == ["P95_LATENCY"]
    assert "sustained-window requirement" in (first.suppressed_reason or "")
    assert first.p95_ratio == 4.5

    second = detector.evaluate(make_window(45.0), baseline, now=T0 + timedelta(seconds=1))
    assert second.triggered is True
    assert second.breaches == ["P95_LATENCY"]
    assert 0.0 < second.confidence <= 1.0


def test_breach_below_multiplier_does_not_trigger():
    detector = RegressionDetector()
    baseline = healthy_baseline(10.0)
    for _ in range(3):
        result = detector.evaluate(make_window(25.0), baseline, now=T0)
    assert result.triggered is False
    assert result.breaches == []
    assert result.p95_ratio == 2.5


def test_error_rate_breach_triggers_on_its_own():
    detector = RegressionDetector()
    baseline = healthy_baseline(10.0)
    config = DetectorConfig(required_consecutive_windows=1)
    detector = RegressionDetector(config)

    result = detector.evaluate(make_window(10.0, errors=9), baseline, now=T0)
    assert result.triggered is True
    assert result.breaches == ["ERROR_RATE"]


def test_cooldown_suppresses_repeat_trigger():
    detector = RegressionDetector()
    baseline = healthy_baseline(10.0)
    assert detector.evaluate(make_window(45.0), baseline, now=T0).triggered is False
    assert detector.evaluate(make_window(45.0), baseline, now=T0).triggered is True

    # Same regression burst, still inside the cooldown.
    assert detector.evaluate(make_window(45.0), baseline, now=T0).triggered is False
    third = detector.evaluate(make_window(45.0), baseline, now=T0)
    assert third.triggered is False
    assert "cooldown active" in (third.suppressed_reason or "")

    # After the cooldown expires, a breach that is still present opens a new
    # incident. The sustained-window counter is deliberately not cleared by a
    # cooldown suppression, because the breach never went away.
    later = T0 + timedelta(seconds=detector.config.cooldown_seconds + 1)
    reopened = detector.evaluate(make_window(45.0), baseline, now=later)
    assert reopened.triggered is True

    # A genuinely healthy window clears that accumulated evidence.
    detector.evaluate(make_window(10.0), baseline, now=later)
    assert detector.consecutive_windows == 0


def test_healthy_window_resets_consecutive_counter():
    detector = RegressionDetector()
    baseline = healthy_baseline(10.0)
    assert detector.evaluate(make_window(45.0), baseline, now=T0).triggered is False
    assert detector.consecutive_windows == 1
    detector.evaluate(make_window(10.0), baseline, now=T0)
    assert detector.consecutive_windows == 0
    assert detector.evaluate(make_window(45.0), baseline, now=T0).triggered is False


def test_baseline_from_another_environment_is_refused():
    detector = RegressionDetector()
    baseline = Baseline.from_window(
        make_window(10.0, release="v1", environment="production"),
        min_samples=30,
        max_error_rate=0.02,
    )
    result = detector.evaluate(make_window(45.0), baseline)
    assert result.triggered is False
    assert "does not match" in (result.suppressed_reason or "")
