"""Control-plane telemetry tests: instrumenting must never change a decision.

``app/integrations/otel.py`` carries the same two promises as the workload's
wiring (``demo/service/otel_setup.py``): telemetry is strictly opt-in, and it can
never change or break the control plane it observes. The second promise is the
one worth testing hardest, so most of this file is about a broken collector
leaving detection and verification completely unaffected.

No test touches the network. Enabling telemetry against an unroutable endpoint
is enough, because the OTLP exporter only connects when a batch is exported.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from opentelemetry.sdk.trace.export import SpanExportResult

from app.integrations import otel
from app.models.metrics import Baseline, MetricWindow
from app.services.detector import RegressionDetector
from app.services.verifier import VerificationThresholds, verify_recovery

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
ENV = "demo-staging"
THRESHOLDS = VerificationThresholds(
    p95_tolerance_multiplier=1.5,
    max_error_rate=0.02,
    min_samples=30,
    stabilization_seconds=5.0,
)

#: Any of these being set in the ambient environment would change an outcome,
#: so every test starts from a known-clean slate.
CONFIGURED_VARIABLES = (
    "OTEL_ENABLED",
    "OTEL_SERVICE_NAME",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORT_TIMEOUT_SECONDS",
    "CI_PROJECT_ID",
    "CI_PROJECT_NAME",
    "CI_COMMIT_SHA",
    "CI_ENVIRONMENT_NAME",
    "DEPLOY_ENV",
)


@pytest.fixture(autouse=True)
def clean_telemetry(monkeypatch):
    """Reset module state and remove every variable that steers it.

    ``reset_state`` shuts down any installed provider before clearing the
    counters, so a late batch from a previous test cannot inflate a later one.
    """
    for name in CONFIGURED_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    otel.reset_state()
    yield
    otel.reset_state()


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
        make_window(p95_ms, release="v1"), min_samples=30, max_error_rate=0.02
    )


def detector_trace() -> list[tuple]:
    """Run a scripted detector sequence and reduce it to its decisions.

    The sequence deliberately exercises several branches: a sustained latency
    breach that triggers on the second window, a healthy window that clears the
    counter, and a later breach that triggers again.
    """
    detector = RegressionDetector()
    baseline = healthy_baseline()
    trace = []
    for index, p95_ms in enumerate((45.0, 45.0, 10.0, 45.0, 45.0)):
        result = detector.evaluate(
            make_window(p95_ms), baseline, now=T0 + timedelta(seconds=index)
        )
        trace.append(
            (
                result.triggered,
                tuple(result.breaches),
                result.suppressed_reason,
                result.p95_ratio,
                result.confidence,
            )
        )
    return trace


def verification_trace() -> list[tuple]:
    """Run a scripted verifier sequence covering every early return."""
    baseline = healthy_baseline()
    faulty = make_window(60.0, release="v2")
    cases = (
        # Verified: an independent, healthy, post-rollback window.
        {
            "after": make_window(11.0, release="v1", start=T0 + timedelta(seconds=1)),
            "executed_at": T0,
        },
        # Early return: no post-rollback observations at all.
        {
            "after": make_window(0.0, release="v1", samples=0, start=T0 + timedelta(seconds=1)),
            "executed_at": T0,
        },
        # Early return: the rollback time is unknown, so independence is unprovable.
        {
            "after": make_window(11.0, release="v1", start=T0 + timedelta(seconds=1)),
            "executed_at": None,
        },
        # The window reuses the data that triggered the incident.
        {
            "after": make_window(11.0, release="v1", start=T0 - timedelta(seconds=30)),
            "executed_at": T0,
        },
        # The wrong release is running.
        {
            "after": make_window(11.0, release="v2", start=T0 + timedelta(seconds=1)),
            "executed_at": T0,
        },
        # Still degraded.
        {
            "after": make_window(18.0, release="v1", start=T0 + timedelta(seconds=1)),
            "executed_at": T0,
        },
        # Fails for several independent reasons at once: the window is not
        # independent, it is still degraded, and the wrong release is serving.
        # This case exists so the reason list is exercised as a list, which is
        # how the span records it.
        {
            "after": make_window(18.0, release="v2", start=T0 - timedelta(seconds=30)),
            "executed_at": T0,
        },
    )
    trace = []
    for case in cases:
        result = verify_recovery(
            expected_release="v1",
            baseline=baseline,
            before=faulty,
            thresholds=THRESHOLDS,
            **case,
        )
        trace.append(
            (
                result.recovered,
                tuple(result.reasons),
                result.independent,
                result.p95_ratio_vs_baseline,
            )
        )
    return trace


class FakeExporter:
    """Stand-in for the network exporter, which is not what is under test."""

    def __init__(
        self,
        result: SpanExportResult | None = SpanExportResult.SUCCESS,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.exported: list[int] = []

    def export(self, spans):
        self.exported.append(len(list(spans)))
        if self.error is not None:
            raise self.error
        return self.result

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


# -- opt-in behaviour ------------------------------------------------------


def test_no_collector_leaves_the_control_plane_uninstrumented():
    """A local run has no collector, so nothing is installed and nothing invented."""
    status = otel.configure_telemetry()

    assert status.enabled is False
    assert status.configured is False
    assert status.endpoint == ""
    assert status.service_name == ""
    assert status.resource_attributes == {}
    assert status.setup_error is None
    # Nothing was claimed about exports that never happened.
    assert status.spans_exported == 0
    assert status.export_failures == 0
    # The module-level report agrees with the status that was returned.
    assert otel.current_status() is status
    assert otel.report() == status.report()

    # The no-op span is still usable as a context manager, and discards writes.
    with otel.span("rollbackiq.test.noop", {"ignored": "yes"}) as active:
        active.set({"also_ignored": 1})


def test_explicit_opt_out_wins_over_a_configured_endpoint(monkeypatch):
    """Opting out is absolute: an endpoint on the box must not turn telemetry on."""
    monkeypatch.setenv("OTEL_ENABLED", "false")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")

    status = otel.configure_telemetry()

    assert status.enabled is False
    assert status.configured is False
    # No exporter was constructed at all, so no endpoint was recorded.
    assert status.endpoint == ""
    assert status.resource_attributes == {}
    assert status.setup_error is None


def test_enabled_with_an_endpoint_reports_gitlab_resource_attributes(monkeypatch):
    """The documented GitLab attributes are read from the CI environment."""
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")
    monkeypatch.setenv("CI_PROJECT_ID", "87424071")
    monkeypatch.setenv("CI_PROJECT_NAME", "rollbackiq")
    monkeypatch.setenv("CI_COMMIT_SHA", "abc1234")
    monkeypatch.setenv("CI_ENVIRONMENT_NAME", "demo-staging")

    status = otel.configure_telemetry()

    assert status.enabled is True
    assert status.configured is True
    assert status.setup_error is None
    # The collector root is normalised to the traces path the SDK posts to.
    assert status.endpoint == "http://127.0.0.1:9/v1/traces"
    assert status.service_name == "rollbackiq-control-plane"

    attributes = status.resource_attributes
    assert attributes["service.name"] == "rollbackiq-control-plane"
    assert attributes["service.version"] == "abc1234"
    assert attributes["deployment.environment.name"] == "demo-staging"
    assert attributes["gitlab.project.id"] == "87424071"
    assert attributes["gitlab.project.name"] == "rollbackiq"


def test_configuring_twice_installs_one_provider(monkeypatch):
    """A second call returns the same status rather than rebuilding."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")

    first = otel.configure_telemetry(service_name="first-name")
    second = otel.configure_telemetry(service_name="second-name")

    assert first is second
    assert second.enabled is True
    # The second call did not replace the installed provider.
    assert second.service_name == "first-name"


# -- telemetry can never change a decision ---------------------------------


def test_a_broken_collector_changes_no_decision():
    """The guard that matters: identical decisions, with and without telemetry.

    Every value compared here — whether detection fired, which breaches it
    named, why it was suppressed, and every verification verdict and reason — is
    produced by the real services. If wiring a span in had changed any of them,
    this comparison fails.
    """
    without_telemetry = (detector_trace(), verification_trace())

    status = otel.configure_telemetry(
        endpoint="http://127.0.0.1:9", service_name="rollbackiq-control-plane"
    )
    assert status.enabled is True

    with_telemetry = (detector_trace(), verification_trace())

    assert with_telemetry[0] == without_telemetry[0]
    assert with_telemetry[1] == without_telemetry[1]
    # And the scripted run really did produce interesting verdicts, so the
    # comparison above is not vacuous.
    assert any(result[0] is True for result in with_telemetry[0])
    assert any(result[0] is False for result in with_telemetry[0])
    assert any(result[0] is True for result in with_telemetry[1])
    assert any(len(result[1]) >= 2 for result in with_telemetry[1])


def test_failing_setup_disables_telemetry_without_raising(monkeypatch):
    """If the SDK cannot be set up, the control plane still decides correctly."""

    def explode(default_service_name: str):
        raise RuntimeError("resource builder unavailable")

    monkeypatch.setattr(otel, "_build_resource", explode)

    status = otel.configure_telemetry(endpoint="http://127.0.0.1:9")

    assert status.enabled is False
    assert status.configured is False
    assert "RuntimeError" in (status.setup_error or "")
    assert "resource builder unavailable" in (status.setup_error or "")

    # With setup broken, the spans are inert no-ops and the decisions are exact.
    detector = RegressionDetector()
    baseline = healthy_baseline()
    first = detector.evaluate(make_window(45.0), baseline, now=T0)
    second = detector.evaluate(
        make_window(45.0), baseline, now=T0 + timedelta(seconds=1)
    )

    assert first.triggered is False
    assert first.breaches == ["P95_LATENCY"]
    assert first.p95_ratio == 4.5
    assert "sustained-window requirement" in (first.suppressed_reason or "")
    assert second.triggered is True
    assert second.breaches == ["P95_LATENCY"]

    verified = verify_recovery(
        expected_release="v1",
        after=make_window(11.0, release="v1", start=T0 + timedelta(seconds=1)),
        baseline=baseline,
        executed_at=T0,
        thresholds=THRESHOLDS,
    )
    assert verified.recovered is True
    assert verified.reasons == []
    assert verified.independent is True


def test_a_failing_export_does_not_reach_the_caller(monkeypatch):
    """An unreachable collector produces a recorded failure, never an exception."""
    network_down = "http://127.0.0.1:9"
    status = otel.configure_telemetry(endpoint=network_down)
    assert status.enabled is True

    # Force the pipeline to try: this is the path a real collector outage takes.
    provider = otel._TYPED.get("provider")
    assert provider is not None
    with otel.span("rollbackiq.test.export-attempt"):
        pass
    provider.force_flush(5000)

    # The detection that produced the span is unaffected either way.
    detector = RegressionDetector()
    result = detector.evaluate(make_window(10.0), healthy_baseline())
    assert result.triggered is False
    assert result.suppressed_reason == "no threshold breached"

    # The failure is visible in the counters rather than swallowed silently.
    assert otel.STATE.export_failures >= 1
    assert otel.STATE.last_export_error
    assert otel.STATE.spans_exported == 0


# -- what a span actually records ------------------------------------------


def test_span_attaches_attributes_to_a_real_span():
    """The live handle writes onto a real span, coercing values safely.

    The tracer is installed directly rather than through
    ``configure_telemetry``, because the process-global provider can only be set
    once and this test is about what the handle does, not about wiring.
    """
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    otel._TYPED["tracer"] = provider.get_tracer("rollbackiq.test")

    try:
        with otel.span(
            "rollbackiq.detector.evaluate",
            {"rollbackiq.detector.samples_seen": 60},
        ) as active:
            active.set(
                {
                    "rollbackiq.detector.triggered": True,
                    "rollbackiq.detector.breaches": ["P95_LATENCY", "ERROR_RATE"],
                    "rollbackiq.detector.p95_ratio": 4.5,
                    "rollbackiq.detector.suppressed_reason": None,
                }
            )
    finally:
        provider.shutdown()
        otel._TYPED.pop("tracer", None)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    recorded = spans[0]
    assert recorded.name == "rollbackiq.detector.evaluate"
    attributes = dict(recorded.attributes)
    assert attributes["rollbackiq.detector.samples_seen"] == 60
    assert attributes["rollbackiq.detector.triggered"] is True
    assert attributes["rollbackiq.detector.breaches"] == "P95_LATENCY,ERROR_RATE"
    assert attributes["rollbackiq.detector.p95_ratio"] == 4.5
    # A None attribute is skipped rather than stringified into "None".
    assert "rollbackiq.detector.suppressed_reason" not in attributes


def test_span_records_an_exception_without_swallowing_it():
    """A failing decision is marked on the span, but the exception still propagates."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.trace import StatusCode

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    otel._TYPED["tracer"] = provider.get_tracer("rollbackiq.test")

    try:
        with pytest.raises(RuntimeError, match="detector exploded"):
            with otel.span("rollbackiq.detector.evaluate"):
                raise RuntimeError("detector exploded")
    finally:
        provider.shutdown()
        otel._TYPED.pop("tracer", None)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code is StatusCode.ERROR
    assert "detector exploded" in (spans[0].status.description or "")


# -- export counting -------------------------------------------------------


def test_counting_exporter_counts_only_accepted_spans():
    """Accepted batches are counted by span; a rejection never counts."""
    inner = FakeExporter(SpanExportResult.SUCCESS)
    exporter = otel.CountingExporter(inner)

    assert exporter.export(["span-a", "span-b"]) == SpanExportResult.SUCCESS
    assert inner.exported == [2]
    assert otel.STATE.spans_exported == 2
    assert otel.STATE.batches_exported == 1
    assert otel.STATE.export_failures == 0

    rejected = FakeExporter(SpanExportResult.FAILURE)
    assert otel.CountingExporter(rejected).export(["span-c"]) == SpanExportResult.FAILURE

    assert otel.STATE.spans_exported == 2
    assert otel.STATE.batches_exported == 1
    assert otel.STATE.export_failures == 1
    assert "FAILURE" in (otel.STATE.last_export_error or "")
    assert "1 span(s)" in (otel.STATE.last_export_error or "")


def test_counting_exporter_records_a_raising_exporter_without_propagating():
    """A broken collector is a recorded failure, not an exception in the caller."""
    broken = FakeExporter(error=RuntimeError("collector unreachable"))

    result = otel.CountingExporter(broken).export(["span-a"])

    assert result == SpanExportResult.FAILURE
    assert otel.STATE.spans_exported == 0
    assert otel.STATE.export_failures == 1
    assert "RuntimeError" in (otel.STATE.last_export_error or "")
    assert "collector unreachable" in (otel.STATE.last_export_error or "")


def test_export_counting_holds_through_the_real_sdk_pipeline():
    """Counts come from the exporter's real return value, via the SDK's processor."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    accepted = FakeExporter(SpanExportResult.SUCCESS)
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(otel.CountingExporter(accepted)))
    tracer = provider.get_tracer("rollbackiq.test")
    try:
        with tracer.start_as_current_span("first"):
            pass
        with tracer.start_as_current_span("second"):
            pass
    finally:
        provider.shutdown()

    assert otel.STATE.spans_exported == 2
    assert otel.STATE.batches_exported == 2
    assert otel.STATE.export_failures == 0

    rejected = FakeExporter(error=RuntimeError("collector unreachable"))
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(otel.CountingExporter(rejected)))
    tracer = provider.get_tracer("rollbackiq.test")
    try:
        with tracer.start_as_current_span("third"):
            pass
    finally:
        provider.shutdown()

    assert otel.STATE.spans_exported == 2
    assert otel.STATE.export_failures == 1
    assert "collector unreachable" in (otel.STATE.last_export_error or "")
