# Evaluation

Every number here was measured on this project's own demo workload. Where a claim is weaker
than it looks, the weakness is written next to it.

## 1. Test suite

| Command | Where | Result |
| --- | --- | --- |
| `.venv/bin/python -m pytest` | this host | **108 passed** |
| `pip install -r backend/requirements.txt; pip install -r demo/service/requirements.txt; python -m pytest` | `python:3.12-slim` in Docker, i.e. `test:pytest`'s exact commands | **98 passed** in 39 s |

Coverage of the parts that decide:

| Area | What it asserts |
| --- | --- |
| State machine | Happy path, illegal transitions rejected, denial escalates instead of executing, history and actor recorded |
| Detector | Empty and insufficient windows, unverified or missing baseline, environment mismatch, the two-window rule, cooldown suppression, counter reset, error-rate-only breach |
| Safety gate | One authorized rollback allowed; 15 veto cases, each required to name its own guard; regression tests for the pass-path wording |
| Verifier | Independent window required, unknown rollback time refused, reused incident data refused, wrong release, insufficient samples, short stabilization window, latency and error limits |
| Detection chain | Real requests through the demo app: healthy baseline → faulted v2 detected → v1 restored → recovery independently verified |
| Telemetry | The real detector and verifier sequences run with and without a collector against an unroutable endpoint produce **identical** verdicts and reasons |
| Incident API | Detection parsed from the committed artifact, all 18 gate checks present, approver and proposal hash, `independent=True` only with a post-rollback window, `missing_artifacts` naming an unreadable file |
| Untrusted evidence | A Duo note that contains instructions and markup is served verbatim by the incident API and changes no status or verdict |
| GitLab outage | `duo_trigger_flow.py` against a local HTTP server that plays GitLab: unreachable → non-zero exit and no evidence file; failure after the trigger → the accepted note is kept and no session is reported; one transient error → the finished session is still recorded |
| Evaluation summary | A run with no verification, a refused verification and a non-independent window are failures; a detection on a healthy control is a false positive; a control with no record is inconclusive |

**Finding from adding the CI test job:** the suite passed locally and failed in the CI image —
`test_enabled_telemetry_reports_its_resources_and_endpoint` asserted telemetry enabled while the
job installed only the control plane's requirements, so the FastAPI instrumentation was absent
and the guarded setup correctly reported itself disabled. The job now installs both shipped
requirement files. The failing test was not skipped.

## 2. The lifecycle, in GitLab CI

Pipeline **2932808602**, project `showcase` (id 87424071), ref `main`, sha `1ba056f`, every job
green. Raw record: `evidence/gitlab-pipeline-2932808602.json`; job artifacts under
`evidence/gitlab-ci-lifecycle-artifacts/`.

| Job | Stage | Trigger | Duration |
| --- | --- | --- | --- |
| `attribution-guard` | verify | auto | 9.9 s |
| `build:workload-image` | build | auto | 71.4 s |
| `deploy:staging` | deploy | auto | 41.8 s |
| `deploy:regressed` | deploy | **manual** | 44.5 s |
| `approval:grant` | operate | **manual** | 21.6 s |
| `rollback:managed` | operate | **manual** | 54.2 s |
| `verify:recovery` | operate | auto | 57.0 s |
| `telemetry-spike` | operate | manual | not played in this run |

| Measurement | Value | Source |
| --- | --- | --- |
| Healthy baseline p95 | 27.24 ms | `baseline-window.json` |
| v2 window 1 | p95 **8.59×** baseline, error rate 13.3% | `faulty-window-1.json` |
| v2 window 2 | p95 **8.75×** baseline, error rate 8.3% | `faulty-window-2.json` |
| Detection | breached `P95_LATENCY` and `ERROR_RATE`, triggered on **window 2** | `ci-detection.json` |
| Safety gate | **18 checks passed**, `veto_codes: []` | `rollback-execution.json` |
| Rollback target | v1 at `sha256:72a3cc17…` — **the same digest as v2** | `rollback-execution.json` |
| Approval | `yablokolabs`, scoped to proposal `70f980983c184108`, 15-minute TTL | `approval.json` |
| Verification | 6.01 s window, 200 samples, p95 **1.014×** baseline, error rate **0.0**, `recovered=True`, `independent=True`, `reasons=[]` | `verification.json` |

**Independence is provable, not asserted:** the verification window started at `04:29:24`,
after the rollback executed at `04:28:18`.

**A refusal kept as evidence:** the first run of `verify:recovery` failed with
`recovered=False reasons=['stabilization window 1.1s is shorter than 3.0s']` — the verifier
refused to certify stability from a window too thin to show it, and the pipeline failed closed.
The record is kept in `evidence/gitlab-ci-verification-refusal.json`.

## 3. The lifecycle, locally, with real containers

41 tests plus a full run against the real Compose workload (`evidence/local-ci-lifecycle/`):
v1 deployed and measured healthy → v2 detected at **p95 8.60×** with 13.3% then 8.3% errors →
approval by `yablokolabs` for proposal `dd7fe7a306dd1183` → `--dry-run` allowed with **nothing
changed** → rollback executed → verification `recovered=True, reasons=[]`.

Six refusals against the same real gate, each naming a different guard and all exiting 2:

| Refusal | Veto code |
| --- | --- |
| No approval | `APPROVAL_PRESENT` |
| Approver `duo` | `APPROVAL_ACTOR_IS_HUMAN` |
| Environment `production` | `ENVIRONMENT_ALLOWLISTED` |
| Target not known-good | `TARGET_IS_KNOWN_GOOD` |
| Wrong image digest | digest mismatch |
| Replay of a consumed key | `NOT_ALREADY_EXECUTED` |

Proof nothing changed: the container's `StartedAt` (03:29:18) still matches the single
successful rollback (`executed_at` 03:29:16.9), and the six refusals ran minutes later.

## 4. Detection and recovery timing (local driver)

From `scripts/demo_regression.py` (`evidence/phase1-regression.json`), reproduced twice:

| Phase | Measurement |
| --- | --- |
| Healthy v1 baseline | 150 real requests, 0 errors, p95 35.6 ms |
| Faulty v2 | 11.3% then 8.7% errors; p95 238.9 ms = 6.72× baseline |
| Time to detect | 7.72 s, on the second sustained window |
| Rollback | 0.51 s (a local process restart at the time; the CI job now exists and ran in 54.2 s) |
| Post-rollback window | 400 requests over ~5 s, 0 errors, p95 28.0 ms = 0.79× baseline |
| Time to verify | 5.22 s; detection to verified recovery 5.43 s; total 13.16 s |

## 5. Repeated runs: success rate and false positives

`scripts/evaluate_runs.py --runs 5 --controls 5`, on this host (4 CPUs, Docker version 29.8.1),
at commit `bc021da`. Raw artifacts and the console log of every run: `evidence/evaluation/`.

**Lifecycle runs** — `scripts/demo_lifecycle_local.sh`, unchanged, five times in sequence:

| Measure | Result over 5 runs |
| --- | --- |
| Recovered **and** independently verified | **5 of 5** |
| Windows needed to detect | 2 in every run (the sustained-window rule) |
| p95 at detection, against the baseline | 8.50 – 9.07× |
| First faulty window started → detection | 6.72 – 6.85 s |
| Rollback executed → verification verdict | 17.84 – 18.48 s (includes the 6 s stabilization window) |
| Verified p95, against the baseline | 0.950 – 1.006× ; error rate 0.0 in every run |
| Wall time of one whole run | 32.12 – 32.72 s |

**Healthy controls** — the same detection path (`ci_incident.py regress`) with both fault
inputs set to zero, five times, four windows of 120 requests each:

| Measure | Result over 5 controls |
| --- | --- |
| Detections on a healthy release (false positives) | **0 of 5** |
| p95 of the 20 control windows, against the baseline | 0.82 – 1.17× (limit 3.0×) ; 0 errors |

What this does and does not support: five runs and five controls show that the result
repeats on this host. They are too few to state a rate with a confidence interval. No
false-negative count is given, because only one fault setting (180 ms latency, 10% errors)
was run; a fault near the thresholds was not tested. The approval is recorded by the host
user without a wait, so no timing here contains human approval time. The control's window
files are named `faulty-window-N.json` because the shared code names them; they hold healthy
measurements.

## 6. Telemetry

`scripts/otel_export_evidence.py` against the group's real collector: **64 spans accepted, 0
failures** from 12 genuine requests (`evidence/otel-export-spike.json`), reproduced **on a
GitLab runner** (job 17073367648, 21.5 s) where the resource attributes carry the real pipeline
context — `service.version` = the commit sha, `gitlab.project.name` = `showcase`
(`evidence/otel-export-ci.json`). With no collector configured the workload serves normally and
`/otel` reports `telemetry_enabled: false`.

Not verified: that those spans render in the Observability UI. There is no public trace-query
REST API, so collector acceptance is the strongest evidence obtainable from this host.

## 7. GitLab Duo

| Run | Result |
| --- | --- |
| Session `9283219`, `developer/v1` | 7332-character grounded analysis; every claim was checked against the code and was accurate |
| Sessions `9283214` | `success` with an **empty** response, because a headless run with no approved tools has no way to read anything. Kept as evidence that a green workflow alone proves only plumbing |
| Sessions `9283600`, `9288721` | Died with `KeyError` — root cause: `aiCatalogFlowUpdate` silently ignores `definition` without `versionBump`/`release`, so sessions kept running the original revision |
| Sessions `9283450`, `9283505`, `9283539`, `9283555` | Four probes that characterised the headless limit: the CLI transmits the custom definition, the service declines to instantiate an inline flow |
| Session `9288744` (custom flow, via the flow trigger) | **`FINISHED`**, 86 s, 17 events, no errors; read the repository and the issue, then posted an investigation report to issue #2 recommending **HOLD**, and its audit caught three mis-transcribed values in this repository's own record |

The load-bearing result is the last one: the flow's value was not that it agreed with the
incident, but that it refused to.

## 8. What these numbers do not show

- **One environment, one fault class.** A single `demo-staging` container on one host and on
  GitLab.com shared runners, with injected latency and error faults. No memory, disk, network or
  dependency-outage fault is exercised, and nothing is claimed about multi-service systems.
- **No production load.** Windows are 150–400 requests at concurrency 4–8. Thresholds are
  hand-set for this workload; they are not derived from a production baseline.
- **The evaluation is not independent.** The author wrote the workload, the detector and the
  verifier, so a shared misconception would survive all three. The one genuinely external check
  is the Duo flow's audit, which found a real documentation error.
- **The recorded CI approval was played through the API** by the token owner during debugging,
  so the approver is a person only because the token belongs to one. The gate itself enforces a
  real, non-agent identity and refuses everything else.
- **`telemetry-spike` was not played in this run**, so `verify:recovery` is the last job of the
  recorded pipeline.
- **The flow's posted note understates its own run**: it says it did not re-open the files, while
  the event stream shows repository reads and its own evidence list names the artifacts it used.
- **No data-recovery claim is made or tested.** A code rollback does not restore deleted data.
