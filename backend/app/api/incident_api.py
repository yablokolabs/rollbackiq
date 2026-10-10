"""Read-only incident API over the committed evidence artifacts.

The dashboard and the demo both need one honest answer to "what happened".
This service reads the artifacts that the pipeline and the Duo flow actually
wrote — ``evidence/gitlab-ci-lifecycle-artifacts/``, the pipeline capture and the
flow-trigger session record — and serves them as typed JSON.

It deliberately does not invent anything that is not in an artifact. When a file
is missing, the incident document names it in ``missing_artifacts`` rather than
filling the gap, and the fixed disclaimers (the fault is injected deployment
configuration; a code rollback does not restore deleted data) travel with every
response so no consumer can present the incident as something it was not.

Run it:

    .venv/bin/uvicorn app.api.incident_api:app --app-dir backend --port 8000

    GET /healthz
    GET /api/incidents
    GET /api/incidents/{incident_id}
    GET /            -> the built dashboard, when dashboard/dist exists

The API reads local files only; it needs no GitLab token.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = REPO_ROOT / "evidence"
LIFECYCLE_DIR = EVIDENCE_DIR / "gitlab-ci-lifecycle-artifacts"
DASHBOARD_DIST = REPO_ROOT / "dashboard" / "dist"

PROJECT_PATH = "gitlab-ai-hackathon/transcend-october-2026/43178176/showcase"
PROJECT_URL = f"https://gitlab.com/{PROJECT_PATH}"

#: Fixed, evidence-backed statements that must travel with the incident.
FAULT_NATURE = (
    "Injected deployment configuration on one image: v1 and v2 share the same "
    "image digest, and only the fault inputs differ. This is not a binary-level "
    "code regression."
)
CODE_ROLLBACK_NOTE = (
    "A code rollback does not restore deleted data. Data recovery is a separate, "
    "human-controlled operation on backups which this system deliberately does not perform."
)


class MetricWindow(BaseModel):
    release: Optional[str] = None
    environment: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    request_count: Optional[int] = None
    error_count: Optional[int] = None
    error_rate: Optional[float] = None
    availability: Optional[float] = None
    p50_ms: Optional[float] = None
    p95_ms: Optional[float] = None
    p99_ms: Optional[float] = None
    mean_ms: Optional[float] = None
    max_ms: Optional[float] = None
    source: Optional[str] = None


class Detection(BaseModel):
    triggered: bool
    incident_id: Optional[str] = None
    breaches: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    confidence_note: Optional[str] = None
    p95_ratio: Optional[float] = None
    windows: List[MetricWindow] = Field(default_factory=list)
    proposal_hash: Optional[str] = None


class SafetyCheck(BaseModel):
    code: str
    passed: bool
    detail: str


class SafetyDecision(BaseModel):
    allowed: bool
    stage: Optional[str] = None
    detail: Optional[str] = None
    veto_codes: List[str] = Field(default_factory=list)
    checks: List[SafetyCheck] = Field(default_factory=list)
    proposal_hash: Optional[str] = None


class Approval(BaseModel):
    id: Optional[str] = None
    incident_id: Optional[str] = None
    proposal_hash: Optional[str] = None
    actor: Optional[str] = None
    decision: Optional[str] = None
    environment: Optional[str] = None
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    scope_note: Optional[str] = None


class DeployRecord(BaseModel):
    release: Optional[str] = None
    environment: Optional[str] = None
    image_digest: Optional[str] = None
    commit_sha: Optional[str] = None
    pipeline_id: Optional[str] = None
    fault_latency_ms: Optional[str] = None
    fault_error_rate: Optional[str] = None
    deployed_at: Optional[str] = None


class VerificationResult(BaseModel):
    recovered: Optional[bool] = None
    reasons: List[str] = Field(default_factory=list)
    samples: Optional[int] = None
    window_seconds: Optional[float] = None
    p95_ms: Optional[float] = None
    baseline_p95_ms: Optional[float] = None
    p95_ratio_vs_baseline: Optional[float] = None
    error_rate: Optional[float] = None
    independent: Optional[bool] = None
    expected_release: Optional[str] = None
    observed_release: Optional[str] = None
    verified_at: Optional[str] = None
    after: Optional[MetricWindow] = None


class TimelineEvent(BaseModel):
    at: str
    kind: str
    title: str
    detail: Optional[str] = None
    link: Optional[str] = None


class EvidenceLink(BaseModel):
    label: str
    target: str
    kind: str


class PipelineJob(BaseModel):
    name: str
    stage: Optional[str] = None
    status: Optional[str] = None
    duration_seconds: Optional[float] = None
    web_url: Optional[str] = None


class Pipeline(BaseModel):
    id: Optional[str] = None
    status: Optional[str] = None
    ref: Optional[str] = None
    sha: Optional[str] = None
    web_url: Optional[str] = None
    jobs: List[PipelineJob] = Field(default_factory=list)


class DuoSession(BaseModel):
    session_id: Optional[str] = None
    url: Optional[str] = None
    status: Optional[str] = None
    human_status: Optional[str] = None
    agent_name: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    trigger_surface: Optional[str] = None
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    report_note_id: Optional[str] = None
    report_excerpt: Optional[str] = None
    errors: List[Any] = Field(default_factory=list)


class IncidentSummary(BaseModel):
    id: str
    environment: str
    status: str
    detected_at: Optional[str] = None
    target_release: Optional[str] = None
    recovered: Optional[bool] = None
    independent: Optional[bool] = None
    p95_ratio: Optional[float] = None
    duo_session_status: Optional[str] = None


class Incident(BaseModel):
    id: str
    environment: str
    status: str
    detected_at: Optional[str] = None
    fault_nature: str = FAULT_NATURE
    code_rollback_note: str = CODE_ROLLBACK_NOTE
    baseline: Optional[MetricWindow] = None
    detection: Optional[Detection] = None
    current_release: Optional[DeployRecord] = None
    target_release: Optional[DeployRecord] = None
    safety: Optional[SafetyDecision] = None
    approval: Optional[Approval] = None
    rollback_executed_at: Optional[str] = None
    idempotency_key: Optional[str] = None
    resolved_image_digest: Optional[str] = None
    verification: Optional[VerificationResult] = None
    pipeline: Optional[Pipeline] = None
    duo: Optional[DuoSession] = None
    timeline: List[TimelineEvent] = Field(default_factory=list)
    evidence: List[EvidenceLink] = Field(default_factory=list)
    missing_artifacts: List[str] = Field(default_factory=list)


def _read(path: Path, missing: List[str]) -> Optional[Dict[str, Any]]:
    if not path.exists():
        missing.append(str(path.relative_to(REPO_ROOT)))
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        missing.append(f"{path.relative_to(REPO_ROOT)} (unparseable)")
        return None


def _pipeline_url(pipeline_id: str) -> str:
    return f"{PROJECT_URL}/-/pipelines/{pipeline_id}"


def _build_timeline(
    baseline: Optional[MetricWindow],
    deploys: List[DeployRecord],
    detection: Optional[Detection],
    approval: Optional[Approval],
    executed_at: Optional[str],
    verification: Optional[VerificationResult],
    duo: Optional[DuoSession],
) -> List[TimelineEvent]:
    events: List[TimelineEvent] = []

    for deploy in deploys:
        if deploy.deployed_at:
            faults = (
                f"fault latency {deploy.fault_latency_ms} ms, error rate {deploy.fault_error_rate}"
                if deploy.fault_latency_ms not in (None, "0")
                else "no fault inputs"
            )
            events.append(
                TimelineEvent(
                    at=deploy.deployed_at,
                    kind="deploy",
                    title=f"{deploy.release} deployed to {deploy.environment}",
                    detail=f"{faults}; image digest {deploy.image_digest}",
                )
            )

    if baseline and baseline.started_at:
        events.append(
            TimelineEvent(
                at=baseline.started_at,
                kind="baseline",
                title="Healthy baseline window captured",
                detail=(
                    f"{baseline.request_count} requests, {baseline.error_count} errors, "
                    f"p95 {baseline.p95_ms:.1f} ms"
                    if baseline.p95_ms is not None
                    else None
                ),
            )
        )

    if detection:
        for window in detection.windows:
            if window.started_at:
                events.append(
                    TimelineEvent(
                        at=window.started_at,
                        kind="window",
                        title=f"Measurement window on {window.release}",
                        detail=(
                            f"{window.request_count} requests, {window.error_count} errors, "
                            f"p95 {window.p95_ms:.1f} ms"
                            if window.p95_ms is not None
                            else None
                        ),
                    )
                )
        if detection.triggered:
            last = detection.windows[-1] if detection.windows else None
            events.append(
                TimelineEvent(
                    at=(last.ended_at if last and last.ended_at else ""),
                    kind="detection",
                    title="Regression detected — thresholds breached",
                    detail="; ".join(detection.reasons) or None,
                )
            )

    if approval and approval.created_at:
        events.append(
            TimelineEvent(
                at=approval.created_at,
                kind="approval",
                title=f"Human approval {approval.decision or 'recorded'} by {approval.actor}",
                detail=(
                    f"scoped to proposal {approval.proposal_hash}, expires {approval.expires_at}; "
                    f"{approval.scope_note or ''}".strip()
                ),
            )
        )

    if executed_at:
        events.append(
            TimelineEvent(
                at=executed_at,
                kind="rollback",
                title="Safety-gated rollback executed",
                detail="target release v1; see the safety gate checks in this incident",
            )
        )

    if verification and verification.after and verification.after.started_at:
        events.append(
            TimelineEvent(
                at=verification.after.started_at,
                kind="verification",
                title="Independent verification window started",
                detail=(
                    f"{verification.samples} samples over {verification.window_seconds:.2f} s "
                    "after the rollback; not the data that triggered recovery"
                    if verification.window_seconds is not None
                    else None
                ),
            )
        )
    if verification and verification.verified_at:
        verdict = "recovered" if verification.recovered else "NOT recovered"
        events.append(
            TimelineEvent(
                at=verification.verified_at,
                kind="verdict",
                title=f"Verification verdict: {verdict}",
                detail=(
                    f"p95 {verification.p95_ratio_vs_baseline:.3f}x baseline, "
                    f"error rate {verification.error_rate}"
                    if verification.p95_ratio_vs_baseline is not None
                    else None
                ),
            )
        )

    if duo and duo.created_at:
        events.append(
            TimelineEvent(
                at=duo.created_at,
                kind="duo",
                title=f"Duo flow session started ({duo.agent_name})",
                detail=(
                    f"trigger: {duo.trigger_surface}; status {duo.status}"
                    if duo.trigger_surface
                    else None
                ),
                link=duo.url,
            )
        )
    if duo and duo.report_note_id:
        events.append(
            TimelineEvent(
                at=duo.updated_at or duo.created_at or "",
                kind="duo-report",
                title="Duo flow posted its investigation to the incident issue",
                detail=duo.report_excerpt,
                link=f"{PROJECT_URL}/-/issues/2#note_{duo.report_note_id}",
            )
        )

    return sorted((e for e in events if e.at), key=lambda e: e.at)


def _duo_session(missing: List[str]) -> Optional[DuoSession]:
    data = _read(EVIDENCE_DIR / "duo-flow-trigger-session.json", missing)
    if data is None:
        return None
    session = data.get("session") or {}
    session_id = (session.get("id") or "").rsplit("/", 1)[-1] or None
    events = data.get("events") or []
    messages: List[Dict[str, Any]] = []
    seen: set = set()
    for event in events:
        message = (event.get("last_message") or "").strip()
        if not message or message in seen:
            continue
        seen.add(message)
        messages.append(
            {
                "type": event.get("message_type"),
                "truncated": len(message) >= 2000,
                "text": message,
            }
        )
    note = next(
        (
            entry
            for entry in (data.get("issue_notes_after_run") or [])
            if entry.get("author") == data.get("service_account") and not entry.get("system")
        ),
        None,
    )
    return DuoSession(
        session_id=session_id,
        url=(
            f"{PROJECT_URL}/-/automate/agent-sessions/{session_id}" if session_id else None
        ),
        status=session.get("status"),
        human_status=session.get("humanStatus"),
        agent_name=session.get("agentName"),
        created_at=session.get("createdAt"),
        updated_at=session.get("updatedAt"),
        trigger_surface=data.get("trigger_surface"),
        messages=messages,
        report_note_id=str(note["id"]) if note else None,
        report_excerpt=note.get("body") if note else None,
        errors=[e.get("errors") for e in events if e.get("errors")] or [],
    )


def _pipeline(pipeline_id: Optional[str], missing: List[str]) -> Optional[Pipeline]:
    path = EVIDENCE_DIR / f"gitlab-pipeline-{pipeline_id}.json" if pipeline_id else None
    data = _read(path, missing) if path else None
    if data is None:
        return None
    raw_jobs = data.get("jobs") or []
    jobs = [
        PipelineJob(
            name=job.get("name") or "?",
            stage=job.get("stage"),
            status=job.get("status"),
            duration_seconds=job.get("duration_s") or job.get("duration_seconds"),
            web_url=job.get("web_url"),
        )
        for job in raw_jobs
    ]
    pipeline = data.get("pipeline") or {}
    return Pipeline(
        id=str(pipeline.get("id") or pipeline_id) if (pipeline.get("id") or pipeline_id) else None,
        status=pipeline.get("status"),
        ref=pipeline.get("ref"),
        sha=pipeline.get("sha"),
        web_url=pipeline.get("web_url") or (_pipeline_url(str(pipeline_id)) if pipeline_id else None),
        jobs=jobs,
    )


def load_incident() -> Incident:
    """Assemble the incident document from the committed artifacts."""
    missing: List[str] = []

    baseline_data = _read(LIFECYCLE_DIR / "baseline-window.json", missing)
    detection_data = _read(LIFECYCLE_DIR / "ci-detection.json", missing)
    decision_data = _read(LIFECYCLE_DIR / "rollback-execution.json", missing)
    approval_data = _read(LIFECYCLE_DIR / "approval.json", missing)
    verification_data = _read(LIFECYCLE_DIR / "verification.json", missing)
    healthy_data = _read(LIFECYCLE_DIR / "deploy-healthy.json", missing)
    regressed_data = _read(LIFECYCLE_DIR / "deploy-regressed.json", missing)
    bundle_data = _read(LIFECYCLE_DIR / "incident-bundle-approved.json", missing)

    if decision_data is None:
        raise HTTPException(status_code=503, detail="rollback-execution.json is not available")

    incident_id = decision_data.get("incident_id") or "unknown"
    environment = decision_data.get("environment") or "unknown"
    pipeline_id = (regressed_data or {}).get("pipeline_id")
    # The incident is created the moment the detector fires; the proposal carries that
    # timestamp, so it is the honest "detected at" rather than the later approval time.
    detected_at = ((bundle_data or {}).get("proposal") or {}).get("created_at")

    baseline = MetricWindow(**baseline_data) if baseline_data else None
    detection = (
        Detection(
            triggered=bool(detection_data.get("triggered")),
            incident_id=detection_data.get("incident_id"),
            breaches=detection_data.get("breaches") or [],
            reasons=detection_data.get("reasons") or [],
            confidence=detection_data.get("confidence"),
            confidence_note=detection_data.get("confidence_note"),
            p95_ratio=detection_data.get("p95_ratio"),
            windows=[MetricWindow(**w) for w in detection_data.get("windows") or []],
            proposal_hash=detection_data.get("proposal_hash"),
        )
        if detection_data
        else None
    )

    decision = decision_data.get("decision") or {}
    safety = SafetyDecision(
        allowed=bool(decision.get("allowed")),
        stage=decision.get("stage"),
        detail=decision.get("detail"),
        veto_codes=decision.get("veto_codes") or [],
        checks=[SafetyCheck(**check) for check in decision.get("checks") or []],
        proposal_hash=decision.get("proposal_hash"),
    )

    approval = Approval(**approval_data) if approval_data else None

    verification = None
    if verification_data:
        result = verification_data.get("result") or {}
        verification = VerificationResult(
            recovered=result.get("recovered"),
            reasons=result.get("reasons") or [],
            samples=result.get("samples"),
            window_seconds=result.get("window_seconds"),
            p95_ms=result.get("p95_ms"),
            baseline_p95_ms=result.get("baseline_p95_ms"),
            p95_ratio_vs_baseline=result.get("p95_ratio_vs_baseline"),
            error_rate=result.get("error_rate"),
            independent=result.get("independent"),
            expected_release=result.get("expected_release"),
            observed_release=result.get("observed_release"),
            verified_at=result.get("verified_at"),
            after=MetricWindow(**result["after"]) if result.get("after") else None,
        )

    deploys = [
        DeployRecord(**data)
        for data in (healthy_data, regressed_data)
        if data is not None
    ]
    duo = _duo_session(missing)
    pipeline = _pipeline(pipeline_id, missing)

    if verification and verification.recovered and verification.independent:
        status = "recovered"
    elif verification and verification.recovered is False:
        status = "escalated"
    else:
        status = "unverified"

    timeline = _build_timeline(
        baseline=baseline,
        deploys=deploys,
        detection=detection,
        approval=approval,
        executed_at=decision_data.get("executed_at"),
        verification=verification,
        duo=duo,
    )

    evidence = [
        EvidenceLink(label="Pipeline", target=_pipeline_url(str(pipeline_id)), kind="pipeline")
        if pipeline_id
        else EvidenceLink(label="Pipeline", target=PROJECT_URL, kind="pipeline"),
        EvidenceLink(label="Incident issue", target=f"{PROJECT_URL}/-/work_items/2", kind="issue"),
        EvidenceLink(
            label="Duo session",
            target=duo.url or f"{PROJECT_URL}/-/automate",
            kind="duo",
        ),
        EvidenceLink(
            label="CI lifecycle artifacts",
            target="evidence/gitlab-ci-lifecycle-artifacts/",
            kind="artifact",
        ),
        EvidenceLink(label="Pipeline capture", target=f"evidence/gitlab-pipeline-{pipeline_id}.json" if pipeline_id else "evidence/", kind="artifact"),
    ]

    return Incident(
        id=incident_id,
        environment=environment,
        status=status,
        detected_at=detected_at,
        baseline=baseline,
        detection=detection,
        current_release=DeployRecord(**regressed_data) if regressed_data else None,
        target_release=DeployRecord(**healthy_data) if healthy_data else None,
        safety=safety,
        approval=approval,
        rollback_executed_at=decision_data.get("executed_at"),
        idempotency_key=decision_data.get("idempotency_key"),
        resolved_image_digest=decision_data.get("resolved_image_digest"),
        verification=verification,
        pipeline=pipeline,
        duo=duo,
        timeline=timeline,
        evidence=evidence,
        missing_artifacts=missing,
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="RollbackIQ control plane (read-only evidence API)",
        description=__doc__,
        version="0.1.0",
    )

    @app.get("/healthz")
    def healthz() -> Dict[str, str]:
        return {
            "status": "ok",
            "time": datetime.now(timezone.utc).isoformat(),
            "serving": "committed evidence artifacts",
        }

    @app.get("/api/incidents", response_model=List[IncidentSummary])
    def list_incidents() -> List[IncidentSummary]:
        incident = load_incident()
        detection = incident.detection
        verification = incident.verification
        return [
            IncidentSummary(
                id=incident.id,
                environment=incident.environment,
                status=incident.status,
                detected_at=incident.detected_at,
                target_release=incident.target_release.release if incident.target_release else None,
                recovered=verification.recovered if verification else None,
                independent=verification.independent if verification else None,
                p95_ratio=detection.p95_ratio if detection else None,
                duo_session_status=incident.duo.status if incident.duo else None,
            )
        ]

    @app.get("/api/incidents/{incident_id}", response_model=Incident)
    def get_incident(incident_id: str) -> Incident:
        incident = load_incident()
        if incident_id != incident.id:
            raise HTTPException(status_code=404, detail=f"unknown incident {incident_id!r}")
        return incident

    if DASHBOARD_DIST.exists():
        app.mount("/", StaticFiles(directory=str(DASHBOARD_DIST), html=True), name="dashboard")

    return app


app = create_app()
