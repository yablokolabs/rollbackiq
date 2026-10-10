#!/usr/bin/env python3
"""Independent HTTP probe for the CI release jobs.

Deliberately a separate measurement from the workload it observes: it issues
its own real HTTP requests, times them itself, and counts its own failures. It
never reads the workload's self-reported metrics, so a release cannot flatter
its own health. The same is true of the trigger: the window that opens an
incident and the window that closes it are both produced here.

Standard library only, on purpose. That lets the *identical* command run inside
the release container's image during a GitLab job and on a developer's machine,
so the pipeline is exercising the same measurement path as a local run rather
than a CI-only variant of it.

Prints the window as JSON and exits non-zero when it collected no observations,
because "no data" must never be indistinguishable from "healthy".

    python scripts/ci_probe.py --url http://workload:8000 --samples 120
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional

#: Status recorded for a request that never produced a response. It counts as
#: an error, matching the control plane's collector.
TRANSPORT_ERROR_STATUS = 599
DEFAULT_PATH = "/api/work"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percentile(sorted_values: List[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    index = max(0, min(len(sorted_values) - 1, math.ceil(fraction * len(sorted_values)) - 1))
    return sorted_values[index]


def _get(url: str, timeout: float) -> tuple[int, float]:
    """One real request. Returns (status, elapsed_ms)."""
    began = time.perf_counter()
    status = TRANSPORT_ERROR_STATUS
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except Exception:
        status = TRANSPORT_ERROR_STATUS
    return status, (time.perf_counter() - began) * 1000.0


def _read_release(base: str, fallback_environment: str, timeout: float) -> tuple[str, str]:
    """Best-effort release identity; an unreachable service stays 'unknown'."""
    try:
        status, _ = 0, None
        with urllib.request.urlopen(f"{base}/release", timeout=timeout) as response:
            status = response.status
            payload = json.loads(response.read().decode() or "{}")
        if status == 200:
            return str(payload.get("release", "unknown")), str(
                payload.get("environment", fallback_environment)
            )
    except Exception:
        pass
    return "unknown", fallback_environment


def probe(
    base: str,
    *,
    path: str = DEFAULT_PATH,
    sample_count: int = 120,
    concurrency: int = 8,
    timeout: float = 5.0,
    environment: str = "demo-staging",
    min_duration: float = 0.0,
) -> Dict[str, object]:
    """Measure ``base`` with real requests.

    ``min_duration`` paces the requests so the window actually spans at least
    that many seconds. Without it a fast, healthy service answers as quickly as
    the probes can be issued, which produces a window only a second or two long.
    That is not a flaw in the measurement, but it is not a *stabilization*
    window either, and the verifier refuses one — correctly, because a service
    that has been healthy for one second has not demonstrated it stays healthy.
    """
    if sample_count < 1:
        raise ValueError("sample_count must be at least 1")

    release, observed_environment = _read_release(base, environment, timeout)
    started = _utcnow()

    durations: List[float] = []
    statuses: List[int] = []
    lock = threading.Lock()
    pending = list(range(sample_count))
    index_lock = threading.Lock()

    workers = max(1, min(concurrency, sample_count))
    # Each worker handles sample_count / workers requests, so pacing one request
    # per slot spreads the burst across the requested duration.
    slot_seconds = (min_duration * workers / sample_count) if min_duration > 0 else 0.0

    def worker() -> None:
        while True:
            with index_lock:
                if not pending:
                    return
                pending.pop()
            status, elapsed = _get(f"{base}{path}", timeout)
            with lock:
                statuses.append(status)
                durations.append(elapsed)
            if slot_seconds > 0:
                remaining = slot_seconds - (elapsed / 1000.0)
                if remaining > 0:
                    time.sleep(remaining)

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    ended = _utcnow()
    ordered = sorted(durations)
    errors = sum(1 for status in statuses if status >= 500)
    total = len(durations)
    if total == 0:
        raise RuntimeError("no observations collected; the workload did not answer a single request")

    return {
        "release": release,
        "environment": observed_environment,
        "started_at": started,
        "ended_at": ended,
        "request_count": total,
        "error_count": errors,
        "error_rate": errors / total,
        "availability": (total - errors) / total,
        "p50_ms": _percentile(ordered, 0.50),
        "p95_ms": _percentile(ordered, 0.95),
        "p99_ms": _percentile(ordered, 0.99),
        "mean_ms": sum(ordered) / total,
        "max_ms": ordered[-1],
        "source": (
            f"probe: {total} real HTTP GET {path} "
            f"(concurrency {workers}, timeout {timeout}s"
            + (f", paced across >= {min_duration}s" if min_duration > 0 else "")
            + ")"
        ),
        "status_counts": {str(status): statuses.count(status) for status in sorted(set(statuses))},
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="RollbackIQ independent CI probe")
    parser.add_argument("--url", required=True, help="base URL of the workload, e.g. http://workload:8000")
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--samples", type=int, default=120)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--environment", default="demo-staging")
    parser.add_argument(
        "--min-duration",
        type=float,
        default=0.0,
        help="pace the requests so the window spans at least this many seconds",
    )
    parser.add_argument("--expect-release", default="", help="fail unless this release is serving")
    parser.add_argument("--expect-healthy", action="store_true", help="fail unless the window looks healthy")
    parser.add_argument("--max-error-rate", type=float, default=0.05)
    parser.add_argument("--out", default="")
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the window as JSON on stdout and nothing else, for callers that capture it",
    )
    args = parser.parse_args(argv)

    # The window is evidence of an HTTP service. urllib also opens other schemes,
    # such as file://, and a window measured from one of those would be false evidence.
    if urllib.parse.urlsplit(args.url).scheme not in ("http", "https"):
        parser.error(f"--url must be an http:// or https:// URL, not {args.url!r}")

    window = probe(
        args.url,
        path=args.path,
        sample_count=args.samples,
        concurrency=args.concurrency,
        timeout=args.timeout,
        environment=args.environment,
        min_duration=args.min_duration,
    )
    payload = json.dumps(window, indent=2) + "\n"

    if args.out:
        from pathlib import Path

        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(payload)

    if args.json:
        # Machine-readable mode: stdout is the artifact, so a caller can pipe it
        # straight into a file without a shared filesystem.
        print(json.dumps(window))
    else:
        print(
            f"release={window['release']} samples={window['request_count']} "
            f"errors={window['error_count']} error_rate={window['error_rate']:.1%} "
            f"p50={window['p50_ms']:.1f}ms p95={window['p95_ms']:.1f}ms"
        )
        if args.out:
            print(f"written: {args.out}")

    if args.expect_release and window["release"] != args.expect_release:
        print(
            f"FAIL: serving release {window['release']!r}, expected {args.expect_release!r}",
            file=sys.stderr,
        )
        return 1
    if args.expect_healthy and float(window["error_rate"]) > args.max_error_rate:
        print(
            f"FAIL: error rate {window['error_rate']:.1%} exceeds {args.max_error_rate:.1%}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
