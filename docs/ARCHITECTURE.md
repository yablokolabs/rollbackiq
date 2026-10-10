# Architecture

RollbackIQ detects a deployment regression, gathers evidence, proposes a safe response,
requires an explicit human approval, drives a controlled rollback through GitLab CI/CD, and
then **independently verifies that the service recovered**.

> A successful rollback job is not proof of recovery. Observed recovery against a healthy
> baseline is proof.

The defining constraint is that **agent reasoning never changes deployment state**. Everything
that can alter a deployment lives behind a gate that checks a human approval, and the agent
has no tool that can reach it.

![System architecture](diagrams/architecture.png)

![Trust boundary layers: the enforcement stack](diagrams/trust-boundary-layers.png)

The sources are [`diagrams/architecture.html`](diagrams/architecture.html) and
[`diagrams/trust-boundary-layers.html`](diagrams/trust-boundary-layers.html).

## Components

| Component | Path | Responsibility |
| --- | --- | --- |
| Demo workload | `demo/service/app.py` | The deployed service. Serves real HTTP, exposes `/metrics`, `/release`, `/otel` and a rolling request window. v1 is healthy; v2 injects latency and error faults through **deployment inputs**, not a different build. |
| Observer collector | `backend/app/services/collector.py` | Measures the workload with its own probes. Measurement never comes from the service's self-report. |
| Regression detector | `backend/app/services/detector.py` | Deterministic thresholds, minimum sample counts, two sustained windows, a cooldown, and a refusal to fire on a baseline it did not verify. |
| Incident state machine | `backend/app/models/incident.py` | Nine states and the legal transitions between them. An illegal move raises; a denied or expired approval escalates. |
| Safety gate | `backend/app/services/safety.py` | Runs 18 checks over a proposal and an approval, reports **every** veto, and fails closed. |
| Independent verifier | `backend/app/services/verifier.py` | Certifies recovery only from a new post-rollback window, against a verified baseline, with a stabilization duration. |
| CI lifecycle scripts | `scripts/ci_release.py`, `ci_incident.py`, `ci_rollback.py`, `ci_probe.py` | Deploy, measure, detect, approve, gate and verify. They run unchanged on a laptop and in a job. |
| Read-only API | `backend/app/api/incident_api.py` | Serves typed JSON read from the pipeline's own artifacts, plus the built console. No write path. |
| Incident console | `dashboard/` | React + TypeScript + Tailwind: overview, timeline, investigation, approval centre, verification, report. |
| Duo custom agent + flow | `duo/` | The Recovery Investigator: investigates and proposes; it cannot deploy, approve or roll back. Provisioned from this repository into the AI Catalog. |
| Telemetry | `demo/service/otel_setup.py`, `backend/app/integrations/otel.py` | OTLP/HTTP spans for the workload and for detection/verification decisions, guarded so telemetry can never break or change a decision. |

## The two flows

### 1. The recovery lifecycle (GitLab CI/CD)

![Measured pipeline timeline](diagrams/pipeline-timeline.png)

![Incident state machine](diagrams/incident-state-machine.png)

```
push to main
   │
   ├─ attribution-guard            committed files and commit messages stay free of AI attribution
   ├─ test:pytest                  the suite that protects the gate
   ├─ build:workload-image         build, push, publish the immutable digest
   ├─ deploy:staging               deploy v1, health-gated, capture the healthy baseline window
   ├─ deploy:regressed   (manual)  deploy v2, measure, and require the REAL detector to fire
   ├─ approval:grant     (manual)  record an approval from GITLAB_USER_LOGIN, scoped to the proposal hash
   ├─ rollback:managed   (manual)  run the SafetyGate over the bundle, then deploy the target
   └─ verify:recovery              fresh deploy + a new window, then prove recovery or fail the pipeline
```

Two properties are deliberate:

- **`deploy:regressed` cannot manufacture an incident.** If the detector does not fire on the
  measured window, the job exits non-zero and writes no bundle.
- **`verify:recovery` is a separate job.** A job that reports its own success is not evidence.

### 2. The investigation (GitLab Duo)

![Duo flow sequence](diagrams/duo-flow-sequence.png)

An incident exists as an issue. Mentioning the custom flow's service account triggers a Duo
session; the flow reads the repository's committed evidence and posts its own report back to
the issue. Session `9288744` did exactly that and — notably — refused to accept the issue's
figures without artifacts, flagging mismatched ratios, hash and digest. Those mismatches were
real: they were a transcription error in this repository's own record, corrected afterwards.
The flow's audit is why it was caught.

## Constraints the design answers

| Constraint | Consequence |
| --- | --- |
| GitLab jobs run on separate ephemeral runners | A container does not survive between jobs. State travels as **artifacts**, and each job re-establishes its deployment. |
| Artifacts are the record | The API reads the artifacts rather than a second copy in a database. `ROLLBACKIQ_BUILD.md` §9 allows a simpler proven design, and a duplicate store could only drift from what the pipeline wrote. |
| One image, two releases | v1 and v2 share an image digest; the fault is injected deployment configuration. That is what lets "roll back" be a change of inputs rather than a rebuild — and it is why the digest identity check proves *artifact* identity, not a different binary. |
| A rollback must be repeatable to demo, but never twice by accident | An idempotency ledger artifact makes a replay inside a pipeline refuse. It is **not** a distributed lock, and it is documented as such. |
| Duo must be genuinely used | A custom agent and custom flow are provisioned from `duo/` by `scripts/duo_provision_catalog.py`, and the flow executes through the project's flow trigger. |

## Known limitations (stated, not hidden)

- **The headless Duo CLI cannot select a custom flow.** It negotiates the advertised
  `developer` flow; with `--workflow-type` it *does* transmit the custom definition, and the
  service then declines to instantiate it. The working path is the project's flow trigger.
  Evidence and the source lines behind this are in `docs/PROGRESS.md`.
- **CI networking assumptions were proven on a runner**, not merely locally, but only on the
  GitLab.com shared runner (`docker:27-dind`). Nothing is claimed about other executors.
- **The Duo flow is not in the execution path of the console or the gate.** It investigates and
  reports. The lifecycle runs without it, by design.
- **The ledger is not a distributed lock**, and the deployment target is an isolated
  `demo-staging` demo, never customer infrastructure.
