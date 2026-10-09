#!/usr/bin/env python3
"""Prove that the demo workload exports real telemetry to an OTLP collector.

This starts the workload exactly as it is deployed, drives genuine HTTP traffic
through the user-facing endpoint, flushes the exporter and then reads the
workload's own ``/otel`` report. The report is not a claim: it is produced by a
counter wrapped around the real exporter, so spans are only counted once the
collector has accepted the batch.

Exit status is 0 only when at least one span was exported and nothing failed,
which makes this usable as a check rather than a demonstration.

Usage:
    python scripts/otel_export_evidence.py \
        --endpoint https://<group-id>.otel.gitlab-o11y.com:14318 \
        --out evidence/otel-export.json
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / "demo" / "service"
PYTHON = ROOT / ".venv" / "bin" / "python"


def _get(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode())


def _post(url: str, timeout: float = 10.0):
    request = urllib.request.Request(url, data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode()
        return response.status, (json.loads(body) if body.strip() else {})


def wait_for_health(base: str, deadline: float) -> None:
    while time.time() < deadline:
        try:
            status, _ = _get(f"{base}/healthz", timeout=2.0)
            if status == 200:
                return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.25)
    raise SystemExit(f"service did not become healthy at {base}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--endpoint",
        default=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
        help="OTLP collector root or /v1/traces URL",
    )
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--requests", type=int, default=12)
    parser.add_argument("--out", default="evidence/otel-export.json")
    args = parser.parse_args()

    if not args.endpoint:
        raise SystemExit("no endpoint: pass --endpoint or set OTEL_EXPORTER_OTLP_ENDPOINT")

    base = f"http://127.0.0.1:{args.port}"
    env = dict(os.environ)
    env.update(
        {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": args.endpoint,
            "OTEL_SERVICE_NAME": "rollbackiq-demo-workload",
            "RELEASE_VERSION": "v1",
            "RELEASE_COMMIT_SHA": env.get("CI_COMMIT_SHA", "local"),
            "DEPLOY_ENV": "demo-staging",
            "BASE_LATENCY_MS": "5",
            "FAULT_LATENCY_MS": "0",
            "FAULT_ERROR_RATE": "0",
            "CI_PROJECT_ID": env.get("CI_PROJECT_ID", "87424071"),
            "CI_PROJECT_NAME": env.get("CI_PROJECT_NAME", "rollbackiq"),
        }
    )

    python = str(PYTHON) if PYTHON.exists() else sys.executable
    process = subprocess.Popen(
        [python, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(args.port), "--log-level", "warning"],
        cwd=str(SERVICE_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    record: dict = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "captured_with": "scripts/otel_export_evidence.py",
        "collector_endpoint": args.endpoint,
        "service_started_from": str(SERVICE_DIR),
    }

    try:
        # Long start budget: the first run may build nothing but must import the SDK.
        wait_for_health(base, deadline=time.time() + 45)

        statuses: list[int] = []
        started = time.perf_counter()
        for _ in range(args.requests):
            try:
                status, _ = _get(f"{base}/api/work?units=2")
                statuses.append(status)
            except urllib.error.HTTPError as exc:
                statuses.append(exc.code)
        elapsed = time.perf_counter() - started

        # Flush rather than sleep: the point is to read the exporter's own state.
        _, report = _post(f"{base}/admin/flush-telemetry")

        record.update(
            {
                "requests_sent": len(statuses),
                "statuses": statuses,
                "traffic_seconds": round(elapsed, 3),
                "workload_telemetry_report": report,
            }
        )

        spans = int(report.get("spans_exported", 0))
        failures = int(report.get("export_failures", 0))
        enabled = bool(report.get("telemetry_enabled"))

        record["verdict"] = {
            "telemetry_enabled": enabled,
            "spans_exported": spans,
            "export_failures": failures,
            "passed": enabled and spans >= len(statuses) and failures == 0,
        }

        out_path = pathlib.Path(args.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(record, indent=2) + "\n")

        print(json.dumps(record["verdict"], indent=2))
        print(f"written: {out_path.relative_to(ROOT)}")
        if record["verdict"]["passed"]:
            print(f"spans accepted by the collector: {spans} (failures: {failures})")
            return 0
        print(f"NOT PROVEN: spans={spans} failures={failures} enabled={enabled}", file=sys.stderr)
        return 1
    finally:
        process.send_signal(signal.SIGINT)
        try:
            output, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            process.kill()
            output, _ = process.communicate()
        if output and output.strip():
            print("--- workload output ---")
            print(output.strip()[-2000:])


if __name__ == "__main__":
    raise SystemExit(main())
