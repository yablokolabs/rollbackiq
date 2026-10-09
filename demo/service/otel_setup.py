"""OpenTelemetry wiring for the RollbackIQ demo workload.

The workload exports real spans to an OTLP collector — in the hackathon setup,
GitLab Observability (``https://<group-id>.otel.gitlab-o11y.com:14318``). Two
rules shape this module:

1. **Telemetry must never be able to break the workload.** Every step is
   guarded; if the SDK or the collector is unavailable the service starts
   normally and reports the failure through its own ``/otel`` endpoint.
2. **It reports what actually happened.** Exports are counted by a wrapper
   around the real exporter, so ``/otel`` shows spans that were genuinely
   accepted or rejected rather than a claim that telemetry is "on".

Resource attributes follow the names GitLab documents, so traces correlate back
to the project and the exact deployed commit:

===========================  ==========================================
``gitlab.project.id``        GitLab project the workload belongs to
``gitlab.project.name``      Human-readable project name
``service.version``          Commit SHA of the running code
``deployment.environment.name``  Environment (for example ``demo-staging``)
===========================  ==========================================
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional, Sequence

__all__ = ["setup_telemetry", "report"]


def _env(*names: str, default: str = "") -> str:
    """First non-empty environment value among ``names``."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class TelemetryState:
    """Live record of what the telemetry layer is doing."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.enabled = False
        self.endpoint = ""
        self.service_name = ""
        self.resource_attributes: Dict[str, str] = {}
        self.batches_sent = 0
        self.spans_sent = 0
        self.failures = 0
        self.last_error: Optional[str] = None
        self.setup_error: Optional[str] = None

    def record_success(self, span_count: int) -> None:
        with self.lock:
            self.batches_sent += 1
            self.spans_sent += span_count

    def record_failure(self, error: str) -> None:
        with self.lock:
            self.failures += 1
            self.last_error = error[:500]

    def as_dict(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "telemetry_enabled": self.enabled,
                "exporter_endpoint": self.endpoint,
                "service_name": self.service_name,
                "resource_attributes": dict(self.resource_attributes),
                "batches_exported": self.batches_sent,
                "spans_exported": self.spans_sent,
                "export_failures": self.failures,
                "last_export_error": self.last_error,
                "setup_error": self.setup_error,
                "source": "real OTLP export counters, not a simulated metric",
            }


STATE = TelemetryState()
TYPED: Dict[str, Any] = {}


def report() -> Dict[str, Any]:
    """Current telemetry state, safe to call whether or not setup ran."""
    return STATE.as_dict()


def _build_resource(app_name: str) -> Any:
    from opentelemetry.sdk.resources import Resource

    attributes = {
        "service.name": _env("OTEL_SERVICE_NAME", "CI_PROJECT_NAME", default=app_name),
        "service.version": _env("CI_COMMIT_SHA", "RELEASE_COMMIT_SHA", default="local"),
        "deployment.environment.name": _env("CI_ENVIRONMENT_NAME", "DEPLOY_ENV", default="demo-staging"),
    }
    project_id = _env("CI_PROJECT_ID")
    if project_id:
        attributes["gitlab.project.id"] = project_id
    project_name = _env("CI_PROJECT_NAME")
    if project_name:
        attributes["gitlab.project.name"] = project_name
    return Resource.create(attributes)


def _normalise_endpoint(raw: str) -> str:
    """Accept either the collector root or the full traces URL."""
    endpoint = raw.rstrip("/")
    if endpoint.endswith("/v1/traces"):
        return endpoint
    return f"{endpoint}/v1/traces"


class CountingExporter:
    """Wraps the real OTLP exporter and counts what it actually did."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def export(self, spans: Sequence[Any]) -> Any:
        from opentelemetry.sdk.trace.export import SpanExportResult

        span_list = list(spans)
        try:
            result = self._inner.export(span_list)
        except Exception as exc:  # pragma: no cover - network dependent
            STATE.record_failure(f"{type(exc).__name__}: {exc}")
            return SpanExportResult.FAILURE
        if result == SpanExportResult.SUCCESS:
            STATE.record_success(len(span_list))
        else:
            STATE.record_failure(f"exporter returned {result!r} for {len(span_list)} span(s)")
        return result

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._inner.force_flush(timeout_millis)


def setup_telemetry(app: Any, default_service_name: str = "rollbackiq-demo-workload") -> Dict[str, Any]:
    """Instrument ``app`` and return the resulting telemetry report.

    Instrumentation is enabled when ``OTEL_ENABLED`` is truthy, or when an
    endpoint is configured and ``OTEL_ENABLED`` is not explicitly false. With no
    endpoint the workload simply runs uninstrumented, which is the normal state
    for local runs and tests.
    """
    explicit = _env("OTEL_ENABLED").strip().lower()
    endpoint_raw = _env("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")

    if explicit in {"0", "false", "no", "off"}:
        return report()
    if not endpoint_raw and explicit not in {"1", "true", "yes", "on"}:
        return report()

    STATE.endpoint = _normalise_endpoint(endpoint_raw) if endpoint_raw else ""

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        resource = _build_resource(default_service_name)
        STATE.resource_attributes = {
            k: str(v) for k, v in dict(resource.attributes).items()
        }
        STATE.service_name = str(resource.attributes.get("service.name", default_service_name))

        exporter_kwargs: Dict[str, Any] = {"timeout": _env_float("OTEL_EXPORT_TIMEOUT_SECONDS", 10.0)}
        if STATE.endpoint:
            exporter_kwargs["endpoint"] = STATE.endpoint
        inner = OTLPSpanExporter(**exporter_kwargs)

        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(CountingExporter(inner)))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        TYPED["provider"] = provider
        TYPED["tracer"] = provider.get_tracer("rollbackiq.demo.service")
        STATE.enabled = True
    except Exception as exc:  # pragma: no cover - depends on installed packages
        STATE.enabled = False
        STATE.setup_error = f"{type(exc).__name__}: {exc}"

    return report()


def get_tracer() -> Any:
    """Tracer for manual spans, or ``None`` when telemetry is off."""
    return TYPED.get("tracer")


def flush(timeout_millis: int = 5_000) -> bool:
    """Flush pending spans; used by the demo runner to make evidence deterministic."""
    provider = TYPED.get("provider")
    if provider is None:
        return False
    try:
        return bool(provider.force_flush(timeout_millis))
    except Exception as exc:  # pragma: no cover - defensive
        STATE.record_failure(f"flush failed: {type(exc).__name__}: {exc}")
        return False
