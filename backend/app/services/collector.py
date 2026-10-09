"""Real HTTP probing.

The collector issues real HTTP requests and summarises its *own* observed
latencies and status codes. It deliberately does not trust the workload's
self-reported metrics for detection or verification, so the measurement that
triggers an incident and the measurement that closes it come from the observer,
not from the service under suspicion.

Run standalone for evidence:

    .venv/bin/python -m app.services.collector --url http://127.0.0.1:8000 --samples 60
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any, Dict, List, Optional

import httpx

from ..models.incident import utcnow
from ..models.metrics import MetricWindow
from .stats import summarise_durations

DEFAULT_PATH = "/api/work"
#: Status code recorded for a request that never produced a response
#: (timeout, connection reset). It counts as an error and is never a success.
TRANSPORT_ERROR_STATUS = 599


async def collect_window(
    base_url: str,
    *,
    path: str = DEFAULT_PATH,
    sample_count: int = 60,
    concurrency: int = 8,
    timeout: float = 2.0,
    release: Optional[str] = None,
    environment: str = "demo",
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> MetricWindow:
    """Probe ``base_url`` and return a window built from the real results."""
    if sample_count < 1:
        raise ValueError("sample_count must be at least 1")

    semaphore = asyncio.Semaphore(max(1, concurrency))
    durations: List[float] = []
    errors = 0
    lock = asyncio.Lock()
    started = utcnow()

    async with httpx.AsyncClient(
        base_url=base_url, timeout=timeout, transport=transport
    ) as client:
        if release is None:
            release, environment = await _read_release(client, environment)

        async def one_request() -> None:
            nonlocal errors
            async with semaphore:
                began = time.perf_counter()
                status = TRANSPORT_ERROR_STATUS
                try:
                    response = await client.get(path)
                    status = response.status_code
                except Exception:
                    status = TRANSPORT_ERROR_STATUS
                elapsed_ms = (time.perf_counter() - began) * 1000.0
                async with lock:
                    durations.append(elapsed_ms)
                    if status >= 500:
                        errors += 1

        await asyncio.gather(*(one_request() for _ in range(sample_count)))

    ended = utcnow()
    summary = summarise_durations(durations, errors)
    return MetricWindow(
        release=release or "unknown",
        environment=environment,
        started_at=started,
        ended_at=ended,
        request_count=int(summary["request_count"]),
        error_count=int(summary["error_count"]),
        error_rate=float(summary["error_rate"]),
        availability=float(summary["availability"]),
        p50_ms=float(summary["p50_ms"]),
        p95_ms=float(summary["p95_ms"]),
        p99_ms=float(summary["p99_ms"]),
        mean_ms=float(summary["mean_ms"]),
        max_ms=float(summary["max_ms"]),
        source=(
            f"probe: {sample_count} real HTTP GET {path} "
            f"(concurrency {concurrency}, timeout {timeout}s)"
        ),
    )


async def _read_release(
    client: httpx.AsyncClient, fallback_environment: str
) -> tuple[str, str]:
    """Best-effort release label; an unreachable service stays 'unknown'."""
    try:
        response = await client.get("/release")
        response.raise_for_status()
        payload = response.json()
        return (
            str(payload.get("release", "unknown")),
            str(payload.get("environment", fallback_environment)),
        )
    except Exception:
        return "unknown", fallback_environment


def collect_window_sync(base_url: str, **kwargs: Any) -> MetricWindow:
    """Synchronous convenience wrapper for scripts and tests."""
    return asyncio.run(collect_window(base_url, **kwargs))


def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="RollbackIQ metric probe")
    parser.add_argument("--url", required=True, help="base URL of the workload")
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--samples", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--environment", default="demo-staging")
    parser.add_argument("--json", action="store_true", help="print the window as JSON only")
    args = parser.parse_args(argv)

    window = collect_window_sync(
        args.url,
        path=args.path,
        sample_count=args.samples,
        concurrency=args.concurrency,
        timeout=args.timeout,
        environment=args.environment,
    )
    payload: Dict[str, Any] = window.model_dump(mode="json")
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"release      {window.release} ({window.environment})")
    print(f"samples      {window.request_count}")
    print(f"window       {payload['started_at']} -> {payload['ended_at']}")
    print(f"error rate   {window.error_rate:.3%}  (errors {window.error_count})")
    print(f"p50 / p95    {window.p50_ms:.1f}ms / {window.p95_ms:.1f}ms")
    print(f"p99 / max    {window.p99_ms:.1f}ms / {window.max_ms:.1f}ms")
    print(f"source       {window.source}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(_main())
