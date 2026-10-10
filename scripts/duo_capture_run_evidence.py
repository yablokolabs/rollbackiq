#!/usr/bin/env python3
"""Capture bounded evidence from `duo run --output-format json` results.

Every claim in the documentation about what a GitLab Duo flow did has to be
backed by a captured artifact. The raw CLI output cannot be committed, though:
the Duo CLI embeds ``AGENTS.md`` into the session as ``plan_context``, and
``AGENTS.md`` quotes the prohibited attribution strings verbatim as policy, so
the raw log carries text the attribution guard forbids. A policy quotation is
not a reason to weaken the guard, so this script extracts only bounded,
non-content fields and the run's own response text.

What is captured, per run:

* ``sessionId``, ``status``, ``exitCode``, ``schemaVersion`` from stdout;
* the response text and its length, plus element counts by type;
* from the matching ``.err`` log, only *structure*: which tool actions the flow
  requested and which flow identity was negotiated on the wire. Log bodies are
  never copied.

    .venv/bin/python scripts/duo_capture_run_evidence.py OUT.json RUN [RUN ...]
    # RUN is a path to a `duo run --output-format json` stdout file; the matching
    # .err and .status files are picked up beside it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Tool action names the workflow requested, e.g. `...,"runShellCommand"`.
ACTION_RE = re.compile(r'Action received: \{"requestID":"[a-f0-9-]+","([a-zA-Z]+)"')
#: The flow identity the CLI actually negotiated, read from the wire URL.
DEFINITION_RE = re.compile(r"workflow_definition=([A-Za-z0-9%\-/]+)")
FLOW_CONFIG_ID_RE = re.compile(r'"flowConfigId": "([^"]*)"')


def capture_run(stdout_path: Path) -> Dict[str, Any]:
    result = json.loads(stdout_path.read_text())
    err_path = stdout_path.with_suffix(".err")
    status_path = stdout_path.with_suffix(".status")

    elements = result.get("elements") or []
    by_type = Counter(e.get("type") for e in elements)

    record: Dict[str, Any] = {
        "stdout_file": stdout_path.name,
        "session_id": result.get("sessionId"),
        "status": result.get("status"),
        "exit_code": result.get("exitCode"),
        "schema_version": result.get("schemaVersion"),
        "response_chars": len(result.get("response") or ""),
        "response": result.get("response"),
        "elements_total": len(elements),
        "elements_by_type": dict(sorted(by_type.items())),
    }

    if status_path.exists():
        record["process_status"] = status_path.read_text().strip()

    if err_path.exists():
        err = err_path.read_text(errors="replace")
        record["requested_actions"] = dict(sorted(Counter(ACTION_RE.findall(err)).items()))
        record["negotiated_flow_definition"] = sorted(set(DEFINITION_RE.findall(err)))
        record["negotiated_flow_config_ids"] = sorted(set(FLOW_CONFIG_ID_RE.findall(err)))

    return record


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", help="evidence JSON path to write")
    parser.add_argument("runs", nargs="+", help="`duo run --output-format json` stdout files")
    args = parser.parse_args(argv[1:])

    records: List[Dict[str, Any]] = []
    for raw in args.runs:
        path = Path(raw)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.exists():
            print(f"missing run output: {path}", file=sys.stderr)
            return 2
        records.append(capture_run(path))

    evidence = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "captured_with": "scripts/duo_capture_run_evidence.py",
        "invocation": "duo run --output-format json (see docs/PROGRESS.md for the exact flags)",
        "excluded_and_why": (
            "raw CLI stdout/stderr are not committed: the Duo CLI embeds AGENTS.md as "
            "plan_context and AGENTS.md quotes the prohibited attribution strings as policy, "
            "so the raw log trips the attribution guard. Only bounded fields above are kept."
        ),
        "runs": records,
    }

    target = Path(args.out)
    if not target.is_absolute():
        target = REPO_ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, indent=2) + "\n")

    for record in records:
        print(
            f"session {record['session_id']} status={record['status']} "
            f"exit={record['exit_code']} response={record['response_chars']} chars "
            f"definition={record.get('negotiated_flow_definition')} "
            f"actions={record.get('requested_actions')}"
        )
    shown = target.relative_to(REPO_ROOT) if target.is_relative_to(REPO_ROOT) else target
    print(f"written: {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
