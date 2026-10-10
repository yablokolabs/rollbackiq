#!/usr/bin/env python3
"""Probe the GitLab MCP server and record exactly what it answers.

The GitLab MCP server is documented at ``POST <instance>/api/v4/mcp`` (streamable
HTTP), with OAuth 2.0 dynamic client registration as the documented way to
authenticate. This probe is read-only: it sends the MCP ``initialize`` and
``tools/list`` requests, and optionally one read-only ``tools/call``, and writes
the HTTP status and the server's own answer to an evidence file.

    GITLAB_TOKEN=... .venv/bin/python scripts/gitlab_mcp_probe.py

    GITLAB_TOKEN=... .venv/bin/python scripts/gitlab_mcp_probe.py \
        --call get_mcp_server_version

Exit status is 0 only when the server lists its tools (and, with ``--call``, the
tool call returns without an error). A refusal exits 1 and is recorded with the
server's own status and message, so MCP use cannot be claimed from a failed probe.

The token is read from GITLAB_TOKEN and is never written to the evidence file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_VERSION = "2025-06-18"


def _decode(response: httpx.Response) -> Optional[Dict[str, Any]]:
    """Return the JSON-RPC message from a JSON or an event-stream response."""
    text = response.text
    if "text/event-stream" in response.headers.get("content-type", ""):
        data = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        text = data[-1] if data else ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _exchange(
    client: httpx.Client, url: str, request_id: int, method: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    try:
        response = client.post(
            url, json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
    except httpx.HTTPError as exc:
        return {"method": method, "http_status": None, "transport_error": str(exc)}
    message = _decode(response)
    session_id = response.headers.get("mcp-session-id")
    if session_id:
        client.headers["Mcp-Session-Id"] = session_id
    return {
        "method": method,
        "http_status": response.status_code,
        "www_authenticate": response.headers.get("www-authenticate"),
        "message": message,
        "raw_body": None if message is not None else response.text[:600],
    }


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--call", default="", help="one read-only tool to call after listing")
    parser.add_argument("--arguments", default="{}", help="JSON arguments for --call")
    parser.add_argument("--evidence", default="evidence/gitlab-mcp-probe.json")
    args = parser.parse_args(argv[1:])

    token = os.getenv("GITLAB_TOKEN", "")
    if not token:
        print("GITLAB_TOKEN is not set", file=sys.stderr)
        return 2

    url = os.getenv("GITLAB_URL", "https://gitlab.com").rstrip("/") + "/api/v4/mcp"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
    }
    exchanges: List[Dict[str, Any]] = []
    # Asked without credentials first: the server's challenge names the scope it requires.
    try:
        challenge = httpx.post(url, json={}, timeout=60.0).headers.get("www-authenticate")
    except httpx.HTTPError as exc:
        challenge = f"transport error: {exc}"
    with httpx.Client(headers=headers, timeout=60.0) as client:
        exchanges.append(
            _exchange(
                client, url, 1, "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "rollbackiq-mcp-probe", "version": "0.1.0"},
                },
            )
        )
        exchanges.append(_exchange(client, url, 2, "tools/list", {}))
        if args.call:
            exchanges.append(
                _exchange(
                    client, url, 3, "tools/call",
                    {"name": args.call, "arguments": json.loads(args.arguments)},
                )
            )

    listing = (exchanges[1].get("message") or {}).get("result") or {}
    tools = [
        {"name": tool.get("name"), "description": (tool.get("description") or "")[:200]}
        for tool in listing.get("tools") or []
    ]
    exchanges[1]["message"] = (
        {"result": {"tools": f"{len(tools)} tool(s), listed under 'tools'"}}
        if tools
        else exchanges[1].get("message")
    )

    call = exchanges[2] if args.call else None
    call_message = (call or {}).get("message") or {}
    call_ok = call is None or (
        call.get("http_status") == 200
        and "error" not in call_message
        and not (call_message.get("result") or {}).get("isError")
    )

    record = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "captured_with": "scripts/gitlab_mcp_probe.py",
        "endpoint": url,
        "authentication": "Bearer personal access token from GITLAB_TOKEN (value not recorded)",
        "protocol_version_requested": PROTOCOL_VERSION,
        "unauthenticated_challenge": challenge,
        "tools_listed": len(tools),
        "tools": tools,
        "tool_called": args.call or None,
        "exchanges": exchanges,
    }
    target = Path(args.evidence)
    target = target if target.is_absolute() else REPO_ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2) + "\n")

    for exchange in exchanges:
        print(f"{exchange['method']}: HTTP {exchange['http_status']}")
    print(f"server challenge without credentials: {challenge}")
    print(f"tools listed: {len(tools)}")
    print(f"written: {target}")
    return 0 if tools and call_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
