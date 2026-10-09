"""Telemetry wiring tests: instrumentation must report what it really did.

The module under test is ``demo/service/otel_setup.py``. Two claims are worth
pinning down, because both are easy to state and easy to get wrong:

* instrumentation is strictly opt-in — with no collector configured the workload
  must run untouched and say so, and an explicit ``OTEL_ENABLED=false`` must win
  even when an endpoint is present;
* the reported counters come from the exporter's real return value, so a
  rejected batch is never counted as a successful one.

No network is touched: enabling instrumentation with an unroutable endpoint is
enough, because the exporter only connects when a batch is exported.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

# ``app.py`` puts its own directory on the path for the same reason: the
# workload is a self-contained directory rather than an installed package.
SERVICE_DIR = pathlib.Path(__file__).resolve().parents[2] / "demo" / "service"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from fastapi import FastAPI  # noqa: E402
from opentelemetry.sdk.trace.export import SpanExportResult  # noqa: E402

import otel_setup  # noqa: E402

#: Any of these being set in the ambient environment would change the outcome,
#: so each test starts from a known-clean slate.
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
    "RELEASE_COMMIT_SHA",
    "DEPLOY_ENV",
)


@pytest.fixture(autouse=True)
def clean_telemetry_state(monkeypatch):
    """Reset module-level state and remove every variable that steers it."""
    for name in CONFIGURED_VARIABLES:
        monkeypatch.delenv(name, raising=False)

    otel_setup.STATE.enabled = False
    otel_setup.STATE.endpoint = ""
    otel_setup.STATE.service_name = ""
    otel_setup.STATE.resource_attributes = {}
    otel_setup.STATE.batches_sent = 0
    otel_setup.STATE.spans_sent = 0
    otel_setup.STATE.failures = 0
    otel_setup.STATE.last_error = None
    otel_setup.STATE.setup_error = None
    otel_setup.TYPED.clear()
    yield


class FakeExporter:
    """Stand-in for the network exporter, which is not what is under test.

    ``CountingExporter`` is; this only needs to reproduce the three methods it
    calls and to be able to return a chosen result or raise.
    """

    def __init__(self, result: SpanExportResult | None = SpanExportResult.SUCCESS, error: Exception | None = None):
        self.result = result
        self.error = error
        self.exported: list[int] = []
        self.shutdown_called = False
        self.flush_timeouts: list[int] = []

    def export(self, spans):
        self.exported.append(len(list(spans)))
        if self.error is not None:
            raise self.error
        return self.result

    def shutdown(self):
        self.shutdown_called = True

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        self.flush_timeouts.append(timeout_millis)
        return True


def test_telemetry_is_disabled_when_no_collector_is_configured():
    """A local run has no collector, so nothing is instrumented and nothing invented."""
    report = otel_setup.setup_telemetry(object())

    assert report["telemetry_enabled"] is False
    assert report["exporter_endpoint"] == ""
    assert report["service_name"] == ""
    assert report["resource_attributes"] == {}
    assert report["setup_error"] is None
    # Nothing was claimed about exports that never happened.
    assert report["spans_exported"] == 0
    assert report["batches_exported"] == 0
    assert report["export_failures"] == 0
    # And the live report agrees with the value setup returned.
    assert otel_setup.report() == report


def test_explicitly_disabled_ignores_a_configured_endpoint(monkeypatch):
    """Opting out is absolute: an endpoint on the box must not turn telemetry on."""
    monkeypatch.setenv("OTEL_ENABLED", "false")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")

    report = otel_setup.setup_telemetry(object())

    assert report["telemetry_enabled"] is False
    # No exporter was constructed at all, so no endpoint was recorded.
    assert report["exporter_endpoint"] == ""
    assert report["resource_attributes"] == {}
    assert report["setup_error"] is None


def test_enabled_telemetry_reports_its_resources_and_endpoint(monkeypatch):
    """With a collector configured, the documented GitLab attributes are set.

    A real ``FastAPI`` instance is used rather than a bare object because
    instrumenting a FastAPI app is the code path that ships; a stub would only
    exercise the failure branch. The endpoint is unroutable on purpose — the
    exporter opens no connection until a batch is exported.
    """
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")
    monkeypatch.setenv("CI_PROJECT_ID", "87424071")
    monkeypatch.setenv("CI_PROJECT_NAME", "rollbackiq")
    monkeypatch.setenv("CI_COMMIT_SHA", "abc1234")
    monkeypatch.setenv("CI_ENVIRONMENT_NAME", "demo-staging")

    app = FastAPI(title="telemetry test app")
    report = otel_setup.setup_telemetry(app, default_service_name="rollbackiq-test")

    try:
        assert report["telemetry_enabled"] is True
        assert report["setup_error"] is None

        # The collector root is normalised to the traces path the SDK posts to.
        assert report["exporter_endpoint"] == "http://127.0.0.1:9/v1/traces"

        attributes = report["resource_attributes"]
        # service.name falls back to CI_PROJECT_NAME when OTEL_SERVICE_NAME is unset.
        assert report["service_name"] == "rollbackiq"
        assert attributes["service.name"] == "rollbackiq"
        assert attributes["service.version"] == "abc1234"
        assert attributes["deployment.environment.name"] == "demo-staging"
        assert attributes["gitlab.project.id"] == "87424071"
        assert attributes["gitlab.project.name"] == "rollbackiq"

        # The tracer provider is global to the process and can only be set once;
        # re-setting it is a logged no-op in the OpenTelemetry API rather than an
        # error, which is why setup reports success here.
        assert otel_setup.get_tracer() is not None
    finally:
        # Stop the batch processor thread: otherwise a later export attempt could
        # increment the counters a subsequent test asserts on.
        provider = otel_setup.TYPED.get("provider")
        if provider is not None:
            provider.shutdown()
        otel_setup.TYPED.clear()


def test_counting_exporter_counts_spans_the_real_exporter_accepted():
    """Accepted batches are counted by span, so the number is auditable."""
    inner = FakeExporter(SpanExportResult.SUCCESS)
    exporter = otel_setup.CountingExporter(inner)

    result = exporter.export(["span-a", "span-b"])

    assert result == SpanExportResult.SUCCESS
    assert inner.exported == [2]
    assert otel_setup.STATE.spans_sent == 2
    assert otel_setup.STATE.batches_sent == 1
    assert otel_setup.STATE.failures == 0

    exporter.export(["span-c"])
    assert otel_setup.STATE.spans_sent == 3
    assert otel_setup.STATE.batches_sent == 2


def test_counting_exporter_records_rejections_without_raising():
    """A rejected batch or a broken exporter must be recorded, never propagated."""
    rejected = FakeExporter(SpanExportResult.FAILURE)
    result = otel_setup.CountingExporter(rejected).export(["span-a"])

    assert result == SpanExportResult.FAILURE
    assert otel_setup.STATE.spans_sent == 0
    assert otel_setup.STATE.failures == 1
    assert "FAILURE" in (otel_setup.STATE.last_error or "")
    assert "1 span(s)" in (otel_setup.STATE.last_error or "")

    # A raising exporter is a failure as well; it must not take the workload down.
    broken = FakeExporter(error=RuntimeError("collector unreachable"))
    result = otel_setup.CountingExporter(broken).export(["span-b"])

    assert result == SpanExportResult.FAILURE
    assert otel_setup.STATE.spans_sent == 0
    assert otel_setup.STATE.failures == 2
    assert "RuntimeError" in (otel_setup.STATE.last_error or "")
    assert "collector unreachable" in (otel_setup.STATE.last_error or "")


def test_counting_exporter_delegates_shutdown_and_flush():
    """Shutdown and flush reach the real exporter instead of being swallowed."""
    inner = FakeExporter()
    exporter = otel_setup.CountingExporter(inner)

    assert exporter.force_flush(1234) is True
    exporter.shutdown()

    assert inner.flush_timeouts == [1234]
    assert inner.shutdown_called is True
