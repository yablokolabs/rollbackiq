"""RollbackIQ demo workload.

This is the *deployed application* whose health RollbackIQ observes. It is
deliberately small so that its behaviour is auditable:

* ``v1`` serves requests with a small, stable latency.
* ``v2`` injects a real, configurable regression (extra latency and/or errors)
  so the regression detector has something measurable to find.

Every request is recorded in an in-process rolling window, and ``/metrics``
exposes the values computed from those real observations. Nothing here invents
numbers: if no request has been served, the metrics are empty.
"""

from __future__ import annotations

import itertools
import os
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List

from fastapi import FastAPI, HTTPException, Query, Response

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# Configuration (all overridable from the environment so CI can pin them)
# ---------------------------------------------------------------------------


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:  # pragma: no cover - defensive
        return default


@dataclass(frozen=True)
class Settings:
    release: str = field(default_factory=lambda: os.getenv("RELEASE_VERSION", "v1"))
    commit_sha: str = field(default_factory=lambda: os.getenv("RELEASE_COMMIT_SHA", "local"))
    pipeline_id: str = field(default_factory=lambda: os.getenv("RELEASE_PIPELINE_ID", "local"))
    image_digest: str = field(default_factory=lambda: os.getenv("RELEASE_IMAGE_DIGEST", "local"))
    environment: str = field(default_factory=lambda: os.getenv("DEPLOY_ENV", "demo"))

    # Fault injection. v1 defaults to 0, so the deployment only regresses when
    # the deployment itself asks for it.
    base_latency_ms: float = field(default_factory=lambda: _env_float("BASE_LATENCY_MS", 8.0))
    fault_latency_ms: float = field(default_factory=lambda: _env_float("FAULT_LATENCY_MS", 0.0))
    fault_error_rate: float = field(default_factory=lambda: _env_float("FAULT_ERROR_RATE", 0.0))
    fault_seed: int = field(default_factory=lambda: int(_env_float("FAULT_SEED", 1234)))

    window_size: int = field(default_factory=lambda: int(_env_float("METRIC_WINDOW_SIZE", 5000)))


SETTINGS = Settings()

# ---------------------------------------------------------------------------
# Real observation store: one entry per served request
# ---------------------------------------------------------------------------


@dataclass
class Observation:
    at: float
    duration_ms: float
    status: int


class RollingWindow:
    """Thread-safe rolling window of the requests this process actually served."""

    def __init__(self, maxlen: int) -> None:
        self._lock = threading.Lock()
        self._items: Deque[Observation] = deque(maxlen=maxlen)

    def record(self, observation: Observation) -> None:
        with self._lock:
            self._items.append(observation)

    def snapshot(self, since: float | None = None, until: float | None = None) -> List[Observation]:
        with self._lock:
            items = list(self._items)
        if since is not None:
            items = [i for i in items if i.at >= since]
        if until is not None:
            items = [i for i in items if i.at < until]
        return items

    def reset(self) -> None:
        with self._lock:
            self._items.clear()


WINDOW = RollingWindow(SETTINGS.window_size)

# Per-request index for fault injection. Seeding from this counter keeps a run
# reproducible while still spreading injected errors across requests; seeding
# from the release alone would draw the same random value every time and make
# an "8% error rate" mean either 0% or 100%.
_REQUEST_SEQUENCE = itertools.count()


def _request_rng() -> random.Random:
    index = next(_REQUEST_SEQUENCE)
    return random.Random(f"{SETTINGS.fault_seed}:{SETTINGS.release}:{index}")


def _percentile(sorted_values: List[float], fraction: float) -> float:
    """Nearest-rank percentile; deterministic for a given sample."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = max(0, min(len(sorted_values) - 1, int(round(fraction * (len(sorted_values) - 1)))))
    return sorted_values[index]


def summarise(observations: List[Observation]) -> Dict[str, float]:
    """Compute window statistics from real observations only."""
    count = len(observations)
    if count == 0:
        return {
            "request_count": 0,
            "error_count": 0,
            "error_rate": 0.0,
            "availability": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "mean_ms": 0.0,
            "max_ms": 0.0,
        }
    durations = sorted(o.duration_ms for o in observations)
    errors = [o for o in observations if o.status >= 500]
    return {
        "request_count": float(count),
        "error_count": float(len(errors)),
        "error_rate": len(errors) / count,
        "availability": (count - len(errors)) / count,
        "p50_ms": _percentile(durations, 0.50),
        "p95_ms": _percentile(durations, 0.95),
        "p99_ms": _percentile(durations, 0.99),
        "mean_ms": sum(durations) / count,
        "max_ms": durations[-1],
    }


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(title="RollbackIQ demo workload", version=__version__)


@app.middleware("http")
async def observe_request(request, call_next):
    """Time and record every request, including failures raised by handlers."""
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        duration_ms = (time.perf_counter() - started) * 1000.0
        # Health, metrics and metadata endpoints are probes, not user traffic,
        # so they are excluded from the window they themselves report on.
        if request.url.path not in {"/healthz", "/metrics", "/release", "/readyz"}:
            WINDOW.record(Observation(at=time.time(), duration_ms=duration_ms, status=status))


@app.get("/healthz")
def healthz() -> Dict[str, object]:
    return {"status": "ok", "release": SETTINGS.release, "environment": SETTINGS.environment}


@app.get("/readyz")
def readyz() -> Dict[str, object]:
    return {"status": "ready", "release": SETTINGS.release}


@app.get("/release")
def release_info() -> Dict[str, str]:
    """Release metadata, normally populated by the GitLab pipeline."""
    return {
        "release": SETTINGS.release,
        "commit_sha": SETTINGS.commit_sha,
        "pipeline_id": SETTINGS.pipeline_id,
        "image_digest": SETTINGS.image_digest,
        "environment": SETTINGS.environment,
    }


@app.get("/api/work")
def work(units: int = Query(default=3, ge=1, le=50)) -> Dict[str, object]:
    """User-facing endpoint: the one the probes measure."""
    # Deterministic per-request jitter so repeated runs are comparable.
    rng = _request_rng()

    if SETTINGS.fault_error_rate > 0 and rng.random() < SETTINGS.fault_error_rate:
        raise HTTPException(status_code=500, detail="simulated dependency failure")

    total = 0
    for i in range(units):
        total += i * i

    sleep_ms = SETTINGS.base_latency_ms + SETTINGS.fault_latency_ms
    if sleep_ms > 0:
        # Deterministic jitter of +/-20% keeps the baseline realistic while
        # leaving the injected regression clearly visible.
        jitter = 1.0 + rng.uniform(-0.2, 0.2)
        time.sleep((sleep_ms * jitter) / 1000.0)

    return {"release": SETTINGS.release, "units": units, "checksum": total}


@app.get("/metrics")
def metrics(since: float | None = None, until: float | None = None) -> Dict[str, object]:
    """Window statistics computed from real served requests."""
    observations = WINDOW.snapshot(since=since, until=until)
    summary = summarise(observations)
    return {
        "release": SETTINGS.release,
        "environment": SETTINGS.environment,
        "window_seconds": (observations[-1].at - observations[0].at) if len(observations) > 1 else 0.0,
        "source": "demo-workload in-process observation window",
        **summary,
    }


@app.get("/metrics/prometheus")
def metrics_prometheus() -> Response:
    """Minimal Prometheus text exposition of the same real observations."""
    summary = summarise(WINDOW.snapshot())
    lines = [
        "# HELP rollbackiq_requests_total Requests served by this release",
        "# TYPE rollbackiq_requests_total counter",
        f"rollbackiq_requests_total {int(summary['request_count'])}",
        "# HELP rollbackiq_errors_total Requests served with a 5xx status",
        "# TYPE rollbackiq_errors_total counter",
        f"rollbackiq_errors_total {int(summary['error_count'])}",
        "# HELP rollbackiq_request_duration_ms Request latency percentiles in ms",
        "# TYPE rollbackiq_request_duration_ms gauge",
        f'rollbackiq_request_duration_ms{{quantile="0.5"}} {summary["p50_ms"]:.3f}',
        f'rollbackiq_request_duration_ms{{quantile="0.95"}} {summary["p95_ms"]:.3f}',
        f'rollbackiq_request_duration_ms{{quantile="0.99"}} {summary["p99_ms"]:.3f}',
        "# HELP rollbackiq_release_info Deployed release metadata",
        "# TYPE rollbackiq_release_info gauge",
        f'rollbackiq_release_info{{release="{SETTINGS.release}",environment="{SETTINGS.environment}"}} 1',
    ]
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@app.post("/admin/reset-window")
def reset_window() -> Dict[str, str]:
    """Clear the observation window (used by the demo to separate phases)."""
    WINDOW.reset()
    return {"status": "reset"}
