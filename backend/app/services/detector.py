"""Deterministic regression detection.

Detection is arithmetic over measured windows, not a language model opinion.
The detector refuses to fire when the evidence is thin (too few samples, no
verified baseline) and refuses to fire again inside its cooldown, so a noisy
window cannot produce a burst of incident escalations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ..models.incident import utcnow
from ..models.metrics import Baseline, MetricWindow


@dataclass(frozen=True)
class DetectorConfig:
    """Thresholds for detection.

    Defaults follow the specification's example trigger: p95 above three times
    the baseline, or an error rate above five percent, sustained across two
    consecutive windows with at least 30 samples each.
    """

    p95_multiplier: float = 3.0
    error_rate_threshold: float = 0.05
    min_samples: int = 30
    required_consecutive_windows: int = 2
    cooldown_seconds: float = 60.0


class DetectionResult(BaseModel):
    triggered: bool
    breaches: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    suppressed_reason: Optional[str] = None
    sample_count: int = 0
    window_started_at: Optional[datetime] = None
    window_ended_at: Optional[datetime] = None
    baseline_release: Optional[str] = None
    p95_ratio: Optional[float] = None
    error_rate: float = 0.0
    confidence: float = 0.0
    confidence_note: str = (
        "heuristic margin-and-sample indicator between 0 and 1, not a probability"
    )
    evaluated_at: datetime = Field(default_factory=utcnow)


class RegressionDetector:
    """Stateful detector: consecutive-window and cooldown tracking live here."""

    def __init__(self, config: Optional[DetectorConfig] = None) -> None:
        self.config = config or DetectorConfig()
        self._consecutive = 0
        self._last_trigger_at: Optional[datetime] = None

    @property
    def consecutive_windows(self) -> int:
        return self._consecutive

    @property
    def last_trigger_at(self) -> Optional[datetime]:
        return self._last_trigger_at

    def reset(self) -> None:
        self._consecutive = 0
        self._last_trigger_at = None

    # -- internals ---------------------------------------------------------

    def _confidence(self, p95_ratio: float, error_rate: float, samples: int) -> float:
        """Documented heuristic, deliberately not presented as a probability."""
        margin = max(
            p95_ratio / self.config.p95_multiplier if self.config.p95_multiplier else 0.0,
            error_rate / self.config.error_rate_threshold
            if self.config.error_rate_threshold
            else 0.0,
        )
        margin_score = min(1.0, margin / 1.5)
        sample_score = min(1.0, samples / (2.0 * self.config.min_samples))
        return round(0.5 * margin_score + 0.5 * sample_score, 4)

    # -- public API --------------------------------------------------------

    def evaluate(
        self,
        window: MetricWindow,
        baseline: Optional[Baseline],
        *,
        now: Optional[datetime] = None,
    ) -> DetectionResult:
        now = now or utcnow()
        base = DetectionResult(
            triggered=False,
            sample_count=window.request_count,
            window_started_at=window.started_at,
            window_ended_at=window.ended_at,
            baseline_release=baseline.release if baseline else None,
            error_rate=window.error_rate,
            evaluated_at=now,
        )

        if window.is_empty:
            base.suppressed_reason = "no observations in window"
            return base

        if window.request_count < self.config.min_samples:
            base.suppressed_reason = (
                f"insufficient samples: {window.request_count} < {self.config.min_samples}"
            )
            return base

        if baseline is None or not baseline.verified:
            base.suppressed_reason = "no verified healthy baseline"
            return base

        if baseline.environment != window.environment:
            base.suppressed_reason = (
                f"baseline environment {baseline.environment!r} does not match "
                f"window environment {window.environment!r}"
            )
            return base

        baseline_p95 = baseline.window.p95_ms
        p95_ratio = (window.p95_ms / baseline_p95) if baseline_p95 > 0 else float("inf")
        base.p95_ratio = p95_ratio

        breaches: List[str] = []
        reasons: List[str] = []

        if p95_ratio > self.config.p95_multiplier:
            breaches.append("P95_LATENCY")
            reasons.append(
                f"p95 {window.p95_ms:.1f}ms is {p95_ratio:.2f}x the baseline "
                f"{baseline_p95:.1f}ms (limit {self.config.p95_multiplier:.1f}x)"
            )
        if window.error_rate > self.config.error_rate_threshold:
            breaches.append("ERROR_RATE")
            reasons.append(
                f"error rate {window.error_rate:.3%} exceeds "
                f"{self.config.error_rate_threshold:.1%}"
            )

        base.breaches = breaches
        base.reasons = reasons
        base.confidence = self._confidence(p95_ratio, window.error_rate, window.request_count)

        if not breaches:
            self._consecutive = 0
            base.suppressed_reason = "no threshold breached"
            return base

        self._consecutive += 1

        if self._consecutive < self.config.required_consecutive_windows:
            base.suppressed_reason = (
                f"sustained-window requirement not met: {self._consecutive} of "
                f"{self.config.required_consecutive_windows}"
            )
            return base

        if self._last_trigger_at is not None:
            ready_at = self._last_trigger_at + timedelta(seconds=self.config.cooldown_seconds)
            if now < ready_at:
                base.suppressed_reason = (
                    f"cooldown active until {ready_at.isoformat()}; a further "
                    "incident is not opened from the same regression burst"
                )
                return base

        base.triggered = True
        self._last_trigger_at = now
        self._consecutive = 0
        return base

    def summary(self) -> Dict[str, object]:
        return {
            "config": self.config.__dict__,
            "consecutive_windows": self._consecutive,
            "last_trigger_at": self._last_trigger_at.isoformat() if self._last_trigger_at else None,
        }
