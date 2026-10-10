#!/usr/bin/env python3
"""Trigger the RollbackIQ Duo flow through a real trigger surface and watch it.

The custom flow is registered in the GitLab AI Catalog, enabled in the project,
and attached to a flow trigger with the mention and assign event types. This
script exercises the **mention** trigger exactly as the platform documents it: it
posts a comment that mentions the flow's service account, then polls the
resulting Duo workflow session through GitLab's GraphQL API until it reaches a
terminal status.

It is deliberately an external observer — it never talks to the flow runtime,
only to GitLab's public API — so the captured status and messages are the
platform's own record of the run, not this script's claim about it.

    GITLAB_TOKEN=... .venv/bin/python scripts/duo_trigger_flow.py \
        --issue-iid 2 --evidence evidence/duo-flow-trigger-session.json

Exit status is 0 only when the session reaches FINISHED. Every other terminal
status (FAILED, STOPPED, PAUSED, INPUT_REQUIRED) exits 1 and is recorded with the
session's own error text, so a failed run cannot be reported as a success.

GitLab can stop answering at any point. If the trigger note cannot be posted, the
script exits 1 and writes no evidence file, because nothing happened. If GitLab
fails after the note was accepted, each failed poll is recorded in ``poll_errors``
and polling continues until the timeout, so the evidence file always names the
note that GitLab accepted.

The token is read from GITLAB_TOKEN and is never written to the evidence file.
GITLAB_URL selects the instance (default https://gitlab.com).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

DEFAULT_GITLAB_URL = "https://gitlab.com"
REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_PROJECT_ID = "87424071"
DEFAULT_SERVICE_ACCOUNT = "ai-rollbackiq-recovery-investigator-flow-gitlab-ai-hackathon"
DEFAULT_MESSAGE = (
    "@{service_account} investigate this incident and recommend a course of action.\n\n"
    "State which hypotheses the evidence supports and which it contradicts, name what you "
    "cannot distinguish and what observation would resolve it, and recommend roll back, hold "
    "or escalate with the residual risk of that choice.\n\n"
    "Report only what you can actually retrieve from this work item and the repository, and "
    "mark anything you could not retrieve as missing. Keep the reply under 400 words."
)

TERMINAL_STATUSES = {"FINISHED", "FAILED", "STOPPED", "PAUSED", "INPUT_REQUIRED"}

WORKFLOWS_QUERY = """
query LatestWorkflows($path: ID!) {
  project(fullPath: $path) {
    duoWorkflowWorkflows(first: 5, sort: UPDATED_DESC) {
      nodes {
        id
        status
        humanStatus
        workflowDefinition
        agentName
        goal
        createdAt
        updatedAt
      }
    }
  }
}
"""

EVENTS_QUERY = """
query SessionEvents($path: ID!, $workflowId: AiDuoWorkflowsWorkflowID!) {
  project(fullPath: $path) {
    duoWorkflowEvents(workflowId: $workflowId, first: 30) {
      nodes {
        workflowStatus
        executionStatus
        errors
        lastDuoMessage { content messageType }
      }
    }
  }
}
"""


def resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def post_mention(
    client: httpx.Client, rest: str, project_id: str, issue_iid: str, body: str
) -> Dict[str, Any]:
    response = client.post(
        f"{rest}/projects/{project_id}/issues/{issue_iid}/notes",
        data={"body": body},
    )
    response.raise_for_status()
    note = response.json()
    return {"id": note["id"], "url": f"{rest}/projects/{project_id}/issues/{issue_iid}/notes/{note['id']}"}


def graphql(
    client: httpx.Client, endpoint: str, query: str, variables: Dict[str, Any]
) -> Dict[str, Any]:
    response = client.post(endpoint, json={"query": query, "variables": variables})
    response.raise_for_status()
    body = response.json()
    if body.get("errors"):
        raise RuntimeError(
            "GraphQL rejected the query: "
            + "; ".join(e.get("message", "?") for e in body["errors"])
        )
    return body.get("data") or {}


def latest_session(
    client: httpx.Client, endpoint: str, project_path: str, after: datetime
) -> Optional[Dict[str, Any]]:
    data = graphql(client, endpoint, WORKFLOWS_QUERY, {"path": project_path})
    nodes = ((data.get("project") or {}).get("duoWorkflowWorkflows") or {}).get("nodes") or []
    candidates = [
        node for node in nodes if node.get("createdAt") and _parse(node["createdAt"]) >= after
    ]
    if not candidates:
        return None
    return candidates[0]


def session_events(
    client: httpx.Client, endpoint: str, project_path: str, workflow_id: str
) -> List[Dict[str, Any]]:
    data = graphql(
        client, endpoint, EVENTS_QUERY, {"path": project_path, "workflowId": workflow_id}
    )
    nodes = ((data.get("project") or {}).get("duoWorkflowEvents") or {}).get("nodes") or []
    events = []
    for node in nodes:
        message = node.get("lastDuoMessage") or {}
        events.append(
            {
                "workflow_status": node.get("workflowStatus"),
                "execution_status": node.get("executionStatus"),
                "errors": node.get("errors"),
                "last_message": (message.get("content") or "")[:2000] or None,
                "message_type": message.get("messageType"),
            }
        )
    return events


def issue_note_authors(
    client: httpx.Client, rest: str, project_id: str, issue_iid: str
) -> List[Dict[str, Any]]:
    response = client.get(
        f"{rest}/projects/{project_id}/issues/{issue_iid}/notes",
        params={"sort": "desc", "per_page": 10},
    )
    response.raise_for_status()
    return [
        {
            "id": note["id"],
            "author": (note.get("author") or {}).get("username"),
            "system": note.get("system"),
            "created_at": note.get("created_at"),
            "body": (note.get("body") or "")[:400],
        }
        for note in response.json()
    ]


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-id", default=os.getenv("GITLAB_PROJECT_ID", DEFAULT_PROJECT_ID))
    parser.add_argument("--project-path", default="gitlab-ai-hackathon/transcend-october-2026/43178176/showcase")
    parser.add_argument("--issue-iid", default="2")
    parser.add_argument("--service-account", default=DEFAULT_SERVICE_ACCOUNT)
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=420)
    parser.add_argument("--evidence", default="evidence/duo-flow-trigger-session.json")
    args = parser.parse_args(argv[1:])

    token = os.getenv("GITLAB_TOKEN", "")
    if not token:
        print("GITLAB_TOKEN is not set", file=sys.stderr)
        return 2

    body = args.message.replace("{service_account}", args.service_account)
    if f"@{args.service_account}" not in body:
        body = f"@{args.service_account} {body}"

    gitlab_url = os.getenv("GITLAB_URL", DEFAULT_GITLAB_URL).rstrip("/")
    rest_url = f"{gitlab_url}/api/v4"
    graphql_url = f"{gitlab_url}/api/graphql"

    fired_at = datetime.now(timezone.utc)
    poll_errors: List[str] = []
    with httpx.Client(headers={"PRIVATE-TOKEN": token}, timeout=60.0) as rest:
        try:
            note = post_mention(rest, rest_url, args.project_id, args.issue_iid, body)
        except httpx.HTTPError as exc:
            print(
                f"GitLab did not accept the trigger note, so no flow was started: {exc}",
                file=sys.stderr,
            )
            return 1
        print(f"trigger note posted: {note['id']}")

        with httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=60.0) as gql:
            session: Optional[Dict[str, Any]] = None
            deadline = time.monotonic() + args.timeout_seconds
            while time.monotonic() < deadline:
                time.sleep(args.poll_seconds)
                try:
                    session = latest_session(gql, graphql_url, args.project_path, fired_at)
                except (httpx.HTTPError, RuntimeError) as exc:
                    # The note is already posted, so the session may still run. Stopping
                    # here would lose the record of it; the timeout bounds the retries.
                    poll_errors.append(str(exc))
                    print(f"  GitLab did not answer the poll: {exc}")
                    time.sleep(1)
                    continue
                if session is None:
                    print("  waiting for the platform to create a session ...")
                    continue
                print(f"  session {session['id'].rsplit('/', 1)[-1]} status={session['status']}")
                if session["status"] in TERMINAL_STATUSES:
                    break

            events: List[Dict[str, Any]] = []
            notes_after: List[Dict[str, Any]] = []
            try:
                if session is not None:
                    events = session_events(gql, graphql_url, args.project_path, session["id"])
                notes_after = issue_note_authors(rest, rest_url, args.project_id, args.issue_iid)
            except (httpx.HTTPError, RuntimeError) as exc:
                poll_errors.append(str(exc))

    record = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "captured_with": "scripts/duo_trigger_flow.py (GitLab REST + GraphQL APIs)",
        "trigger_surface": "flow trigger event type 'mention' (service account mentioned in an issue comment)",
        "project_id": args.project_id,
        "issue_iid": args.issue_iid,
        "service_account": args.service_account,
        "trigger_note": note,
        "fired_at": fired_at.isoformat(),
        "session": session,
        "poll_errors": poll_errors,
        "events": events,
        "issue_notes_after_run": notes_after,
    }

    target = resolve(args.evidence)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2) + "\n")

    if session is None:
        print("no session was created before the timeout", file=sys.stderr)
        return 1

    status = session["status"]
    print(f"\nsession {session['id']}")
    print(f"status: {status}   human status: {session.get('humanStatus')}")
    for event in events[:3]:
        if event.get("errors"):
            print("errors:", json.dumps(event["errors"])[:800])
        if event.get("last_message"):
            print("message:", event["last_message"][:800].replace("\n", " "))
    print(f"written: {display(target)}")
    return 0 if status == "FINISHED" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
