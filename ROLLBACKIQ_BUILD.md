# ROLLBACKIQ_BUILD.md — Product and Engineering Specification

> **RollbackIQ — Detect. Decide. Recover.**  
> GitLab Transcend Hackathon | **Path A: Start Fresh**  
> Status: product specification; no implementation claims until verified.

## 1. Product thesis

RollbackIQ is a **GitLab-native agentic production recovery engineer** that detects a release regression, correlates telemetry with GitLab deployment context, recommends a safe recovery action, requests explicit human approval for consequential remediation, executes a controlled GitLab CI/CD rollback, and **verifies** that service health is restored.

**Differentiator:** A successful rollback job is not success; observed recovery against a healthy baseline is success.

### Origin story

A production bug once deleted customer data, requiring backup recovery and a costly multi-person war room. The product is inspired by the need to reduce time spent correlating evidence and coordinating recovery. **A code rollback cannot recover already-deleted data**; this product's MVP deliberately focuses on deployment regressions, while data restoration remains a separate future human-controlled workflow.

## 2. Competition strategy and guardrails

**Entry:** Path A: Start Fresh. Build a new independent GitLab project; do not repurpose SightOps.

**Primary target:** Best Supervised Agent. **Secondary:** Most Stages Covered (Path A) and, if deserved, Most Creative. Hands-off autonomy is not the default for risky recovery. Never claim eligibility or prizes before official confirmation.

Judging dimensions (user-provided): technological implementation, design, potential impact, innovation, presentation — equally weighted. Genuine GitLab AI use is a pass/fail prerequisite.

Verify current official submission rules before publishing: https://gitlab-transcend.devpost.com/rules. User reports public GitLab repo with MIT license and under-three-minute video; confirm those constraints at submission time. Optional Google Cloud deployment bonus must not trigger paid provisioning.

**DevSecOps stages to genuinely touch:** plan/issue, code/commit context, build, test, secure, release, deploy, operate/observe, monitor, incident response and retrospective. Stage coverage must be evidenced by actual workflows, not diagram labels.

## 3. User personas and jobs

- **On-call SRE:** Understand the incident and execute a safe, approved recovery.
- **Release engineer:** Correlate deployment changes with application health.
- **Engineering manager:** See recovery evidence, time-to-detect, time-to-recover, and audit trail.
- **Hackathon judge:** Understand and watch the end-to-end automation in under three minutes.

## 4. MVP success scenario

1. Healthy version `v1` deploys via GitLab CI/CD.
2. Observability establishes a healthy baseline from real requests.
3. Deliberately faulty `v2` deploys; latency or error rate deteriorates.
4. Monitoring detects a statistically meaningful regression under configured thresholds.
5. A **real GitLab Duo custom agent/flow** gathers pipeline, commit, deployment, and telemetry evidence.
6. Agent proposes rollback to last known-good `v1`, with confidence and contraindications.
7. Human reviews and approves; denial or timeout results in no action.
8. GitLab CI/CD executes an idempotent, authorized rollback.
9. Independent verifier measures application health and compares it with baseline.
10. GitLab issue/incident report records all evidence and outcomes.
11. Dashboard displays incident lifecycle, reasoning, approval, and verification.

A deterministic seeded regression makes the demo repeatable; do not present generated metrics as real observations.

## 5. Non-goals

- Autonomous destructive database operations.
- Restoring deleted data by code rollback.
- Direct access to customer production systems.
- Unrestricted agent execution of shell commands.
- Pretending a mocked LLM/API is a GitLab Duo agent.
- Paid AWS/GCP services without explicit authorization.

## 6. Mandatory capability spike — do this FIRST

Before writing a complex orchestration engine:
1. Authenticate GitLab CLI and verify `glab --version`, `glab auth status` without exposing tokens.
2. Inspect the provisioned hackathon GitLab namespace, project permissions, and CI/CD availability.
3. Check Duo CLI availability and current documented invocation.
4. Inspect GitLab MCP server availability and actual tool list/scopes.
5. Create and execute the smallest supported **Duo custom agent/flow**.
6. Confirm supported event triggers, external tool access, approval integration, and artifact visibility.
7. Record links/screenshots/logs proving the execution.
8. Document unavailable features and adapt without misrepresenting GitLab AI use.

Documentation:
- https://docs.gitlab.com/user/gitlab_duo_cli/
- https://docs.gitlab.com/user/model_context_protocol/mcp_server/
- https://docs.gitlab.com/user/get_started/get_started_agent_platform/

**Gate:** Do not proceed to full architecture until at least one real Duo agent/flow has run or a clearly documented access blocker has been escalated.

## 7. Reference architecture

```text
GitLab merge/pipeline/deployment event
          |
          v
    GitLab CI/CD deployment --------> FastAPI demo service
          |                                 |
          |                          OpenTelemetry / metrics
          |                                 |
          +------> Regression detector <----+
                        |
                        v
                GitLab Duo Agent Flow
              /         |           \
       Context       Investigation   Recovery plan
       collector     evidence        + risk analysis
              \         |           /
                        v
                 Approval request
                        |
                  approved only
                        |
                        v
                 GitLab rollback job
                        |
                        v
                Independent verifier
                        |
              +---------+----------+
              |                    |
          recovered           not recovered
              |                    |
       close with proof       escalate / keep open
              \                    /
                       v
             GitLab issue + audit
                       |
                       v
                 React dashboard
```

**Trust boundary:** Agent reasoning never directly changes deployment state. A narrowly scoped server-side controller verifies identity, state, approval, target, and idempotency before triggering an allowlisted CI job.

## 8. Agent and flow responsibilities

### 8.1 Release Guardian
Collect release metadata, pipeline status, test/security evidence, and known-good release ID. Output structured JSON and evidence links.

### 8.2 Canary Watcher
Compare actual service telemetry to baseline; flag threshold violations, sample count, observation window, and confidence. Deterministic detection logic; LLM does not invent metrics.

### 8.3 Incident Detective
Correlate error/latency shifts with deployment timestamps and GitLab commits/MRs. Identify competing hypotheses and missing evidence; never equate temporal proximity with proof.

### 8.4 Recovery Planner
Choose `rollback`, `hold`, or `escalate`; include risks, migration compatibility, target identity, and expected recovery conditions.

### 8.5 Safety Gate
Verify human approval for controlled recovery; enforce protected environment and allowlist. Deny if unsafe or ambiguous.

### 8.6 Recovery Verifier
Re-run real probes after action. Evaluate latency, error rate, availability, and stabilization window. Mark success only when thresholds are satisfied.

### 8.7 Incident Scribe
Create/update GitLab issue or incident artifact with timeline, raw evidence links, action, approval, and final status.

These are **logical roles**. Implement as actual GitLab Duo agents/flows only where supported. Fewer real agents are better than seven fake agents.

## 9. Data model

Use typed schemas and SQLite for local persistence unless a simpler proven design suffices.

- `Release`: id, commit SHA, pipeline ID, environment, deployed_at, artifact/image digest.
- `MetricWindow`: start/end, request count, p50/p95/p99 latency, error rate, availability, source.
- `Incident`: id, release_id, status, severity, detected_at, baseline_ref, evidence_refs.
- `Investigation`: hypotheses, supporting/contradicting evidence, confidence, missing data.
- `RecoveryProposal`: action, target_release, risk, checks, required_approver.
- `Approval`: actor, timestamp, decision, expiry, scoped proposal hash.
- `RemediationExecution`: job ID, idempotency key, started/finished, state, logs.
- `Verification`: windows, thresholds, raw metric refs, result, verified_at.
- `AuditEvent`: immutable append-only timestamp, actor, action, context, result.

All timestamps UTC; secrets never in records. Use explicit state machine and reject illegal transitions.

## 10. Incident state machine

```text
HEALTHY -> SUSPECTED -> INVESTIGATING -> PROPOSED
                                      |         |
                                   ESCALATED   v
                                          AWAITING_APPROVAL
                                            |        |
                                         denied   approved
                                            |        v
                                         ESCALATED EXECUTING
                                                      |
                                                      v
                                                  VERIFYING
                                                   /     \
                                             RECOVERED  ESCALATED
```

Handle duplicate events, race conditions, stale approvals, retry storms, and deployment changes during approval.

## 11. Detection and verification design

- Collect real HTTP probes from a reproducible workload.
- Baseline only after enough stable healthy samples.
- Example *configurable* trigger: p95 latency exceeds baseline by 3x across two observation windows, or error rate exceeds 5%; tune with evidence.
- Minimum sample count and cooldown; alert suppression for noisy small windows.
- Distinguish detection from investigation; report uncertainty.
- Verification must use **new independent post-rollback observations**, not the same data that triggered recovery.
- Track false positives, false negatives, detection delay, and recovery time in evaluation.
- No hardcoded successful metrics or fake before/after charts.

## 12. Remediation safety contract

**Mandatory** for every rollback:
- Approved actor and authorization scope.
- Exact project, protected environment, pipeline, and target image digest.
- Target is a previously verified known-good release.
- No unsafe/incompatible schema migration.
- Approval scoped to the exact proposal and not expired.
- Idempotency key and single-flight lock.
- Dry-run option, timeout, bounded retries.
- Full audit log and failure escalation.
- Independent post-action verification.

If any check fails, do not execute. Database backup restore is **not part of MVP**.

## 13. Backend and API

Suggested FastAPI modules:
```text
backend/app/
  main.py
  api/{health,incidents,approvals,releases,metrics}.py
  core/{config,auth,logging}.py
  models/{incident,release,approval,verification}.py
  services/{detector,gitlab_client,duo_bridge,planner,remediator,verifier,audit}.py
  integrations/{gitlab,otel}.py
```

Suggested endpoints (validate final design):
- `GET /healthz`, `GET /readyz`
- `GET /api/incidents`, `GET /api/incidents/{id}`
- `GET /api/releases`, `GET /api/metrics`
- `POST /api/incidents/{id}/approve`
- `POST /api/incidents/{id}/reject`
- `POST /api/webhooks/gitlab` (signature/token validation, replay protection)
- `GET /api/incidents/{id}/events` (SSE for live timeline)

Use structured responses, explicit error types, pagination, and authentication.

## 14. Frontend and UX

Build a credible operations console, not a generic chat window.

Main views:
1. **Overview:** current service status, latest release, active incident, live p95/error rate.
2. **Release timeline:** commits, pipelines, deployments, observed health shifts.
3. **Investigation:** hypotheses, evidence cards, confidence, missing signals.
4. **Approval center:** target release, expected outcome, risks, exact action, approve/reject.
5. **Recovery verification:** pre/post charts, stabilization window, verdict.
6. **Incident report:** human-readable timeline with links to GitLab evidence.

Responsive React + TypeScript + Tailwind; accessible contrast and keyboard navigation; meaningful loading/error states. Never show fake “live” metrics without labeling them demo fixtures.

## 15. GitLab CI/CD and isolated environment

- Pipeline stages as supported: lint, test, security checks, build, deploy, smoke, observe, rollback, verify, report.
- Use protected CI variables; do not expose credentials in job logs.
- Deploy `v1` healthy and `v2` faulty Docker images on the existing Azure VM or an isolated local runner.
- GitLab pipeline rollback job must be allowlisted and restricted; verify actual GitLab protected environment semantics.
- Preserve job IDs, commit SHA, artifacts, logs, and metrics snapshots for demo.
- Never run a rollback against an unrelated production environment.

## 16. Tests and evaluation

**Unit:** threshold math, baseline validation, state transitions, approval expiry, idempotency, migration veto, proposal validation.

**Integration:** GitLab webhook authentication, mocked GitLab API errors, retry policy, pipeline trigger, evidence persistence, metric ingestion.

**End-to-end:** real v1 healthy -> v2 regression -> Duo investigation -> approval -> rollback -> new metrics -> verified recovery -> GitLab issue.

**Negative cases:** missing approval, denied approval, expired approval, unknown rollback target, incompatible migration, GitLab outage, no metrics, rollback failure, recovery not restored, duplicate event, prompt injection in incident evidence.

**Report** real measurements from repeated runs: detection delay, investigation time, approval wait (separate), rollback execution time, verification time, total MTTR, success rate, false positives. Include hardware/environment and raw artifacts. No invented numbers.

## 17. Documentation and diagrams

Required:
- `README.md` with product story, real architecture, installation, safety, demo, and reproducibility.
- `AGENTS.md`, `ROLLBACKIQ_BUILD.md`, `docs/PROGRESS.md`.
- `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/EVALUATION.md`, `docs/DEMO.md`.
- `docs/COMPETITION_COMPLIANCE.md` mapping requirements to actual evidence.
- `docs/INCIDENT_RUNBOOK.md` and `.env.example`.
- MIT `LICENSE` and required third-party credits.

Render at least five diagrams, preferably SVG, with `diagram-design` if available: system architecture, Duo agent/flow sequence, incident state machine, approval trust boundary, and rollback verification pipeline. Verify commands from https://github.com/cathrynlavery/diagram-design.

## 18. Demo and submission

**Video:** aim for ~2:35–2:50, hard limit **under three minutes** if official rules confirm.

Suggested storyboard:
- 0:00–0:15: Origin problem, war room, promise.
- 0:15–0:35: Healthy v1, GitLab deployment, baseline.
- 0:35–0:55: Faulty v2, real latency/error regression.
- 0:55–1:25: GitLab Duo custom agent/flow actually investigating with evidence.
- 1:25–1:45: Risk summary and human approval.
- 1:45–2:10: Real GitLab rollback job.
- 2:10–2:35: New telemetry proves recovery; issue/report.
- 2:35–2:50: DevSecOps stages and clear takeaway.

Use real application captures, readable overlays, captions, and honest narration. VideoWright reference: https://github.com/scosman/videowright. Use ElevenLabs voice only if access is available and rights/terms permit; do not make it a dependency. Save final output to `demo/videos/rollbackiq-demo.mp4`.

Prepare Devpost description with the **actual** stack, GitLab repo, video URL, deployment URL if real, and measurable impact. Do not claim environmental/SCI impact without documented methodology and measured evidence.

## 19. Implementation phases and gates

**Phase 0 — Bootstrap:** repository, read rules, verify access, GitLab Duo custom flow proof, Hindsight `rollbackiq`, progress file. **Gate:** evidence of genuine Duo invocation.

**Phase 1 — Deterministic environment:** FastAPI v1/v2, Docker, metrics, baseline and fault injection. **Gate:** repeatable observed regression.

**Phase 2 — Detection and investigation:** threshold detector, GitLab context collection, actual Duo flow integration. **Gate:** real evidence-driven incident.

**Phase 3 — Approval and rollback:** policy checks, human approval, protected GitLab CI job, idempotency. **Gate:** unauthorized requests cannot roll back.

**Phase 4 — Recovery verification:** independent probes, metrics comparison, incident state transitions. **Gate:** failed recovery cannot be marked successful.

**Phase 5 — Product UI and reporting:** live dashboard, audit trail, GitLab issue. **Gate:** judge can follow the workflow end to end.

**Phase 6 — Reliability and security:** negative tests, concurrency, threat model, documentation. **Gate:** reproducible tests and no secret leakage.

**Phase 7 — Demo and submission:** rendered diagrams, VideoWright, public GitLab MIT repo, verified video duration, actual Devpost evidence. **Gate:** all claims supported.

## 20. Skills, tooling, and source links

Use installed skills if available: `adhd`, `full-send`, `senior-swe`, `ponytail`, `headroom`, `nori`, `novgraph`, `Serena MCP`, `Tavily`, `Hindsight`. **Their specific GitHub URLs are unverified in this specification.** Discover installed skill manifests and commands; never fabricate links or invocations.

Known user-provided GitHub references:
- https://github.com/cathrynlavery/diagram-design
- https://github.com/scosman/videowright

Official docs:
- https://docs.gitlab.com/user/gitlab_duo_cli/
- https://docs.gitlab.com/user/model_context_protocol/mcp_server/
- https://docs.gitlab.com/user/get_started/get_started_agent_platform/
- https://contributors.gitlab.com/transcend-hackathon
- https://gitlab-transcend.devpost.com/rules

## 21. Memory and continuity

Use Hindsight **`rollbackiq`** on port **8888** continuously: recall before major tasks, retain after milestones, verify writes, never store secrets. Keep `docs/PROGRESS.md` current every 15 minutes and after each meaningful change. At each new ~1-hour Freebuff session, re-read these documents, recall memory, inspect Git, and continue without repeating finished work.

## 22. Completion acceptance checklist

- [ ] Official Path A rules checked and recorded.
- [ ] Real GitLab Duo agent/flow execution proved.
- [ ] Real GitLab CI/CD deploy and rollback jobs.
- [ ] Reproducible healthy and regressed releases.
- [ ] Real metric-driven detection and evidence-based investigation.
- [ ] Approval gate, policy vetoes, idempotency, audit trail.
- [ ] Independent post-rollback verification.
- [ ] GitLab incident issue with actual evidence.
- [ ] Polished UI and rendered architecture diagrams.
- [ ] Unit/integration/E2E/negative tests and reproducible evaluation.
- [ ] No leaked credentials or fabricated benchmarks.
- [ ] No AI attribution footers in commits or generated content.
- [ ] Hindsight `rollbackiq` and progress checkpoints functioning.
- [ ] Public MIT GitLab repo and compliant short demo video, if required.
- [ ] Final Devpost claims correspond to demonstrated implementation.

**Build for credible, safe, verifiable recovery. FULL SEND.**