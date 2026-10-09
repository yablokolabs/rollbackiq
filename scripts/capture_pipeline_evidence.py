#!/usr/bin/env python3
"""Capture GitLab pipeline evidence for the incident/evaluation record.

Pulls pipeline, job and log data straight from the GitLab API and writes it to
``evidence/`` so that every claim about CI execution in the documentation is
backed by a captured artifact rather than by memory.

The token is read from the environment (``GITLAB_TOKEN``) and is never written
to the output file.

    GITLAB_TOKEN=... .venv/bin/python scripts/capture_pipeline_evidence.py <project_id> [pipeline_id]
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import httpx

API = "https://gitlab.com/api/v4"
REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = REPO_ROOT / "evidence"
#: Log lines that matter as proof the guard really executed.
INTERESTING = ("attribution guard:", "[skip]", "(scanned", "Job succeeded", "Job failed")


def fetch(client: httpx.Client, path: str) -> Any:
    response = client.get(f"{API}{path}")
    response.raise_for_status()
    return response.json()


def main(argv: List[str]) -> int:
    token = os.getenv("GITLAB_TOKEN", "")
    if not token:
        print("GITLAB_TOKEN is not set", file=sys.stderr)
        return 2
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    project_id = argv[1]
    pipeline_id = argv[2] if len(argv) > 2 else None

    with httpx.Client(headers={"PRIVATE-TOKEN": token}, timeout=30.0) as client:
        project = fetch(client, f"/projects/{project_id}")
        if pipeline_id is None:
            pipelines = fetch(client, f"/projects/{project_id}/pipelines?per_page=1")
            if not pipelines:
                print("no pipelines found", file=sys.stderr)
                return 1
            pipeline_id = str(pipelines[0]["id"])

        pipeline = fetch(client, f"/projects/{project_id}/pipelines/{pipeline_id}")
        jobs = fetch(client, f"/projects/{project_id}/pipelines/{pipeline_id}/jobs?per_page=50")

        job_records: List[Dict[str, Any]] = []
        for job in jobs:
            trace = client.get(f"{API}/projects/{project_id}/jobs/{job['id']}/trace")
            trace.raise_for_status()
            lines = [
                line
                for line in trace.text.splitlines()
                if any(marker in line for marker in INTERESTING)
            ]
            job_records.append(
                {
                    "id": job["id"],
                    "name": job["name"],
                    "stage": job["stage"],
                    "status": job["status"],
                    "duration_seconds": job.get("duration"),
                    "web_url": job.get("web_url"),
                    "runner": (job.get("runner") or {}).get("description"),
                    "guard_output": lines,
                }
            )

    evidence = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "captured_with": "scripts/capture_pipeline_evidence.py (GitLab REST API)",
        "project": {
            "id": project["id"],
            "path_with_namespace": project["path_with_namespace"],
            "web_url": project["web_url"],
            "visibility": project.get("visibility"),
            "duo_foundational_flows_enabled": project.get("duo_foundational_flows_enabled"),
            "duo_remote_flows_enabled": project.get("duo_remote_flows_enabled"),
        },
        "pipeline": {
            "id": pipeline["id"],
            "status": pipeline["status"],
            "ref": pipeline["ref"],
            "sha": pipeline["sha"],
            "source": pipeline.get("source"),
            "created_at": pipeline.get("created_at"),
            "updated_at": pipeline.get("updated_at"),
            "web_url": pipeline.get("web_url"),
        },
        "jobs": job_records,
    }

    EVIDENCE_DIR.mkdir(exist_ok=True)
    out = EVIDENCE_DIR / f"gitlab-pipeline-{pipeline['id']}.json"
    out.write_text(json.dumps(evidence, indent=2) + "\n")

    print(f"pipeline {pipeline['id']} status={pipeline['status']} sha={pipeline['sha'][:8]}")
    for job in job_records:
        print(f"  job {job['id']} {job['name']} status={job['status']} {job['duration_seconds']}s")
    print(f"written: {out.relative_to(REPO_ROOT)}")
    return 0 if pipeline["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
