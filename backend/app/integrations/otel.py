"""OpenTelemetry wiring for the RollbackIQ control plane.

The demo workload is instrumented by ``demo/service/otel_setup.py``, which
records what the *service under observation* did. This module does the same job
for the control plane — it records what *detection and verification decided* —
so a single trace can be followed from "a regression was found" to "recovery
was independently verified".

Two rules, copied from the proven workload wiring because they are the whole
point of it:

1. **Telemetry must never be able to break the control plane.** Every step is
   guarded and every failure is reported rather than raised. A detector that
   cannot make a decision because a collector is unreachable would be a far
   worse bug than a missing span.
2. **It reports what actually happened.** Exports are counted by a wrapper
   around the real OTLP exporter, so ``spans_exported`` means batches the
   collector accepted, not an assertion that telemetry is "on".

Resource attributes follow the names GitLab documents, so a trace correlates
back to the project, the exact deployed commit and the environment:

==============================  ==========================================
``gitlab.project.id``           GitLab project the control plane belongs to
``gitlab.project.name``         Human-readable project name
``service.version``             Commit SHA of the running code
``deployment.environment.name`` Environment, for example ``demo-staging``
==============================  ==========================================

Usage::

    from .integrations.otel import configure_telemetry, span

    configure_telemetry()                      # opt-in, no-ops when unconfigured

    with span("rollbackiq.detector.evaluate", {"rollbackiq.release": "v2"}) as active:
        decision = decide()
        active.set({"rollbackiq.detector.triggered": decision.triggered})
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence

__all__ = [
    "CountingExporter",
    "TelemetryStatus",
    "configure_telemetry",
    "current_status",
    "report",
    "reset_state",
    "span",
]

#: Values of ``OTEL_ENABLED`` that mean "definitely on" / "definitely off".
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSEY = frozenset({"0", "false", "no", "off"})

#: Guards the counters, which are mutated by exporter threads.
_LOCK = threading.Lock()


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


def _normalise_endpoint(raw: str) -> str:
    """Accept either the collector root or the full traces URL."""
    endpoint = raw.strip().rstrip("/")
    if not endpoint:
        return ""
    if endpoint.endswith("/v1/traces"):
        return endpoint
    return f"{endpoint}/v1/traces"


def _coerce(value: object) -> object:
    """Map a Python value onto something the OTel attribute API accepts."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (list, tuple, set, frozenset)):
        return ",".join(str(item) for item in value)
    return str(value)


@dataclass
class TelemetryStatus:
    """Live record of what the telemetry layer is doing.

    ``enabled`` and ``configured`` are separate because they answer different
    questions: ``configured`` means a provider was successfully installed,
    ``enabled`` means spans are actually being produced and sent.
    """

    enabled: bool = False
    configured: bool = False
    endpoint: str = ""
    service_name: str = ""
    resource_attributes: Dict[str, str] = field(default_factory=dict)
    spans_exported: int = 0
    batches_exported: int = 0
    export_failures: int = 0
    setup_error: Optional[str] = None
    last_export_error: Optional[str] = None

    def report(self) -> Dict[str, object]:
        """This status as plain, JSON-safe data."""
        with _LOCK:
            return {
                "telemetry_enabled": self.enabled,
                "configured": self.configured,
                "exporter_endpoint": self.endpoint,
                "service_name": self.service_name,
                "resource_attributes": dict(self.resource_attributes),
                "spans_exported": self.spans_exported,
                "batches_exported": self.batches_exported,
                "export_failures": self.export_failures,
                "last_export_error": self.last_export_error,
                "setup_error": self.setup_error,
                "source": "real OTLP export counters, not a simulated metric",
            }


#: The single, process-wide status record.
STATE = TelemetryStatus()

#: Holds the installed provider and tracer once configured.
_TYPED: Dict[str, Any] = {}


def current_status() -> TelemetryStatus:
    """The live status of whatever is configured."""
    return STATE


def report() -> Dict[str, object]:
    """Current telemetry state, safe to call whether or not setup ran."""
    return STATE.report()


def _record_success(span_count: int) -> None:
    with _LOCK:
        STATE.batches_exported += 1
        STATE.spans_exported += span_count


def _record_failure(error: str) -> None:
    with _LOCK:
        STATE.export_failures += 1
        STATE.last_export_error = error[:500]


class CountingExporter:
    """Wraps the real OTLP exporter and counts what it actually did.

    A batch is only counted as exported when the collector accepted it, so the
    number can never be inflated by the code that produced the spans.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def export(self, spans: Sequence[Any]) -> Any:
        from opentelemetry.sdk.trace.export import SpanExportResult

        span_list = list(spans)
        try:
            result = self._inner.export(span_list)
        except Exception as exc:  # the collector is not reachable / rejected us
            _record_failure(f"{type(exc).__name__}: {exc}")
            return SpanExportResult.FAILURE
        if result == SpanExportResult.SUCCESS:
            _record_success(len(span_list))
        else:
            _record_failure(f"exporter returned {result!r} for {len(span_list)} span(s)")
        return result

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._inner.force_flush(timeout_millis)


class _NoopSpan:
    """Context manager returned whenever telemetry is off.

    One shared instance is handed out for every call, so a control plane
    running without a collector pays no per-span allocation for spans it would
    never send.
    """

    __slots__ = ()

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        # Never suppress the caller's exception.
        return False

    def set(self, attributes: Optional[Dict[str, object]] = None) -> None:
        """Accept and discard attributes; there is no span to put them on."""
        return None


_NOOP_SPAN = _NoopSpan()


class _LiveSpan:
    """A real span that can be annotated part-way through the work.

    Attributes are set after the decision is made, not before, so what a span
    records is what the control plane concluded rather than what it was shown.
    """

    __slots__ = ("_cm", "_initial", "_span")

    def __init__(self, tracer: Any, name: str, attributes: Optional[Dict[str, object]]) -> None:
        self._cm = tracer.start_as_current_span(name)
        self._span: Any = None
        self._initial = attributes or {}

    def __enter__(self) -> "_LiveSpan":
        self._span = self._cm.__enter__()
        self.set(self._initial)
        return self

    def set(self, attributes: Optional[Dict[str, object]] = None) -> None:
        """Attach attributes to the span; unknown values are skipped, never fatal."""
        span = self._span
        if span is None or not attributes:
            return
        for key, value in attributes.items():
            if value is None:
                continue
            try:
                span.set_attribute(key, _coerce(value))
            except Exception:
                continue

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        span = self._span
        if span is not None and exc is not None:
            try:
                from opentelemetry.trace import Status, StatusCode

                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
            except Exception:
                pass
        try:
            return bool(self._cm.__exit__(exc_type, exc, tb))
        except Exception:
            # A broken telemetry layer must not swallow the service's exception.
            return False


def span(name: str, attributes: Optional[Dict[str, object]] = None) -> Any:
    """Open a span, or return an inert no-op when telemetry is not configured.

    Never raises: a failure to create a span must not stop a detection or a
    verification from happening.
    """
    tracer = _TYPED.get("tracer")
    if tracer is None:
        return _NOOP_SPAN
    try:
        return _LiveSpan(tracer, name, attributes)
    except Exception as exc:  # pragma: no cover - defensive
        _record_failure(f"span creation failed: {type(exc).__name__}: {exc}")
        return _NOOP_SPAN


def _build_resource(default_service_name: str) -> Any:
    """Resource attributes, using the names GitLab documents."""
    from opentelemetry.sdk.resources import Resource

    attributes = {
        "service.name": _env("OTEL_SERVICE_NAME", default=default_service_name),
        "service.version": _env("CI_COMMIT_SHA", default="local"),
        "deployment.environment.name": _env(
            "CI_ENVIRONMENT_NAME", "DEPLOY_ENV", default="demo-staging"
        ),
    }
    project_id = _env("CI_PROJECT_ID")
    if project_id:
        attributes["gitlab.project.id"] = project_id
    project_name = _env("CI_PROJECT_NAME")
    if project_name:
        attributes["gitlab.project.name"] = project_name
    return Resource.create(attributes)


def _disable() -> None:
    """Leave the control plane running with telemetry off."""
    STATE.enabled = False
    STATE.configured = False
    STATE.endpoint = ""
    STATE.service_name = ""
    STATE.resource_attributes = {}
    STATE.setup_error = None


def configure_telemetry(
    *,
    service_name: Optional[str] = None,
    enabled: Optional[bool] = None,
    endpoint: Optional[str] = None,
) -> TelemetryStatus:
    """Instrument the control plane and return the resulting status.

    Telemetry is opt-in. It is installed only when an endpoint is configured and
    ``OTEL_ENABLED`` has not explicitly opted out — so a local run, or a test,
    behaves exactly as it would with this module absent.

    The call is idempotent: once a provider is installed, further calls return
    the same status rather than building a second one. It never raises.
    """
    if _TYPED.get("configured"):
        return current_status()

    explicit = os.getenv("OTEL_ENABLED", "").strip().lower()
    # An unset OTEL_ENABLED is not an opt-out; only a falsey value is.
    requested = enabled if enabled is not None else explicit not in _FALSEY

    raw_endpoint = endpoint if endpoint is not None else _env(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
    )
    normalised = _normalise_endpoint(raw_endpoint or "")

    if not requested or not normalised:
        _disable()
        return current_status()

    default_name = service_name or _env(
        "OTEL_SERVICE_NAME", default="rollbackiq-control-plane"
    )

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = _build_resource(default_name)
        attributes = {str(k): str(v) for k, v in dict(resource.attributes).items()}

        inner = OTLPSpanExporter(
            endpoint=normalised,
            timeout=_env_float("OTEL_EXPORT_TIMEOUT_SECONDS", 10.0),
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(CountingExporter(inner)))

        STATE.endpoint = normalised
        STATE.resource_attributes = attributes
        STATE.service_name = str(attributes.get("service.name", default_name))

        try:
            trace.set_tracer_provider(provider)
        except Exception:
            # The process already has a global provider. The provider built here
            # is still used for our spans, which is what matters for a trace.
            pass

        _TYPED["provider"] = provider
        _TYPED["tracer"] = provider.get_tracer("rollbackiq.control_plane")
        _TYPED["configured"] = True
        STATE.enabled = True
        STATE.configured = True
        STATE.setup_error = None
    except Exception as exc:  # pragma: no cover - depends on installed packages
        STATE.enabled = False
        STATE.configured = False
        STATE.setup_error = f"{type(exc).__name__}: {exc}"
        _TYPED.clear()

    return current_status()


def reset_state() -> None:
    """Return the module to its unconfigured state.

    Shuts down any installed provider so its batch thread cannot export later,
    which keeps tests order-independent. It does not deregister the
    process-global provider, because the OpenTelemetry API does not allow that.
    """
    provider = _TYPED.get("provider")
    if provider is not None:
        try:
            provider.shutdown()
        except Exception:
            pass
    _TYPED.clear()
    STATE.enabled = False
    STATE.configured = False
    STATE.endpoint = ""
    STATE.service_name = ""
    STATE.resource_attributes = {}
    STATE.spans_exported = 0
    STATE.batches_exported = 0
    STATE.export_failures = 0
    STATE.setup_error = None
    STATE.last_export_error = None
