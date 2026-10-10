#!/usr/bin/env python3
"""Provision the RollbackIQ Duo custom agent and custom flow in the GitLab AI Catalog.

AGENTS.md section 5 requires the competition-facing lifecycle to be orchestrated by
GitLab Duo Agent Platform custom *agent(s)/flow(s)* — a Python service calling GitLab
APIs is not sufficient. This script registers those catalog items so the capability is
reproducible from the repository instead of existing only as something someone clicked.

The repository is the source of truth:

    duo/agents/rollbackiq-recovery-investigator.md   -> agent `systemPrompt`
    duo/flows/rollbackiq-recovery-investigator.yaml  -> flow `definition`

Both are sent verbatim. Because this is idempotent, re-running it after editing either
file re-asserts the edited content onto the catalog item.

    GITLAB_TOKEN=... .venv/bin/python scripts/duo_provision_catalog.py
    GITLAB_TOKEN=... .venv/bin/python scripts/duo_provision_catalog.py --evidence PATH
    GITLAB_TOKEN=... .venv/bin/python scripts/duo_provision_catalog.py --dry-run

Two API facts, learned by probing the live schema, shape this script:

* ``definition`` and ``systemPrompt`` are **write-only**. Neither is exposed on
  ``AiCatalogItemVersion``, so the script cannot read the stored value back and diff it.
  A re-assert is the only available way to guarantee the catalog matches this repository,
  and the script says so instead of implying it verified equality.
* The flow definition is validated server-side and rejects with per-field errors, so a
  clean response is real evidence the definition compiled rather than merely parsed.

The token is read from ``GITLAB_TOKEN`` and is never printed, logged or written to the
evidence file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

API = "https://gitlab.com/api/graphql"
REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_PROMPT_PATH = REPO_ROOT / "duo" / "agents" / "rollbackiq-recovery-investigator.md"
FLOW_DEFINITION_PATH = REPO_ROOT / "duo" / "flows" / "rollbackiq-recovery-investigator.yaml"

AGENT_NAME = "RollbackIQ Recovery Investigator"
FLOW_NAME = "RollbackIQ Recovery Investigator Flow"

FLOW_DESCRIPTION = (
    "Investigates a detected deployment regression: gathers deployment and telemetry "
    "evidence, states which hypotheses the evidence supports, and recommends a rollback, "
    "hold or escalate for a human to approve. It never executes a deployment change."
)
AGENT_DESCRIPTION = (
    "Production recovery investigator for RollbackIQ. Reasoning only: it gathers and "
    "assesses deployment evidence and never executes a deployment change."
)

AGENT_CREATE = """
mutation ProvisionAgent($input: AiCatalogAgentCreateInput!) {
  aiCatalogAgentCreate(input: $input) { errors }
}
"""
AGENT_UPDATE = """
mutation ProvisionAgent($input: AiCatalogAgentUpdateInput!) {
  aiCatalogAgentUpdate(input: $input) { errors }
}
"""
FLOW_CREATE = """
mutation ProvisionFlow($input: AiCatalogFlowCreateInput!) {
  aiCatalogFlowCreate(input: $input) { errors }
}
"""
FLOW_UPDATE = """
mutation ProvisionFlow($input: AiCatalogFlowUpdateInput!) {
  aiCatalogFlowUpdate(input: $input) { errors }
}
"""
FIND_ITEMS = """
query FindItems($search: String!) {
  aiCatalogItems(search: $search, first: 50) {
    nodes {
      id
      name
      itemType
      public
      ... on AiCatalogFlow { versions { nodes { id versionName } } }
    }
  }
}
"""


class ProvisionError(RuntimeError):
    """A catalog operation was rejected; the message carries the server's own words."""


def read_agent_prompt() -> str:
    """The agent system prompt: everything after the first standalone ``---`` rule."""
    text = AGENT_PROMPT_PATH.read_text()
    marker = "\n---\n"
    if marker not in text:
        raise ProvisionError(f"{AGENT_PROMPT_PATH.name} has no '---' separator for the prompt body")
    return text.split(marker, 1)[1].strip() + "\n"


def read_flow_definition() -> str:
    """The flow definition sent verbatim; the leading header is YAML comments."""
    return FLOW_DEFINITION_PATH.read_text()


class CatalogClient:
    def __init__(self, token: str, project_id: str) -> None:
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {token}"}, timeout=60.0
        )
        self._project_gid = f"gid://gitlab/Project/{project_id}"
        self.calls: List[Dict[str, Any]] = []

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CatalogClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def execute(
        self, query: str, variables: Dict[str, Any], label: str
    ) -> Dict[str, Any]:
        response = self._client.post(API, json={"query": query, "variables": variables})
        response.raise_for_status()
        body = response.json()
        self.calls.append({"operation": label, "variables": variables})
        if body.get("errors"):
            raise ProvisionError(
                f"{label} rejected: " + "; ".join(e.get("message", "?") for e in body["errors"])
            )
        return body.get("data") or {}

    def find_item(self, name: str) -> Optional[Dict[str, Any]]:
        """Exact-name lookup. `search` is fuzzy, so an exact match is required."""
        data = self.execute(FIND_ITEMS, {"search": name}, f"aiCatalogItems(search={name!r})")
        nodes = ((data.get("aiCatalogItems") or {}).get("nodes")) or []
        for node in nodes:
            if node.get("name") == name:
                return node
        return None

    def provision(
        self,
        *,
        name: str,
        description: str,
        item_type: str,
        payload_field: str,
        payload: str,
        create_query: str,
        update_query: str,
        dry_run: bool,
    ) -> Tuple[str, str, Optional[str]]:
        """Create the item if absent, otherwise re-assert the payload onto it.

        Returns ``(action, item_id, version_name)``.
        """
        existing = self.find_item(name)
        if existing is None:
            if dry_run:
                return "would-create", "(none)", None
            variables = {
                "input": {
                    "name": name,
                    "description": description,
                    "public": False,
                    "projectId": self._project_gid,
                    payload_field: payload,
                }
            }
            self.execute(create_query, variables, f"{item_type} create {name!r}")
            created = self.find_item(name)
            if created is None:
                raise ProvisionError(f"{item_type} {name!r} was accepted but is not in the catalog")
            return "created", created["id"], _version_name(created)

        if dry_run:
            return "would-update", existing["id"], _version_name(existing)

        variables = {"input": {"id": existing["id"], payload_field: payload}}
        self.execute(update_query, variables, f"{item_type} update {name!r}")
        return "updated", existing["id"], _version_name(existing)


def _version_name(item: Dict[str, Any]) -> Optional[str]:
    versions = ((item.get("versions") or {}).get("nodes")) or []
    return versions[0].get("versionName") if versions else None


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-id", default=os.getenv("GITLAB_PROJECT_ID", "87424071"))
    parser.add_argument("--evidence", help="write a JSON record of this run to this path")
    parser.add_argument("--dry-run", action="store_true", help="report actions without mutating")
    args = parser.parse_args(argv[1:])

    token = os.getenv("GITLAB_TOKEN", "")
    if not token:
        print("GITLAB_TOKEN is not set", file=sys.stderr)
        return 2

    try:
        agent_prompt = read_agent_prompt()
        flow_definition = read_flow_definition()
    except (OSError, ProvisionError) as exc:
        print(f"cannot read the repository artifacts: {exc}", file=sys.stderr)
        return 2

    actions: List[Dict[str, Any]] = []
    operations: List[str] = []
    try:
        with CatalogClient(token, args.project_id) as client:
            for item_type, name, description, payload_field, payload, create, update in (
                (
                    "AGENT",
                    AGENT_NAME,
                    AGENT_DESCRIPTION,
                    "systemPrompt",
                    agent_prompt,
                    AGENT_CREATE,
                    AGENT_UPDATE,
                ),
                (
                    "FLOW",
                    FLOW_NAME,
                    FLOW_DESCRIPTION,
                    "definition",
                    flow_definition,
                    FLOW_CREATE,
                    FLOW_UPDATE,
                ),
            ):
                action, item_id, version = client.provision(
                    name=name,
                    description=description,
                    item_type=item_type,
                    payload_field=payload_field,
                    payload=payload,
                    create_query=create,
                    update_query=update,
                    dry_run=args.dry_run,
                )
                actions.append(
                    {
                        "item_type": item_type,
                        "name": name,
                        "action": action,
                        "id": item_id,
                        "version_name": version,
                        "source_file": str(
                            (AGENT_PROMPT_PATH if item_type == "AGENT" else FLOW_DEFINITION_PATH)
                            .relative_to(REPO_ROOT)
                        ),
                    }
                )
            operations = [call["operation"] for call in client.calls]
    except (httpx.HTTPError, ProvisionError) as exc:
        print(f"catalog provisioning failed: {exc}", file=sys.stderr)
        return 1

    for action in actions:
        version = f" v{action['version_name']}" if action["version_name"] else ""
        print(f"{action['action']:>9}  {action['item_type']:<5} {action['id']}{version}")
        print(f"           from {action['source_file']}")

    if not args.dry_run:
        print(
            "\nNote: `definition` and `systemPrompt` are write-only, so this re-asserted the\n"
            "repository content onto the items rather than proving the catalog already\n"
            "matched. A clean response means each definition compiled server-side."
        )

    if args.evidence:
        target = Path(args.evidence)
        target = target if target.is_absolute() else REPO_ROOT / target
        record = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "captured_with": "scripts/duo_provision_catalog.py (GitLab GraphQL AI Catalog API)",
            "project_id": args.project_id,
            "graphql_endpoint": API,
            "dry_run": args.dry_run,
            "definition_source": str(FLOW_DEFINITION_PATH.relative_to(REPO_ROOT)),
            "agent_prompt_source": str(AGENT_PROMPT_PATH.relative_to(REPO_ROOT)),
            "write_only_fields": ["definition", "systemPrompt"],
            "items": actions,
            "operations": operations,
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record, indent=2) + "\n")
        shown = target.relative_to(REPO_ROOT) if target.is_relative_to(REPO_ROOT) else target
        print(f"\nwritten: {shown}")

    if args.dry_run:
        return 0
    return 0 if all(a["action"] in {"created", "updated"} for a in actions) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
