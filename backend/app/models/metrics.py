"""Typed metric windows.

Every value in a :class:`MetricWindow` comes from real observations reported by
the workload's ``/metrics`` endpoint. Nothing in this module synthesises
numbers, and an empty window is represented as empty rather than as zeros, so a
missing measurement can never be mistaken for a healthy one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

from .incident import utcnow


class MetricWindow(BaseModel):
    """Aggregated observations for one release over one measurement window."""

    release: str
    environment: str = "demo"
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime = Field(default_factory=utcnow)
    request_count: int = 0
    error_count: int = 0
    error_rate: float = 0.0
    availability: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    mean_ms: float = 0.0
    max_ms: float = 0.0
    source: str = "unknown"

    @field_validator("request_count", "error_count")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("counts cannot be negative")
        return v

    @property
    def is_empty(self) -> bool:
        return self.request_count == 0

    @classmethod
    def from_service_payload(
        cls,
        payload: Dict[str, Any],
        *,
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
    ) -> "MetricWindow":
        """Build a window from a workload ``/metrics`` response.

        Unknown or missing fields are rejected loudly rather than defaulted,
        because an unparsed field would silently change detection behaviour.
        """
        required = ("release", "request_count", "error_count", "error_rate", "p95_ms")
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"metrics payload missing required fields: {missing}")

        return cls(
            release=str(payload["release"]),
            environment=str(payload.get("environment", "demo")),
            started_at=started_at or utcnow(),
            ended_at=ended_at or utcnow(),
            request_count=int(payload["request_count"]),
            error_count=int(payload["error_count"]),
            error_rate=float(payload["error_rate"]),
            availability=float(payload.get("availability", 0.0)),
            p50_ms=float(payload.get("p50_ms", 0.0)),
            p95_ms=float(payload["p95_ms"]),
            p99_ms=float(payload.get("p99_ms", 0.0)),
            mean_ms=float(payload.get("mean_ms", 0.0)),
            max_ms=float(payload.get("max_ms", 0.0)),
            source=str(payload.get("source", "unknown")),
        )


class Baseline(BaseModel):
    """A verified healthy reference for one release and environment."""

    release: str
    environment: str = "demo"
    captured_at: datetime = Field(default_factory=utcnow)
    window: MetricWindow
    sample_count: int = 0
    verified: bool = False

    @classmethod
    def from_window(
        cls,
        window: MetricWindow,
        *,
        min_samples: int,
        max_error_rate: float,
    ) -> "Baseline":
        """Create a baseline only if the reference window is trustworthy."""
        verified = window.request_count >= min_samples and window.error_rate <= max_error_rate
        return cls(
            release=window.release,
            environment=window.environment,
            window=window,
            sample_count=window.request_count,
            verified=verified,
        )
