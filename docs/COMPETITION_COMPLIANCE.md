# Competition compliance and stage coverage

**Entry:** GitLab Transcend Hackathon, **Path A: Start Fresh** — a new, independent project, not
a repurposing of any existing work.

**Primary target:** Best Supervised Agent (the approval gate is a supervised decision by design).
**Secondary:** Most Stages Covered (Path A). No prize eligibility is claimed: that is the
judges' call, and the official rules — <https://gitlab-transcend.devpost.com/rules> — override
anything written here. This document records what exists, and what does not.

## Submission assets

| Requirement (as understood) | Status | Evidence |
| --- | --- | --- |
| Public GitLab repository | Yes | `gitlab-ai-hackathon/transcend-october-2026/43178176/showcase`, primary remote `origin` |
| MIT licence | Yes | `LICENSE` |
| Under-3-minute video showing the automation running | **Made**: 2:36, narrated, with a recording of a real lifecycle run inside it and the real GitLab pages. Not in it: a person playing the approval job in the GitLab UI; see [`DEMO.md`](DEMO.md) sections 5 and 6 | https://youtu.be/rvs6M7xOTR0 — checked on 2026-10-10: reachable without a login, and its transcript matches the narration. **Not verified:** that its visibility is Public and not Unlisted; both open with the link, and only the uploader can see the setting. File: `demo/videos/rollbackiq-demo.mp4`, built in `demo/videowright/` |
| Genuine GitLab AI use, visible | Yes | Custom Duo agent + flow provisioned from `duo/`, executed via the project's flow trigger; session `9288744` finished and posted its report to issue #2 |
| No AI attribution footers anywhere | Yes | `scripts/check_no_attribution.sh`, enforced by hooks and the `attribution-guard` job |

## DevSecOps stages: what is genuinely touched

Each row names the artifact that proves it. "Partly" and "not covered" are used where that is
the truth.

| Stage | What runs | Evidence | Honest scope |
| --- | --- | --- | --- |
| **Plan** | The incident exists as a GitLab **issue** with the evidence links; the workspace onboarding issue is kept | issue #2, `evidence/gitlab-pipeline-2932808602.json` | No issue templates, iterations or boards are used |
| **Code** | Conventional commits, one focused change per commit; commit and pipeline context travel into every artifact (sha, pipeline id) | `git log`, `evidence/gitlab-ci-lifecycle-artifacts/deploy-regressed.json` | No merge-request review flow — this is a solo repository, changes land on `main` behind protected-branch rules |
| **Build** | `build:workload-image` builds the real image, pushes it, and publishes its **immutable digest** as an artifact | job 17076805676, `image-digest.txt` | One image, one service |
| **Test** | `test:pytest` runs the full suite in CI (98 tests), including the detector's and the gate's negative cases | the new `test` stage; verified locally by running the job's exact commands in `python:3.12-slim` | No coverage gate, and no JUnit report is uploaded to GitLab yet |
| **Secure** | The attribution guard; the safety gate's 18 checks; secret handling (token from env only, registry login via `--password-stdin`); prompt-injection handling treated as untrusted evidence | `attribution-guard` job; `backend/tests/test_safety.py`; [`SECURITY.md`](SECURITY.md) | **GitLab Secure scanning (SAST, DAST, dependency, container scanning) is not enabled and is not claimed.** The "secure" coverage here is application-level safety, not GitLab's scanners |
| **Release** | A release is a set of deployment inputs on one image; the digest is the identity a rollback may target | `evidence/gitlab-ci-lifecycle-artifacts/rollback-execution.json` | No release objects, changelogs or semantic-release tooling |
| **Deploy** | `deploy:staging` (health-gated, captures the baseline), `deploy:regressed` (manual), `rollback:managed` (manual, gated) inside GitLab environments | jobs 17076805677/78/80; the `demo-staging` environment | The target is an isolated demo environment, never customer infrastructure |
| **Operate / observe** | Real OpenTelemetry traces to the workspace's GitLab Observability collector, from the workload and from the detection/verification decisions | `evidence/otel-export-spike.json` (64 spans, 0 failures), `evidence/otel-export-ci.json` (same, from a runner) | Nothing is claimed about how those traces render in the UI: no public trace-query API exists to prove it from here |
| **Monitor** | The observer's own probes feed a deterministic detector (thresholds, two sustained windows, cooldown) | `backend/app/services/detector.py`, `evidence/gitlab-ci-lifecycle-artifacts/ci-detection.json` | Not wired into GitLab's built-in Prometheus/alerts — detection is this service's logic, not a GitLab alert rule |
| **Incident response** | The Duo custom flow investigates the issue, a human approves one hashed proposal, the gate authorizes a rollback, an independent job verifies recovery | session `9288744`, `approval.json`, `rollback-execution.json`, `verification.json` | The flow does **not** execute remediation; the CI gate does |
| **Retrospective** | Measured results, refusals kept as evidence, and the record correction are all written down | [`EVALUATION.md`](EVALUATION.md), `docs/PROGRESS.md` session logs | — |

## GitLab capabilities: used, and not used

| Capability | Status | Evidence |
| --- | --- | --- |
| GitLab CI/CD pipelines, stages, manual jobs, artifacts, environments, container registry | **Used and verified** | pipeline 2932808602, all jobs green |
| Protected branch on `main` (GitLab refused a force push; a non-force merge was used instead) | **Used and verified** | `docs/PROGRESS.md` |
| GitLab Duo Agent Platform — custom **agent** and custom **flow** in the AI Catalog, provisioned from this repository | **Used and verified** | items `1016480` (agent) and `1016482` (flow); `scripts/duo_provision_catalog.py` reads stored content back and compares by SHA-256 |
| Duo flow **trigger** on the project (event types: mention, assign) | **Used and verified** | trigger `3013795`; session `9288744` |
| Duo CLI (`@gitlab/duo-cli`, foundational `developer` flow) | **Used and verified** | session `9283219` |
| GitLab Duo Code Review on a merge request | **Used and verified** | session `9290081` (`code_review/v1`) on merge request !1: three findings, all confirmed against the code and fixed. Re-review session `9290175` after the fixes: no new finding. `evidence/duo-code-review-mr1.json`. Each review states that it saw less than half of the diff (about 45% and 42%) |
| Duo CLI selecting a **custom** flow headless | **Blocker, characterised** | the CLI transmits the custom definition; the service declines to instantiate it. Recorded with source lines in `docs/PROGRESS.md` |
| GitLab Observability (OTLP collector) | **Used and verified at the collector** | 64 spans accepted, 0 failures |
| GitLab MCP server (`POST /api/v4/mcp`) | **Blocker, characterised — not claimed** | the server answers `403 Forbidden` to `initialize` and `tools/list`: its own challenge requires the `mcp` scope, and the available token does not have it. `evidence/gitlab-mcp-probe.json`, written by `scripts/gitlab_mcp_probe.py` |
| GitLab Secure scanners, DORA metrics, merge request approvals | **Not used — not claimed** | — |

## Judging dimensions

| Dimension | What backs it |
| --- | --- |
| **Technological implementation** | Deterministic detector, 9-state machine that raises on illegal transitions, an 18-check gate that reports every veto, a verifier that refuses to certify from thin or reused evidence, real CI/CD with artifact-carried state, OTLP telemetry, a read-only typed API and a React console — 98 passing tests |
| **Design** | Refusing is a feature: unknown migration, unknown target, unverified baseline and thin windows all fail closed, and the refusals are kept as evidence rather than papered over |
| **Potential impact** | Time-to-detect and time-to-recover are measured in seconds here, and the output is an auditable record a human signed off on |
| **Innovation** | The differentiator is the claim itself: **a successful rollback job is not success**; observed recovery against a verified baseline, measured after the action, is |
| **Presentation** | Five rendered diagrams, a real incident console with six views, screenshots generated from real data, and an evaluated record that states its own weaknesses |

## What is deliberately not claimed

- No prize, eligibility or award is asserted anywhere.
- No Google Cloud or AWS deployment: all of it runs on GitLab.com shared runners and one Azure VM.
- No GitLab Secure scanning, MCP usage, production deployment, customer data, or data-restore capability.
- The fault is **injected deployment configuration on one image**, not a binary regression, and
  the documentation says so next to every set of numbers.
