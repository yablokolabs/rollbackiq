"""Independent recovery verification.

A successful rollback job is not evidence of recovery. The verifier only marks
an incident recovered when *new* observations taken after the rollback land
inside the healthy envelope, with enough samples and a long enough
stabilization window to be meaningful.

Observations that predate the rollback are rejected as non-independent, which
is the specific failure mode this module exists to prevent: reusing the metrics
that triggered the incident to declare it fixed.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from ..models.incident import utcnow
from ..models.metrics import Baseline, MetricWindow


class VerificationThresholds(BaseModel):
    """Acceptance envelope for a post-rollback window."""

    #: p95 must return within this multiple of the healthy baseline.
    p95_tolerance_multiplier: float = 1.5
    max_error_rate: float = 0.02
    min_samples: int = 30
    stabilization_seconds: float = 5.0


class VerificationResult(BaseModel):
    recovered: bool
    reasons: List[str] = Field(default_factory=list)
    expected_release: str
    observed_release: str = ""
    samples: int = 0
    window_seconds: float = 0.0
    independent: bool = False
    p95_ms: float = 0.0
    baseline_p95_ms: float = 0.0
    p95_ratio_vs_baseline: float = 0.0
    error_rate: float = 0.0
    improved_vs_faulty: Optional[bool] = None
    before: Optional[MetricWindow] = None
    after: Optional[MetricWindow] = None
    verified_at: datetime = Field(default_factory=utcnow)


def verify_recovery(
    *,
    expected_release: str,
    after: MetricWindow,
    baseline: Baseline,
    executed_at: Optional[datetime] = None,
    before: Optional[MetricWindow] = None,
    thresholds: Optional[VerificationThresholds] = None,
) -> VerificationResult:
    thresholds = thresholds or VerificationThresholds()
    reasons: List[str] = []

    result = VerificationResult(
        recovered=False,
        expected_release=expected_release,
        observed_release=after.release,
        samples=after.request_count,
        window_seconds=(after.ended_at - after.started_at).total_seconds(),
        p95_ms=after.p95_ms,
        baseline_p95_ms=baseline.window.p95_ms,
        error_rate=after.error_rate,
        before=before,
        after=after,
    )

    result.p95_ratio_vs_baseline = (
        after.p95_ms / baseline.window.p95_ms if baseline.window.p95_ms > 0 else float("inf")
    )

    # 1. There must be post-rollback evidence at all.
    if after.request_count == 0:
        reasons.append("no post-rollback observations; a passing job is not proof of recovery")
        result.reasons = reasons
        return result

    # 2. The window must be independent of the incident: it must start at or
    #    after the rollback execution. An unknown execution time is refused
    #    rather than assumed, because independence is the whole point.
    if executed_at is None:
        reasons.append(
            "rollback execution time is unknown, so the post-rollback window cannot be "
            "proven independent of the incident data"
        )
    else:
        result.independent = after.started_at >= executed_at
        if not result.independent:
            reasons.append(
                "post-rollback window starts before the rollback executed, so it reuses "
                "the data that triggered the incident"
            )

    # 3. The running release must be the one we rolled back to.
    if after.release != expected_release:
        reasons.append(
            f"observed release {after.release!r} is not the expected release {expected_release!r}"
        )

    # 4. Enough evidence, over a long enough stabilization window.
    if after.request_count < thresholds.min_samples:
        reasons.append(
            f"insufficient post-rollback samples: {after.request_count} < {thresholds.min_samples}"
        )
    if result.window_seconds < thresholds.stabilization_seconds:
        reasons.append(
            f"stabilization window {result.window_seconds:.1f}s is shorter than "
            f"{thresholds.stabilization_seconds:.1f}s"
        )

    # 5. Health must actually be inside the envelope.
    if result.p95_ratio_vs_baseline > thresholds.p95_tolerance_multiplier:
        reasons.append(
            f"p95 {after.p95_ms:.1f}ms is {result.p95_ratio_vs_baseline:.2f}x the healthy baseline "
            f"{baseline.window.p95_ms:.1f}ms (limit {thresholds.p95_tolerance_multiplier:.1f}x)"
        )
    if after.error_rate > thresholds.max_error_rate:
        reasons.append(
            f"error rate {after.error_rate:.3%} is above the recovery limit "
            f"{thresholds.max_error_rate:.1%}"
        )

    # 6. Comparative information for the report (reported, not gated).
    if before is not None and before.p95_ms > 0:
        result.improved_vs_faulty = after.p95_ms < before.p95_ms

    result.reasons = reasons
    result.recovered = not reasons
    return result
