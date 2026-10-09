# RollbackIQ — Detect. Decide. Recover.

**RollbackIQ is a GitLab-native agentic production recovery engineer.** It detects a
deployment regression, gathers evidence, proposes a safe response, requires explicit
human approval before any consequential action, drives a controlled rollback through
GitLab CI/CD, and then **independently verifies that the service actually recovered**.

> **The defining principle: a successful rollback job is not proof of recovery.**
> Observed recovery against a healthy baseline is proof.

Built for the **GitLab Transcend Hackathon (Path A: Start Fresh)**.

## Status — what is implemented today

This repository is honest about its progress. Nothing below claims GitLab execution that
has not happened.

| Area | Status | Evidence |
| --- | --- | --- |
| Healthy/faulty demo workload with real HTTP metrics | **Implemented and verified** | `demo/service/app.py`, `evidence/phase1-regression.json` |
| Deterministic regression detection (thresholds, sustained windows, cooldown) | **Implemented and verified** | `backend/app/services/detector.py`, `backend/tests/test_detector.py` |
| Incident state machine with illegal transitions rejected | **Implemented and verified** | `backend/app/models/incident.py` |
| Safety gate (approval scope/expiry/actor, environment allowlist, known-good target, migration veto, idempotency) | **Implemented and verified** | `backend/app/services/safety.py`, `backend/tests/test_safety.py` |
| Independent post-rollback verification | **Implemented and verified** | `backend/app/services/verifier.py` |
| Docker image and Compose stack for both releases | **Implemented and verified** | `docker-compose.yml`, `demo/service/Dockerfile` |
| Attribution guard (no AI attribution footers) in hooks and CI | **Implemented and verified locally** | `scripts/check_no_attribution.sh`, `.gitlab-ci.yml` |
| OpenTelemetry export to GitLab Observability | **Implemented and verified against the real collector** (64 spans accepted, 0 failures) | `demo/service/otel_setup.py`, `evidence/otel-export-spike.json` |
| GitLab CI/CD deploy and rollback jobs | **Not yet implemented** | plan in `ROLLBACKIQ_BUILD.md` |
| GitLab Duo agent/flow investigation | **Not yet implemented** | Duo flows confirmed enabled on the project; no flow executed yet |
| Control-plane API, persistence and dashboard | **Not yet implemented** | — |

Test suite: **51 passing** (`pytest`).

## Measured end-to-end run

From `scripts/demo_regression.py` (raw record: `evidence/phase1-regression.json`), reproduced
twice with the same class of result on a local machine:

| Phase | Measurement |
| --- | --- |
| Healthy `v1` baseline | 150 real requests, 0 errors, p95 **35.6 ms** |
| Faulty `v2` | 11.3% then 8.7% error rate; p95 **238.9 ms = 6.72x** baseline |
| Detection | breached `P95_LATENCY` and `ERROR_RATE` on the second sustained window, after **7.72 s** |
| Rollback | 0.51 s — *a local process restart standing in for the GitLab CI job, which is not implemented yet* |
| Post-rollback window | 400 requests over ~5 s, 0 errors, p95 **28.0 ms = 0.79x** baseline |
| Verification | `recovered=True`, `independent=True` |
| Totals | time to verify 5.22 s; detection-to-verified-recovery 5.43 s; total **13.16 s** |

## Quick start

```bash
# 1. Python environment
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

# 2. Tests
.venv/bin/python -m pytest            # 51 passing

# 3. The full regression demonstration (healthy -> faulty -> detected -> rolled back -> verified)
.venv/bin/python scripts/demo_regression.py

# 4. The workload on its own
docker compose up -d workload-v1      # healthy release
curl -s localhost:8000/release
curl -s localhost:8000/metrics

# faulty release (same image, different deployment inputs)
RELEASE_VERSION=v2 FAULT_LATENCY_MS=180 FAULT_ERROR_RATE=0.10 \
  docker compose --profile faulty up -d workload-v2
```

## How it works

```
deployment (GitLab CI/CD)            real user traffic
        |                                    |
        v                                    v
  demo workload  -------------------->  HTTP probes (observer)      <-- measurement comes from the
  /metrics, /release                    backend/app/services/collector.py    observer, not the service
        |                                    |
        |                                    v
        |                            regression detector  (thresholds, sustained windows, cooldown)
        |                                    |
        |                                    v
        |                         incident state machine  (HEALTHY -> ... -> RECOVERED / ESCALATED)
        |                                    |
        |                                    v
        |                       GitLab Duo investigation  (planned: evidence + hypotheses)
        |                                    |
        |                                    v
        |                            recovery proposal + risk
        |                                    |
        |                                    v
        |                            SAFETY GATE (human approval, allowlist, known-good target,
        |                                    |         migration veto, idempotency)
        |                                    v
        |                          GitLab CI/CD rollback job  (planned)
        |                                    |
        v                                    v
     previous release  <--------  independent verifier  (new post-rollback observations only)
                                             |
                                             v
                                  incident record + audit trail
```

Design rules that make this trustworthy:

- **Detection is arithmetic, not an opinion.** Thresholds, minimum sample counts, sustained
  windows and cooldowns are deterministic; the numbers come from real requests.
- **Thin evidence never triggers.** No verified baseline, too few samples, or an environment
  mismatch suppresses detection instead of guessing.
- **The safety gate reports every veto**, not just the first one, and refuses when migration
  compatibility is unknown rather than assuming it is safe.
- **Verification refuses to reuse the incident data.** An unknown rollback execution time means
  independence cannot be claimed, so recovery is not confirmed.
- **Measurement is independent.** The observer's own probe latencies are used, not the
  service's self-report.

## Repository layout

```
backend/app/models/       incident state machine, metric windows, releases, approvals
backend/app/services/     detector, safety gate, verifier, collector, stats
backend/tests/            unit, negative and integration tests (51)
demo/service/             the deployed workload (v1 healthy, v2 faulty) + Dockerfile
scripts/                  demo regression runner, attribution guard, Git hooks
evidence/                 raw measured records from real runs
docs/PROGRESS.md          session checkpoint and current blockers
```

## Safety model

- Human approval is mandatory before a rollback; approvals are scoped to one exact proposal
  hash, so approving one action never authorizes a different one.
- Non-human actors (`system`, `agent`, and similar) cannot approve.
- Rollback targets must be releases this system observed as healthy. Unknown target, target
  equal to the current release, environment mismatch, unsafe/unknown migration and duplicate
  idempotency keys all refuse.
- **Code rollback does not restore deleted data.** Data restoration is deliberately out of
  scope and remains a separate, human-controlled operation.
- Retrieved telemetry, commit messages and issue text are treated as untrusted evidence, never
  as instructions.

See `AGENTS.md` and `ROLLBACKIQ_BUILD.md` for the full product and safety specification.

## Observability

The demo workload exports real OpenTelemetry traces to the collector configured through
`OTEL_EXPORTER_OTLP_ENDPOINT`, with the resource attributes GitLab documents so a trace
links back to the project and the exact deployed commit (`gitlab.project.id`,
`gitlab.project.name`, `service.version`, `deployment.environment.name`).

Telemetry is opt-in and can never break the workload: with no collector configured the
service runs exactly as before, and its own `/otel` endpoint reports what the telemetry
layer actually did — including a counter wrapped around the real exporter, so spans are
only reported as sent once the collector accepted the batch. `demo/otel.env.example`
shows the configuration (no credentials in the repository).

`scripts/otel_export_evidence.py` proves the path end to end: it starts the workload as
deployed, sends genuine requests, flushes, and exits non-zero unless spans were accepted
with zero failures. It is also a manual CI job (`telemetry-spike`) so the export can be
re-proven on a GitLab runner.

## Hackathon workspace

This repository lives in the provided Transcend Hackathon workspace project for `@yablokolabs`
(DevPost: `yablokolabs`), which also hosts the [onboarding issue](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43178176/showcase/-/work_items/1).
The workspace starter `README.md` that this file replaces remains in history at commit
`a4d8a7ad`, and the workspace starter commit is kept as the first parent of the merge that
brought this project into the repository.

## Licence

MIT — see `LICENSE`.
