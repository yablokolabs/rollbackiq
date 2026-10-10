"""Tests for the independent probe's input.

The probe's window is the evidence for detection and for recovery, so it must
measure an HTTP service and nothing else. A local HTTP server plays the workload.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load_probe():
    spec = importlib.util.spec_from_file_location("ci_probe", SCRIPTS / "ci_probe.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ci_probe"] = module
    spec.loader.exec_module(module)
    return module


class _Workload(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:
        body = json.dumps({"release": "v1", "environment": "demo-staging"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.mark.parametrize("url", ["file:///etc/hostname", "ftp://example.invalid/x", "workload:8000"])
def test_a_url_that_is_not_http_is_refused_and_no_window_is_written(url, tmp_path, capsys):
    out = tmp_path / "window.json"

    with pytest.raises(SystemExit) as refusal:
        _load_probe().main(["--url", url, "--samples", "3", "--out", str(out)])

    assert refusal.value.code != 0
    assert not out.exists()
    assert "http" in capsys.readouterr().err


def test_an_http_service_is_measured_with_one_sample_for_each_request(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Workload)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    out = tmp_path / "window.json"
    try:
        code = _load_probe().main(
            ["--url", f"http://127.0.0.1:{server.server_address[1]}", "--samples", "12",
             "--concurrency", "3", "--out", str(out)]
        )
    finally:
        server.shutdown()
        server.server_close()

    window = json.loads(out.read_text())
    assert code == 0
    assert window["request_count"] == 12
    assert window["error_count"] == 0
