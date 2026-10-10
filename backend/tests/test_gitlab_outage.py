"""Tests for the Duo trigger script when GitLab is unavailable.

The script's evidence file is the record that a Duo session ran, so the cases
that matter are the ones where GitLab stops answering: the script must exit
non-zero, must not report a session it did not observe, and must not lose the
record of a trigger note that GitLab already accepted.

A real HTTP server on a local port plays GitLab, so the script's own HTTP
handling is what is exercised.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

FINISHED_SESSION = {
    "data": {
        "project": {
            "duoWorkflowWorkflows": {
                "nodes": [
                    {
                        "id": "gid://gitlab/Ai::DuoWorkflows::Workflow/4242",
                        "status": "FINISHED",
                        "humanStatus": "finished",
                        "workflowDefinition": "rollbackiq/recovery-investigator/v1",
                        "agentName": "RollbackIQ Recovery Investigator Flow",
                        "goal": "investigate",
                        "createdAt": "2099-01-01T00:00:00Z",
                        "updatedAt": "2099-01-01T00:01:00Z",
                    }
                ]
            }
        }
    }
}
NO_EVENTS = {"data": {"project": {"duoWorkflowEvents": {"nodes": []}}}}


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "duo_trigger_flow", SCRIPTS / "duo_trigger_flow.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["duo_trigger_flow"] = module
    spec.loader.exec_module(module)
    return module


class FakeGitLab:
    """A local HTTP server that answers like GitLab, with scripted GraphQL replies."""

    def __init__(self, graphql_replies: List[object]) -> None:
        self.graphql_replies = list(graphql_replies)
        self.notes_posted: List[Dict[str, str]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def _send(self, status: int, payload: object) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode()
                if self.path.endswith("/notes"):
                    fake.notes_posted.append({"path": self.path, "body": raw})
                    self._send(201, {"id": 555})
                    return
                if self.path.endswith("/api/graphql"):
                    reply = (
                        fake.graphql_replies.pop(0)
                        if len(fake.graphql_replies) > 1
                        else fake.graphql_replies[0]
                    )
                    if isinstance(reply, int):
                        self._send(reply, {"message": "GitLab is not responding"})
                    else:
                        self._send(200, reply)
                    return
                self._send(404, {})

            def do_GET(self) -> None:
                self._send(200, [])

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeGitLab":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()


def _closed_port_url() -> str:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def _run(monkeypatch: pytest.MonkeyPatch, gitlab_url: str, evidence: Path) -> int:
    monkeypatch.setenv("GITLAB_TOKEN", "test-token-not-a-secret")
    monkeypatch.setenv("GITLAB_URL", gitlab_url)
    script = _load_script()
    return script.main(
        [
            "duo_trigger_flow.py",
            "--project-id", "1",
            "--project-path", "group/project",
            "--poll-seconds", "0",
            "--timeout-seconds", "2",
            "--evidence", str(evidence),
        ]
    )


def test_unreachable_gitlab_exits_non_zero_and_writes_no_evidence(monkeypatch, tmp_path, capsys):
    evidence = tmp_path / "session.json"

    code = _run(monkeypatch, _closed_port_url(), evidence)

    assert code != 0
    assert not evidence.exists()
    assert "GitLab" in capsys.readouterr().err


def test_outage_after_the_trigger_keeps_the_note_and_reports_no_session(
    monkeypatch, tmp_path
):
    evidence = tmp_path / "session.json"

    with FakeGitLab(graphql_replies=[502]) as gitlab:
        code = _run(monkeypatch, gitlab.url, evidence)

    assert code != 0
    assert len(gitlab.notes_posted) == 1
    record = json.loads(evidence.read_text())
    assert record["trigger_note"]["id"] == 555
    assert record["session"] is None
    assert record["poll_errors"]
    assert "502" in record["poll_errors"][0]
    assert "test-token-not-a-secret" not in evidence.read_text()


def test_a_transient_gitlab_error_does_not_lose_a_finished_session(monkeypatch, tmp_path):
    evidence = tmp_path / "session.json"

    with FakeGitLab(graphql_replies=[502, FINISHED_SESSION, NO_EVENTS]) as gitlab:
        code = _run(monkeypatch, gitlab.url, evidence)

    assert code == 0
    record = json.loads(evidence.read_text())
    assert record["session"]["status"] == "FINISHED"
    assert len(record["poll_errors"]) == 1
