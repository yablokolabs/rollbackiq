# RollbackIQ — Development Progress

> Persistent checkpoint for coding sessions. Update **at least every 15 minutes** and after milestones.  
> Hindsight bank: **`rollbackiq`** | Hindsight API port: **8888**

## Current phase
**Session 009 (2026-10-10): submission completion, on branch `submission-completion`.** The system is built and evidenced; this session closed specification gaps. Done and committed: a repeated-run evaluation (**5 of 5** lifecycle runs recovered and independently verified, **0 of 5** false positives on healthy controls, `evidence/evaluation/`), outage handling in `scripts/duo_trigger_flow.py`, negative tests for untrusted evidence and a GitLab outage (**108 passed**), `docs/INCIDENT_RUNBOOK.md`, `.env.example`, the recording moved to `demo/videos/`, and a correction of four wrong check codes in `docs/SECURITY.md`. The GitLab MCP spike ended in a characterised blocker (the token has no `mcp` scope). Later in the session: the narrated demonstration video was built (`demo/videos/rollbackiq-demo.mp4`, 2:36, VideoWright project in `demo/videowright/`), the diagrams were embedded in the README and re-rendered whole, and the branch pipeline ran `test:pytest` on a runner for the first time (success). Open: a take with the approval played by hand in the GitLab UI, the GitLab MCP token, and the merge of this branch.

**User decisions in session 009:** work on a branch, not on `main`; push the branch and open a merge request, the user merges; **use only the `showcase` project (`origin`)** — do not push to `rollbackiq-project`; the video uses a **British female ElevenLabs voice**, with `~/mender/demo/videos` and `~/sightops/demo/videos` as references; the video rules are: under three minutes, shows the automation running (not slides or a mockup), explains the problem, the solution and the use of GitLab.

State before session 009, kept for the record:

**The end-to-end lifecycle now runs on GitLab, and a real Duo flow has executed.** As of `a192569`, one pipeline (`2932808602`, showcase) carries build → deploy → deliberate regression → human approval → safety-gated rollback → independently verified recovery, every job green, with the measured numbers recorded in `evidence/`. The Phase 0 Duo gate is met: `duo run` completed session `9283219` on the `developer/v1` flow and returned a grounded 7332-character analysis whose every claim was checked against the code. OpenTelemetry is wired into the workload and the control plane. A **custom Duo agent and custom flow exist in the AI Catalog**, are provisioned from the repository, enabled in the project, and **they now execute end-to-end through a real flow trigger**: session `9288744` finished and posted a genuine investigation note to incident issue #2. Getting there required fixing two real defects: the flow YAML (`OneOffComponent` has no `final_answer` output; inline prompts need `placeholder: history`; `params` must not be a mapping) and, more subtly, `scripts/duo_provision_catalog.py`, whose update path was a **silent no-op** — without `versionBump`/`release` the catalog kept serving the old revision while provisioning reported success. The script now passes both fields and reads the stored definition back, comparing it with the repository file by SHA-256. The flow's first successful audit caught a real transcription error in the incident record, which has been corrected. The headless CLI still cannot select a custom flow (inline config is declined; that finding stands). Two further Duo investigations ran earlier and one found a genuine bug in `safety.py`, now fixed and covered by tests. **The incident console now exists** (`backend/app/api/incident_api.py` + `dashboard/`, session 008): a read-only API over the pipeline's own artifacts, six views, and a Chromium render check that fails on any page or console error. **Session 008 also finished the graphics and the documentation**: five diagrams (`docs/diagrams/`) drawn with the `diagram-design` skill, each self-checked and geometry-audited; `docs/ARCHITECTURE.md`, `SECURITY.md`, `EVALUATION.md`, `DEMO.md` and `COMPETITION_COMPLIANCE.md`; and a real gap closed — the pipeline never ran the test suite, so a `test:pytest` job now gates it (which immediately exposed a test that passed locally and failed in the CI image, fixed properly). Remaining work is the demo video and the submission pass.

## GitLab pipeline: full lifecycle end to end (2026-10-10, `a192569`)

Pipeline **2932808602** on `showcase` (`main`), status **success**. Runner: GitLab.com shared. Duration per job:

| Job | Stage | Trigger | Status | Duration | Job id |
| --- | --- | --- | --- | --- | --- |
| `attribution-guard` | verify | auto | success | 9.9 s | 17076760897-era |
| `build:workload-image` | build | auto | success | 71.4 s | — |
| `deploy:staging` | deploy | auto | success | 41.8 s | — |
| `deploy:regressed` | deploy | **manual** | success | 44.5 s | — |
| `approval:grant` | operate | **manual** | success | 21.6 s | — |
| `rollback:managed` | operate | **manual** | success | 54.2 s | — |
| `verify:recovery` | operate | auto | success | 57.0 s | 17076805681 |
| `telemetry-spike` | operate | manual | not run | — | — |

URL: https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43178176/showcase/-/pipelines/2932808602

**Measured in CI, not simulated:**

- Detection on the regressed release: window 1 **p95 8.59x** baseline (234.0 ms against a 27.24 ms baseline) at 13.3% errors, window 2 **8.75x** (238.4 ms) at 8.3% errors, breaches `P95_LATENCY, ERROR_RATE`, triggered on window 2 (the sustained-window rule held on a real runner).
- The rollback ran through the control plane's own `SafetyGate`: **all 18 checks passed**, `veto_codes: []`, then it deployed v1 at digest `sha256:72a3cc17…` — **the same digest as v2**, because the fault is injected deployment configuration on one image, not a different binary.
- The independent verification job measured a **6.01 s window of 200 samples** starting `04:29:24` — after the rollback executed at `04:28:18`, so `independent=True` is provable, not asserted — with **p95 at 1.014x** the healthy baseline, error rate **0.0**, `recovered=True`, `reasons=[]`.
- The approval artifact names `yablokolabs`, taken from `GITLAB_USER_LOGIN`, scoped to proposal `70f980983c184108`. **`GITLAB_USER_LOGIN` is populated for manual jobs** — now verified rather than assumed.

> **Record correction (2026-10-10).** An earlier revision of this section (and of incident issue #2) cited window ratios `6.31x / 6.43x`, target digest `sha256:211383c1…` and proposal hash `d17d4968d76a71c9`. None of those three values appears in any job artifact; they were mis-transcribed from an earlier, differently-baselined note. A **custom Duo flow's independent re-read** (session `9288744`, whose audit note is on issue #2) surfaced the mismatch and explicitly refused to accept the unreconciled numbers. The values above are taken directly from `evidence/gitlab-ci-lifecycle-artifacts/` (`ci-detection.json`, `faulty-window-1.json`, `faulty-window-2.json`, `rollback-execution.json`, `approval.json`, `verification.json`). The flow's audit is why this was caught.

**Two real bugs that only running it could find, both mine:**

1. `build:workload-image` failed with `denied: requested access to the resource is denied` *after* a successful build. It reads as a registry permission problem; it was a missing `docker login` in the job template, so the push was anonymous. Confirmed by pushing the same image by hand with the PAT (which succeeded) and by the API showing `container_registry_enabled: true`.
2. `verify:recovery` failed with `recovered=False reasons=['stabilization window 1.1s is shorter than 3.0s']` — the verifier refusing to certify recovery from a window too short to demonstrate stability, and the pipeline failing closed. The window was thin because `--min-duration` was in the local run but missing from that job. **The refusal is kept as evidence** (`evidence/gitlab-ci-verification-refusal.json`), because failing when the evidence is insufficient is the behaviour that matters most here. Fixed and re-run green.

Cleanups done: the stray `manual-test` registry tag from the diagnostic push was deleted, and the credential `docker login` wrote to `~/.docker/config.json` was removed (the token lives only in the user's `~/.hermes/.env`).

**How the manual jobs were triggered — stated plainly.** I played `deploy:regressed`, `approval:grant` and `rollback:managed` through the API with the user's own PAT, under their "debug it until it runs" instruction. The environment is the isolated `demo-staging` demo target, not customer infrastructure. The consequence is that the recorded approver is the token owner rather than a person clicking Approve in the UI, so for the demo the approval should be played by hand to show the gate as a human decision. This is a caveat about the demo, not a defect in the gate: the gate enforces that a real, non-agent identity approved a specific proposal hash, and it refuses on every other path.

## GitLab Duo: first real flow execution (2026-10-10)

The Phase 0 gate required a genuinely executed Duo agent or flow. It is now met, and the discovery path is worth recording because the CLI was not present at session start:

- **`@gitlab/duo-cli` v9.16.0** exists on npm, published by GitLab CI/CD. Installed globally; binary `duo`. This is the real Duo CLI (`glab duo cli` is the same tool).
- Invocation used: `duo run --goal … --flow-config-id developer --output-format json --gitlab-project-path <path> --duo-workflow-project-id 87424071 --session-tracking-enabled false --dangerously-skip-permissions`, run in an **isolated clone** so any write tool is contained.
- **Session `9283219`, flow `developer/v1`, status `success`**, negotiated over WebSocket against GitLab's Duo Workflow Service. Capabilities returned: `job_trace_pagination, tool_call_approval_source, incremental_checkpoints, advanced_search, incremental_checkpoints_only, duo_developer, tool_call_approval, tool_call_pattern_approval, flow_semantic_versioning, inline_flow_config_binding`.
- The response was a **7332-character grounded analysis** naming the real checks a deployment change must pass. Every claim was verified against the code: `ENVIRONMENT_ALLOWLISTED` (`safety.py:92`), `TARGET_IS_KNOWN_GOOD` (`:124`), `IDEMPOTENCY_KEY_PRESENT` (`:193`), the corrupt-ledger `SystemExit` (`ci_rollback.py:168`), the missing-bundle check (`:219`). It is accurate, not flattering.
- **The first attempt (`9283214`) is kept as evidence too**: `success` with an empty response, because a headless run with `approved_tools=[]` has no way to read anything. A green workflow proves the plumbing worked and nothing more — recorded so the distinction is not lost later.
- `--session-tracking-enabled false` was passed deliberately so Duo cannot append a session trailer to a commit, which AGENTS.md section 10 forbids.

**The raw CLI log is deliberately not committed.** It embeds `AGENTS.md` as flow context, so it contains the attribution strings the guard forbids; the guard blocked the commit and was right. A policy quotation is not a reason to add an exemption, so only bounded fields are extracted into `evidence/duo-flow-developer-run.summary.txt`.

**Honest gap at the time:** that run used the foundational `developer` flow, not a **custom** flow. `inline_flow_config_binding` looked like the route. It is not, and the reason is established below with the source line — see *Blocker: the headless CLI cannot select a custom flow*.

## Custom Duo agent and flow in the AI Catalog, and the headless blocker (2026-10-10)

AGENTS.md §5 asks for **custom** Duo agent(s)/flow(s), not only a foundational flow. Both now exist in the project's AI Catalog, provisioned **from the repository** rather than clicked into existence:

| Catalog item | Type | GID | Version | Source of truth |
| --- | --- | --- | --- | --- |
| RollbackIQ Recovery Investigator | `AGENT` | `1016480` | 1.0.0 | `duo/agents/rollbackiq-recovery-investigator.md` |
| RollbackIQ Recovery Investigator Flow | `FLOW` | `1016482` | 1.0.0 | `duo/flows/rollbackiq-recovery-investigator.yaml` |

`scripts/duo_provision_catalog.py` creates or re-asserts both from those files (`--dry-run` reports without mutating). The definition is a real component graph, not a prompt: `recall_incident_evidence` (`OneOffComponent`) gathers deployment and telemetry evidence, then `assess_and_propose` (`AgentComponent`) turns it into supported/contradicted hypotheses, named unknowns, and one of roll back / hold / escalate. The flow has **no tool that can deploy, approve or roll back**; execution authority stays in `backend/app/services/safety.py`.

**The schema was established by probing, not guessing.** GraphQL introspection returned a schema blob, so the shape came from the server's own per-field rejections: `One and only one of [public, visibility] is required` → add `public`; `Flow definition is missing and cannot be validated` → the definition travels in the mutation; `prompts.N.unit_primitives: Field required` → a prompt field the docs do not mention. Re-running the provisioning script against the committed YAML returned `errors: []`, so the file that ships is the file that compiled.

**Why that response means more than "green":** `definition` and `systemPrompt` are **write-only** — neither is exposed on `AiCatalogItemVersion` — so a re-assert is the only way to keep the catalog aligned with the repo, and the script states that instead of implying it diffed them. A clean response is evidence the definition *compiled server-side*, which is stronger than "the YAML parsed".

### Blocker: the custom flow reaches the service, which then refuses the session

This took four runs to characterise, and the last two narrowed it properly rather than stopping at the first refusal. All four are in `evidence/duo-flow-runs.json`.

**1 — `--flow-config` alone is silently ignored.** Sessions `9283450` and `9283505` negotiated `workflow_definition=developer/v1` and `flowConfigId: developer`, and never mention the custom flow's component names. The cause is in the CLI's own published source:

```ts
// @gitlab/duo-cli — src/backend/gitlab/workflow_strategy.ts:407
const legacy = !isHeadless && Boolean(backendOpts.legacy);
```

A truthy `flow.developer` takes the branch at `gitlab_backend.ts:475` that sets `flowConfig = undefined`, and `--legacy` — the escape hatch to the branch that honours an explicit flow config — is disabled whenever the session is headless. So plain `duo run` always prefers the instance-advertised developer flow.

**2 — `--workflow-type` *is* honoured headless, and that escapes the override.** The neighbouring line is the key one:

```ts
// workflow_strategy.ts:406 — headless DOES honour the workflow type override
const workflowTypeOverride = isHeadless ? backendOpts.workflowType : undefined;
```

It returns a `plainDescriptor`, which carries no `developer` field, so the session falls through to `#resolveExplicitFlowConfig()` and the explicit flow config *is* sent.

**3 — the CLI then transmits the custom flow, pinned to my own definition.** Session `9283539` ran with `--workflow-type rollbackiq/recovery-investigator/v1 --flow-config duo/flows/…yaml`. The wire shows exactly what was intended: `workflow_definition=rollbackiq%2Frecovery-investigator%2Fv1`, and the log contains `"flowConfig": "# RollbackIQ Recovery Investigator — GitLab Duo custom f…"`. **So the mechanism works** — the custom flow definition genuinely reaches the Duo Workflow Service.

**4 — the service refuses to run it.** Session `9283539` came back with an in-band service error (`There was an error processing your request in the Duo Agent Platform`), and session `9283555` — retried with `--workflow-type chat` and the CLI's own inline `environment: chat-partial` — failed with `WebSocket closed abnormally`, code `4400`. The service accepts the transport but will not instantiate a flow from an inline definition that is not registered in the flow registry.

**Where that leaves it.** The flow is now **enabled in the project** (`aiCatalogItemConsumerCreate` with `itemId` + `target: {projectId: …}` returned `errors: []`; the group-level target was correctly refused with a permission error). Executing a custom flow therefore needs a surface that resolves a *registered* catalog flow — the Agent Platform / IDE / trigger path — not headless inline config.

Recorded as a **blocker with evidence**, not worked around, and not glossed as success. The correct claim today is: *a real Duo flow executes and does genuine tool-driven investigation; a custom agent and custom flow exist in the AI Catalog, validate server-side, and are enabled in the project; the headless CLI transmits the custom definition correctly but the service declines to instantiate it.*

### Two real investigations, and the bug the first one found

Both runs were real tool-driven investigations of the incident (6 and 7 file reads, 8 and 2 shell commands) rather than summarisation. The first returned a finding that was **correct, and about my own code**:

> several of the 18 check `detail` strings read as if the check *failed* but the `passed` field is `true`

Verified in `backend/app/services/safety.py`: every detail was written as the failure phrasing unconditionally, so a passing check emitted `approval actor 'yablokolabs' is not an authorized human identity` beside `passed: true`. **Fixed**, keeping the failure wording byte-identical on the refusal path — the path that matters most — with two regression tests added. The first attempt at the fix was itself wrong: a plain f-string default is evaluated even on the failing path, so `target_release.id` raised on `None`; the suite caught it and `on_pass` became a lazy callable.

The second run added a caveat worth keeping: the demo's regression is **injected deployment configuration (fault-injection environment variables), not a binary code change**, and it named the one question the available evidence cannot answer — whether v2's ~240 HTTP 500 responses caused write-side data inconsistency. It refused to assert data consistency was fine. Both responses are in `evidence/duo-flow-runs.json`.

### Demo video — acceptance criteria (user-provided, 2026-10-10)

1. **Under three minutes.**
2. **Shows the automation actually running** — not slides, not a mockup.
3. **Explains the problem, the solution, and how GitLab was used.**

Consequences: the deploy → detect → approve → rollback → verify chain must be shown running for real, and the approval must be played **by hand in the UI** so the recorded approver is a person, not the token owner. Because of the blocker above, the Duo segment must not imply the custom flow orchestrates the lifecycle; it shows what actually executed.

## CI/CD lifecycle, approval gate and control-plane instrumentation (2026-10-10)

The pipeline now carries the real lifecycle rather than stopping at detection. `main` = `05af988`.

| Job | Stage | Trigger | What it actually does |
| --- | --- | --- | --- |
| `attribution-guard` | verify | automatic | existing attribution scan |
| `build:workload-image` | build | automatic | builds and pushes the image, resolves and publishes its **immutable digest** |
| `deploy:staging` | deploy | automatic | deploys v1, health-gated, captures the **healthy baseline window** artifact |
| `deploy:regressed` | deploy | **manual** | deploys v2, measures, and fails **without writing a bundle** unless the real detector fires |
| `approval:grant` | operate | **manual** | records the approval against `GITLAB_USER_LOGIN` for the person who played the job, scoped to the proposal hash |
| `rollback:managed` | operate | **manual** | runs the control plane's `SafetyGate` over the bundle, then deploys the target |
| `verify:recovery` | operate | automatic | fresh deploy and a **new** post-rollback window, then `verify_recovery` must prove it |
| `telemetry-spike` | operate | manual | existing OTLP export proof |

New scripts, all stdlib/`backend` only and runnable unchanged locally and in a job: `scripts/ci_release.py` (deploy/stop/probe/verify), `scripts/ci_incident.py` (regress/approve/combine), `scripts/ci_rollback.py` (the gated executor), `scripts/ci_probe.py` (paced independent probe).

**Verified locally with real containers** (`evidence/local-ci-lifecycle/`, 41 new tests → suite **88 passed**):

| Step | Measured result |
| --- | --- |
| deploy v1 + baseline (150 samples) | healthy, error rate 0% |
| deploy v2 + detect | **p95 8.60x baseline, error rate 13.3% then 8.3%**, triggered on window 2 |
| approval | APPROVED by `yablokolabs` for proposal `dd7fe7a306dd1183` |
| rollback `--dry-run` | gate allowed, **nothing changed** |
| rollback execute | executed; recovery **verified: `recovered=True, reasons=[]`** |
| verify:recovery job | fresh deploy + new window: `recovered=True independent=True reasons=[]` |

Six refusals were run, each required to name a *different* guard and all exited 2: no approval → `APPROVAL_PRESENT`; approver `duo` → `APPROVAL_ACTOR_IS_HUMAN`; environment `production` → `ENVIRONMENT_ALLOWLISTED`; target not known-good → `TARGET_IS_KNOWN_GOOD`; wrong image digest → digest mismatch; replay → `NOT_ALREADY_EXECUTED`. Proof the refusals changed nothing: the container's `StartedAt` (03:29:18) still matches the single successful rollback (`executed_at` 03:29:16.9), and the six refusals ran minutes later.

**Two real bugs the local run found, both fixed:**
1. The probe burst as fast as it could, producing a **1.1 s** post-rollback window, which the verifier correctly refused as shorter than a stabilization window. The verifier was right and the measurement was wrong, so the probe now takes `--min-duration` and paces itself.
2. `verify` expected a `Baseline` object but the baseline artifact is the raw healthy *window*; it now builds the `Baseline` via `from_window` and **refuses to certify against an unverified baseline**.

Also fixed: the health wait resolved `container:8000` from the job, which is not on the docker network (and under `dind` the job and daemon are separate containers), so it now reads `/release` via `docker exec` from inside the container. A bind mount is deliberately not used for the probe: under `dind` a mount resolves on the daemon's filesystem, not the job's.

**Honest limitations of this design:** GitLab jobs are ephemeral, so a container does not survive from one job to the next; state travels as artifacts and each job re-establishes its deployment. The idempotency ledger is a JSON artifact, which makes a re-run inside a pipeline refuse but is **not a distributed lock**. The digest identity check proves *artifact* identity — v1 and v2 are the same build with different deployment inputs, which is what makes “roll back” a change of inputs rather than a rebuild. The CI networking and `docker:dind` assumptions are **not yet proven on a runner**.

Control-plane telemetry: `backend/app/integrations/otel.py` adds OTLP export plus spans around `RegressionDetector.evaluate` and `verify_recovery`, recording the verdict **after** the decision so attributes describe the conclusion. Setup is guarded so telemetry can never break or change a decision; the test that matters runs the real detector and verifier sequences with and without a collector against an unroutable endpoint and asserts every verdict and reason is identical.

## GitLab CI evidence (first real pipeline)

| Item | Value |
| --- | --- |
| Project | `gitlab-ai-hackathon/transcend-october-2026/43178176/rollbackiq` (id **87449782**), public |
| Duo on the project | `duo_foundational_flows_enabled = true`, `duo_remote_flows_enabled = true` |
| Pipeline | id **2932203567**, status **success**, ref `main`, sha `796df35a` |
| Job | id **17073050784**, `attribution-guard`, stage `verify`, status **success**, **8.93 s** |
| Runner | `k8s.saas-linux-small-amd64.runners-manager.gitlab.com/default` (GitLab.com shared runner, docker+machine executor) |
| What the job proved | `attribution guard: clean — 35 unit(s) scanned` for files, and `attribution guard: clean — 5 unit(s) scanned` after `(scanned 5 commit message(s) in range: 796df35…)` |
| Captured records | `evidence/gitlab-pipeline-2932203567.json`, `evidence/gitlab-pipeline-2932204831.json` via `scripts/capture_pipeline_evidence.py` |

Seven pipeline runs have now gone green (four in the dedicated project, three in showcase), so CI enforcement is repeatable rather than a one-off:

| Project | Pipeline | Commit | Status | Job | Duration |
| --- | --- | --- | --- | --- | --- |
| rollbackiq | 2932203567 | `796df35a` | success | 17073050784 | 8.93 s |
| rollbackiq | 2932204831 | `cb78914f` | success | 17073060503 | 9.84 s |
| rollbackiq | 2932205470 | `047267b5` | success | — | passed |
| rollbackiq | — | `41bd087` | success | — | passed |
| showcase | 2932220957 | `7166d0de` | success | 17073185452 | 9.64 s |
| **showcase** | **2932227652** | **`7c10cf3a`** | **success** | **17073237708** | **9.48 s** |
| rollbackiq | 2932227684 | `7c10cf3a` | success | 17073237840 | 9.15 s |
| showcase | 2932233927 | `a1828546` | success | — | passed |
| showcase | 2932245570 | `8869c576` | success | 17073367647 guard + 17073367648 telemetry-spike (played manually) | 9.x s + 21.5 s |

By commit `6797fa2` every push to `main` on either project has produced a green pipeline (nine in total). All of them ran the `attribution-guard` job on a GitLab.com shared runner (`k8s.saas-linux-small-amd64.runners-manager.gitlab.com/default`), recorded job-by-job in `evidence/`.

The showcase run of `7166d0de` is the notable one: its job scanned **38 files** and **10 commit messages** (range `a4d8a7ad..7166d0de`, i.e. from the workspace starter commit through the merge) and reported clean for both.

Pipeline URL pattern: https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43178176/showcase/-/pipelines/2932220957

### Repository topology (decided)

The user needs the **hackathon-provided `showcase` project** to hold the project, so it is now the primary remote (`origin`) and the dedicated `rollbackiq` project is secondary (`rollbackiq-project`). Both carry the identical history and tree:

- `showcase` `main` = `7166d0de`, a **non-force merge** whose parents are the workspace starter commit `a4d8a7ad` and the project tip `896c6b7`. The merge was required because the histories were unrelated; GitLab itself refused a force push to the protected `main`, which is the correct behaviour and is why the starter commit is preserved rather than discarded.
- The dedicated `rollbackiq` project (id 87449782) received the same commit by fast-forward and can be deleted if the user prefers a single repository; deleting a project is destructive and has not been done without their say-so.

Push authentication: the remote URL itself carries no credentials. A repository-local credential helper supplies the token from the environment at push time (`credential.helper` holds only a snippet referencing `$GITLAB_TOKEN`, verified to contain no token value), and the token is never written to `.git/config` or committed.

## Current task
1. **Push and merge.** Merge request !1 (`submission-completion` → `main`) on `showcase`. Commits after `5d3c349` are local until the next push.
2. **A take with the approval played by hand** (needs the user): pipeline `2934281629` waits at `deploy:regressed`. Steps in `docs/DEMO.md` §6.
3. **GitLab MCP** (needs the user): a token with the `mcp` scope, or the OAuth flow in a browser. Then `scripts/gitlab_mcp_probe.py --call <read-only tool>`.

Resolved uncertainties from the first pipeline: `docker:27-dind` **is** permitted on the shared runner; the registry accepts the image once the job logs in; `apk add python3 py3-pip` plus `pip install --break-system-packages` works on the Alpine `docker:27` image; and `GITLAB_USER_LOGIN` **is** populated for manual jobs.

## GitLab access (verified 2026-10-09)

| Item | Value |
| --- | --- |
| Account | GitLab user `yablokolabs` (id 43178176), recognised as the hackathon workspace owner |
| Workspace group | `gitlab-ai-hackathon/transcend-october-2026/43178176` (group id 144345494), public, project creation allowed at **developer** level; token access level 30 |
| Workspace project | `…/43178176/showcase` (project id 87424071), public, `main`, currently only the starter README, onboarding issue #1 |
| `glab` CLI | authenticated: "Logged in to gitlab.com as yablokolabs (GITLAB_TOKEN)" via the documented `gitlab/glab` image |
| Token | fine-grained PAT from `~/.hermes/.env`; value never printed or stored |
| Duo Agent Platform | `duo_foundational_flows_enabled = true` and `duo_remote_flows_enabled = true` on the project — the Phase 0 gate has a real target |
| CI/CD | `jobs_enabled = true`, container registry and pages enabled, no pipelines have run yet |
| Convention evidence | across 100 visible workspaces in this hackathon iteration, 87 use the provided `showcase` project and 13 created their own named project (for example `drift-guard`, `deadhand`, `shipmill`) |

**Correction to an earlier statement in this file.** The URL originally supplied (`…/2870391/showcase`) was first reported here as returning 404. That was wrong, and the error is worth recording because of what it actually is: it is a **real project belonging to a different participant**. Verified by API:

| Project | Path | Namespace | Owner |
| --- | --- | --- | --- |
| 87399648 | `…/transcend-october-2026/2870391/showcase` | group id 144290527, path `2870391` | **`romamo`** (DevPost: romamo) |
| 87424071 | `…/transcend-october-2026/43178176/showcase` | group id 144345494, path `43178176` | **`yablokolabs`** (this user) |

Both URL forms return HTTP 200, which is why the wrong link was not self-evidently wrong. The numeric segment is the participant's user id, not a project id, and `2870391` is someone else's. The correct workspace project for this submission is the `43178176` one, and that is where `origin` points.

`/api/v4/namespaces` confirms exactly one hackathon workspace namespace for this user: `gitlab-ai-hackathon/transcend-october-2026/43178176` (id 144345494).

## Last completed milestone
**The incident console renders the real incident.** `backend/app/api/incident_api.py` serves typed JSON read from the pipeline's own artifacts (18 safety checks, the approval scoped to proposal `70f980983c184108`, the Duo session and the note it posted, the independent verification window) and `dashboard/` renders Overview, Timeline, Investigation, Approval centre, Verification and Incident report. `scripts/screenshot_dashboard.py` captured all six views with **no page or console errors**, and the API is covered by 8 new tests (**98 passed**).
**A custom GitLab Duo flow executes end-to-end.** Session `9288744` — started by mentioning the flow's service account on incident issue #2 — finished, read the repository's committed evidence artifacts, and posted its own investigation note recommending HOLD and escalating the data-consistency question; its audit caught a real transcription error in the incident record, now corrected in the issue, this file and `evidence/gitlab-pipeline-2932808602.json`. On the CI side, pipeline `2932808602` still carries the full build → deploy → regression → approval → rollback → verification lifecycle with every job green.

## Phase 0 capability matrix (initial snapshot on this host, 2026-10-09)

This matrix is the state **before** a token was provided. It is kept for the record; the token-dependent rows are superseded by the capability sections further down.

| Capability | Observed result | How it was checked |
| --- | --- | --- |
| `glab` CLI | Works, version 1.122.0, but only via the documented `gitlab/glab` container image; not installed on the host | `docker run --rm --entrypoint glab gitlab/glab --version` |
| GitLab authentication | **None configured** at the time of this snapshot; API returned 401. Superseded: the token now authenticates and `glab` is logged in | `docker run --rm --entrypoint glab gitlab/glab auth status` |
| GitLab project / namespace | **None**; no git remote configured | `git remote -v` (empty) |
| GitLab token in environment | **None set** (checked by name only; no value was printed) | env presence loop for `GITLAB_TOKEN`, `GITLAB_PAT`, `CI_JOB_TOKEN`, `GLAB_TOKEN` |
| GitLab Duo CLI | Binary not present; **capability unverified** | `command -v duo` / `glab-duo` → missing |
| GitLab MCP server | **Unverified**; needs an account, project and plan to inspect tools/scopes | not attempted |
| Duo Agent Platform custom agents/flows | **Unverified — this is the Phase 0 gate** | not attempted |
| Network reachability | `gitlab.com` 301, `registry.gitlab.com` 200, `pypi.org` 200 | `curl` status codes |
| Docker | 29.8.1, Compose v5.5.1, daemon working | `docker --version`, live container runs |
| Python / Node | 3.12.3 / v22.23.2 (pip and venv installed this session) | `--version` |

### Token permissions: what works and what is refused (measured)

| Operation | Result |
| --- | --- |
| Read project, tree, branches, commits, issues, pipelines, environments, members | allowed (HTTP 200) |
| Write repository commits | allowed (an intentionally invalid commit returned HTTP 400 "provide at least one action", not 403) |
| Create a project (`POST /projects`) | **refused: HTTP 403 `insufficient_granular_scope` — needs user permission `Project: Create`** |
| Read protected branches | refused: HTTP 403 `insufficient_granular_scope` |
| `GET /version` | refused: needs instance permission `Metadata: Read` |

Because the chosen destination is a **new** project in the workspace group, the immediate blocker is that one missing permission. Either add `Project: Create` to the existing fine-grained token, or use a token whose scope covers it, or create the empty `rollbackiq` project in the workspace group manually so this session can push into it. Nothing has been created or pushed yet: the showcase project still holds only its starter commit, and no other project besides `showcase` and `yabloko-labs-ltd-group/yabloko-labs-ltd-project` exists for this account.

## Completed features
- [x] Repository on `main` with the attribution guard enforced by local hooks and CI
- [x] Deterministic healthy `v1` and faulty `v2` workload with real HTTP measurements and fault injection
- [x] Docker image and Compose stack for both releases (one image, deployment inputs differ)
- [x] Regression detector: thresholds, minimum samples, sustained windows, cooldown
- [x] Incident state machine with illegal transitions rejected
- [x] Safety gate: approval scope/expiry/actor, environment allowlist, known-good target, migration veto, idempotency
- [x] Independent recovery verification (refuses non-independent or failed windows)
- [x] Unit, negative and integration tests (110 passing)
- [x] Real GitLab Duo agent/flow execution — custom flow registered, enabled and executed (`evidence/duo-flow-trigger-session.json`)
- [x] Real GitLab CI/CD deploy and rollback jobs (pipeline `2932808602`)
- [x] Evidence-based investigation via Duo with GitLab context — the flow's audit note on issue #2 caught a real record error
- [x] Read-only control-plane API over the pipeline's own artifacts (`backend/app/api/incident_api.py`)
- [x] Incident console (React + TypeScript + Tailwind) with every view rendered and checked (`scripts/screenshot_dashboard.py`)
- [x] Five diagrams, self-checked and geometry-audited (`docs/diagrams/`, `scripts/render_diagrams.py`, `scripts/check_diagram_geometry.py`)
- [x] Documentation set (`ARCHITECTURE.md`, `SECURITY.md`, `EVALUATION.md`, `DEMO.md`, `COMPETITION_COMPLIANCE.md`)
- [x] The suite runs in CI as `test:pytest` (it did not before; see session 008)
- [x] Demo recording of a real run + the live console (`demo/videos/rollbackiq-demo.mp4`, 1:44, produced by `scripts/record_demo.py`)
- [x] Repeated-run evaluation: 5/5 recovered and verified, 0/5 false positives (`scripts/evaluate_runs.py`, `evidence/evaluation/`)
- [x] `docs/INCIDENT_RUNBOOK.md` and `.env.example`
- [x] Fresh-clone check: 108 tests, guard clean, console builds (diagram render not rerun there; it needs the gitignored skill)
- [ ] GitLab MCP — blocked: token has no `mcp` scope (`evidence/gitlab-mcp-probe.json`)
- [x] Narrated demonstration video, 2:36, with a recording of a real run inside it (`demo/videos/rollbackiq-demo.mp4`, `demo/videowright/`)
- [x] `test:pytest` observed green on a GitLab runner (pipeline `2934281629`, 61.8 s)
- [x] Diagrams embedded in the README and rendered whole
- [x] GitLab Duo Code Review on merge request !1: three findings fixed (`evidence/duo-code-review-mr1.json`)
- [ ] A take with the approval played by hand in the GitLab UI, and the submission pass

## Work in progress
Nothing is running. The evaluation containers were removed. Two older demo containers (`rollbackiq-local-workload`, `rollbackiq-local-workload-verify`) from session 008 are still up; they are harmless and `scripts/demo_lifecycle_local.sh` replaces them. An untracked `CLAUDE.md` is in the repository root; it was not made by this session, and the attribution guard flags its title, so it must not be committed as it is. `.agents/skills/diagram-design/` is gitignored (re-install with `npx skills add cathrynlavery/diagram-design`). The GitLab side is live: catalog items `1016480` (AGENT) and `1016482` (FLOW), consumer `12491887` pinned to flow v`1.1.2`, trigger `3013795` with service account `ai-rollbackiq-recovery-investigator-flow-gitlab-ai-hackathon`.

## Last successful tests
`.venv/bin/python -m pytest` → **108 passed** in session 009 (98 + 10: untrusted evidence, GitLab outage, evaluation summary), on this host and in a fresh clone. In session 008: **98 passed** (90 + 8 for the incident API), and **98 passed in the CI image too**: the `test:pytest` job's exact commands were run in `python:3.12-slim` on this host. That second run mattered — see session 008. Covers:

| Area | Tests |
| --- | --- |
| State machine | happy path, illegal transitions, denial escalates instead of executing, history/actor recording |
| Detector | empty/insufficient windows, unverified or missing baseline, environment mismatch, sustained-window requirement, cooldown suppression, counter reset, error-rate-only breach |
| Safety gate | fully authorized rollback allowed; 15 veto cases (missing/denied/expired/out-of-scope/over-age approval, non-human actor, environment, unknown target, not known-good, target equals current, migration unknown/incompatible, missing/duplicate idempotency key, hold/escalate actions); regression tests for the `on_pass` detail wording |
| Verifier | independent window required, unknown rollback time refused, reused incident data refused, wrong release, insufficient samples, short stabilization window, latency/error recovery limits |
| Detection chain (integration) | real requests through the demo app: healthy baseline → faulted v2 detected → v1 restored → recovery verified |

### Measured end-to-end run (`.venv/bin/python scripts/demo_regression.py`)
Raw record: `evidence/phase1-regression.json`. Reproduced twice with the same class of result.

| Phase | Measurement |
| --- | --- |
| Healthy v1 baseline | 150 samples, 0 errors, p95 35.6 ms |
| Faulty v2 windows | 11.3% then 8.7% error rate; p95 238.9 ms = **6.72x** baseline |
| Detection | breached P95_LATENCY and ERROR_RATE after the second sustained window; **time to detect 7.72 s** |
| Rollback | 0.51 s in this local driver; the GitLab CI/CD equivalent now exists — `rollback:managed` ran in 54.2 s (including job setup) in pipeline `2932808602` |
| Post-rollback window | 400 samples over ~5 s, 0 errors, p95 28.0 ms = 0.79x baseline |
| Verification | `recovered=True`, `independent=True`, no failure reasons |
| Totals | time to verify 5.22 s, detection-to-verified-recovery 5.43 s, total 13.16 s |

Docker artifacts verified by building and running them: image built, container served real requests, `/metrics` reported the 30 real requests it had just served (p50 21.6 ms, p95 24.8 ms), Prometheus exposition rendered, stack torn down.

## Current failures
None outstanding. Two problems found and fixed during this work:

1. The attribution scanner reported a clean result over zero scanned units when a git call failed (false pass). Fixed: a failed git command is now a hard error.
2. The workload's fault injection seeded its RNG identically for every request, so an "8% error rate" could only mean 0% or 100%. Fixed with a per-request deterministic seed.

Also worth recording for future sessions: `git reset --hard` early in verification silently reverted an uncommitted fix; use `git reset --soft` when dropping scratch commits.

## Known blockers
- **GitLab MCP:** `POST https://gitlab.com/api/v4/mcp` returns 403 to the available token. The server's challenge requires scope `mcp`; the token has `api`, `ai_features` and others, not `mcp`. Needs a new token or the browser OAuth flow. Not claimed anywhere.
- **Approval by hand:** the video exists, but no recording shows a person playing `approval:grant` in the GitLab UI. Only the user can do that.
- The duplicate `rollbackiq` project still exists; the user said to use only `showcase`. Deleting the duplicate needs the user's explicit approval.
- `glab` is usable only through the container image here.
- Novayagraph does not index this repository (it answers for another project), so it was not used.
- Not installed on this host: `adhd`, `full-send`, `senior-swe`, `ponytail`. VideoWright is a project dependency in `demo/videowright/` (`npm ci`). `context-mode` is installed as a CLI (`context-mode index|search`).

## Next three actions
1. **Push the branch** and watch the pipeline; then the user merges !1.
2. **The user plays the three manual jobs by hand** on a pipeline of this branch and records the screen (`docs/DEMO.md` §6).
3. **GitLab MCP**, when a token with the `mcp` scope exists.

Re-provisioning note: after editing `duo/flows/*.yaml` or `duo/agents/*.md`, run `scripts/duo_provision_catalog.py`; it bumps a released version and verifies the stored content by SHA-256. To re-run the flow itself, use `scripts/duo_trigger_flow.py`.

Optional but cheap hackathon bonus noted from the onboarding issue: the workspace group supports its own observability stack via **Observe → Observability configuration → Enable Observability**. Not enabled and not required to submit; do not claim it unless it is turned on and observed.

Resolved this session: the token now has full access, project creation returns 201, `origin` is the showcase project and pushes to it succeed without force (protected `main`, non-force merge path).

## Exact next command
```bash
cd /home/azureuser/rollbackiq && git switch submission-completion && .venv/bin/python -m pytest -q && git status --short && git log --oneline origin/submission-completion..HEAD
```

## Latest Git commit
Branch `submission-completion`. `origin/submission-completion` is at `5d3c349` (merge request !1). Run `git log --oneline origin/submission-completion..HEAD` for the commits that are not pushed yet; they hold the diagram embedding and render fix, and the video project. `origin/main` is still at `5936280`.

## Hindsight synchronization status
Bank `rollbackiq` is active and reachable over HTTP on port 8888 (the `hindsight` CLI is not installed; use `POST /v1/default/banks/rollbackiq/memories` and `…/memories/recall`). Session 009 findings are retained. No secrets are stored.

## Coding standard: no attribution footers

Rule: commits, merge requests, issues, documentation, source files, diagrams, release notes and demo scripts never carry an AI attribution footer, trailer or assistant signature.

- `scripts/check_no_attribution.sh` is the single source of truth: modes `files`, `staged`, `commit-msg <file>`, `range <rev>`, `patterns`.
- Versioned hooks in `scripts/git-hooks/` call it. Run `scripts/install-git-hooks.sh` after a fresh clone: it sets `core.hooksPath` in the repository's local config only.
- `AGENTS.md` and the scanner itself are excluded from file scans (one quotes the prohibited examples as policy, the other defines the patterns); both exclusions are printed on every run.
- `git commit --no-verify` bypasses the message hook, which is why the `pre-push` hook and the `attribution-guard` CI job exist.

## Evidence links
- `evidence/phase1-regression.json` — raw windows, detection decision, verification result and timings.
- `evidence/evaluation/summary.json` — repeated-run counts and timings; `evidence/gitlab-mcp-probe.json` — the MCP refusal.
- Pipeline `2932808602`, Duo session `9288744` and incident issue #2 are linked in the sections above.

## Session log

### Session 009 — Takeover, gap closure, and a measured success rate

- **Context recovered** from the three documents, Git and Hindsight (199 facts). Git and tests agreed with this file, except that `main` was five commits ahead of `origin`, not four.
- **Repeated-run evaluation.** `scripts/evaluate_runs.py` ran the unchanged local lifecycle five times and a healthy control five times. 5/5 recovered and verified; detection on window 2 every time at 8.50–9.07× baseline; rollback to verdict 17.8–18.5 s; 0/5 false positives, control windows at 0.82–1.17× the baseline (limit 3.0×). Limits are written in `docs/EVALUATION.md` §5: few runs, one fault setting, no false-negative count.
- **Outage handling.** `duo_trigger_flow.py` crashed with a traceback when GitLab failed after the trigger note, and lost the record of the note. It now records `poll_errors`, polls until the timeout, and still writes the evidence file. Tested against a real local HTTP server.
- **GitLab MCP spike.** 403 with the token; the unauthenticated challenge names scope `mcp`; the token does not have it. Recorded, not worked around.
- **Documentation error found:** `docs/SECURITY.md` listed four check codes that the gate never emits. Corrected from `safety.py`.
- **A note on the red phase:** the first run of the outage tests reached gitlab.com with a dummy token and got 401 (no effect), because the script had no configurable URL yet.
- Tests **108 passed**; guard clean; fresh clone verified.

### Session 009 (continued) — The narrated video, the diagrams, and the first test run on a runner

- **The video.** `demo/videowright/` is a VideoWright project (scaffold taken from the user's SightOps project): eight scenes, narration by ElevenLabs voice Alice (British English, female, `eleven_multilingual_v2`), 2:36. To show the automation running, `record_run_footage.py` records a real lifecycle run while it happens, and `composite_footage.py` puts two clips of it into the Detect and Recover scenes. The Recover clip plays at 1.25x and the scene says so. The GitLab pipeline, the `verify:recovery` log and the Duo note are captured from the public GitLab pages.
- **Narration history.** The first key had 1,314 credits, so the first take used the half-cost model and came out at 2:54. The user supplied a key with more credits; the second take is shorter (353 words), uses the better model, and says aloud that the fault is injected configuration on the same image.
- **What the video does not show:** a person playing `approval:grant` in the GitLab UI. The Decide scene states that the token owner played it through the API.
- **Console finding:** the 18 check details in the pipeline `2932808602` artifact carry the old failure-style wording beside a passed mark (the artifact predates the `safety.py` wording fix). The video therefore shows the approval record card only; the live footage shows the checks with the corrected wording.
- **Diagrams.** The README named only the HTML sources, so GitLab showed no pictures; the five PNG files are now embedded. All five PNG files were also cut by 64 px on the right, because the renderer's viewport was narrower than the SVG. Fixed in `scripts/render_diagrams.py`.
- **Duo Code Review on !1.** The user started it from Duo Chat: session `9290081`, workflow `code_review/v1`, `FINISHED`. Three findings, each verified before a change, all true: the timeline sorted timestamp strings of mixed formats (the console listed the baseline before the v1 deployment); the rollback event hardcoded "target release v1"; two npm scripts pointed at missing files. Fixed in `19f2660` and `bdac477`, with three tests (**110 passed**). The review saw about 45% of the diff, by its own statement. Record: `evidence/duo-code-review-mr1.json`. The four threads were answered and resolved. **Re-review:** session `9290175`, requested with `/request_review @GitLabDuo`, found nothing new and confirmed the fixes (it saw about 42% of the diff). **Standing practice from the user:** on every merge request, post `/request_review @GitLabDuo`, verify and fix the findings, reply, resolve, and request a re-review. Assigning the service account `duo-code-review-gitlab-ai-hackathon` as reviewer does not start a review.
- **CI.** Pipeline `2934281629` on the branch: `attribution-guard`, `test:pytest`, `build:workload-image` and `deploy:staging` succeeded on a GitLab runner. The manual jobs wait.

### Session 008 (continued) — The demo run, the recording, and two bugs only a recording could find

- **`scripts/demo_lifecycle_local.sh` now reproduces the whole CI lifecycle on one host in ~32 s with real containers** — deploy v1 and measure the baseline, require the real detector to fire on v2, approve one hashed proposal, evaluate the gate by dry run, execute the gated rollback, then verify recovery from a new window. It uses the *same* scripts the CI jobs run; there is no demo-only code path. Final result: `recovered=True independent=True reasons=[]`, 200 samples, 6.01 s window, p95 0.96× baseline.
- **`scripts/record_demo.py` produced `demo/videos/rollbackiq-demo.mp4`** (1:44, 1440×900, captions, no narration): a real run streamed live into the frame, then the console over that run's artifacts. It is **not** the final submission take, because the approval is the local run's rather than a person clicking Approve in the GitLab UI — recorded as such in `docs/DEMO.md`.
- **Two bugs the recording found, both fixed at the source:**
  1. `ci_release.py` printed its command trace to **stdout**, so `$(ci_release.py digest …)` captured the trace plus the digest and the rollback then refused with a digest mismatch that looked nothing like the cause. Traces now go to stderr, keeping stdout machine-readable (GitLab captures both streams, so job logs are unaffected).
  2. The first take rendered a **blank log pane** for the whole run: the player page was loaded with `set_content()`, and a relative `fetch('/run.log')` cannot resolve on `about:blank`. The page is now served from a routed origin, and the recorder **refuses to keep a take whose log pane rendered fewer than 500 characters** — the guard exists because a blank pane still produced a perfectly valid-looking video file.

### Session 008 (continued) — Diagrams, documentation, and a CI gap worth closing

- **Five diagrams built with the `diagram-design` skill** (`npx skills add cathrynlavery/diagram-design`, installed into `.agents/skills/`, which is now gitignored with the reason). Each is a self-contained HTML + inline SVG: architecture, the Duo sequence, the incident state machine, the trust-boundary layer stack, and the measured pipeline timeline. `scripts/render_diagrams.py` runs the skill's own accessible-SVG `self_check.py` and screenshots **only the `<svg>` node**; `scripts/check_diagram_geometry.py` measures the connector rules that cannot be eyeballed — text collisions, off-canvas text, diagonal connectors, label masks over node boxes. It found a real 0.3 px collision between an actor name and its sublabel in the sequence diagram, fixed by raising the actor boxes rather than loosening the check. Outputs: `docs/diagrams/*.{html,png}`.
- **The documentation set is written**: `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/EVALUATION.md`, `docs/DEMO.md`, `docs/COMPETITION_COMPLIANCE.md`, plus `docs/diagrams/README.md`. Every claim in them is tied to a file or a measured number, and each carries an explicit "what this does not show" section.
- **A real CI gap closed.** The pipeline ran the attribution guard and the lifecycle but **never the test suite**. Added a `test` stage with `test:pytest`, validated the YAML through GitLab's CI lint API (`valid: true`). Then ran the job's exact commands in `python:3.12-slim` on this host, which **failed one test locally-green**: `test_enabled_telemetry_reports_its_resources_and_endpoint` asserted telemetry enabled while the job installed only `backend/requirements.txt`, so the FastAPI instrumentation was absent and the guarded setup correctly reported itself disabled. Fix: install both shipped requirement files. Re-run in the same image: **98 passed**. The test was not skipped, and the finding is recorded in `docs/EVALUATION.md`.
- Honest note kept: the new job's success on a **runner** is not yet observed — that requires a push, and pushing has not been authorised this session. The local run in the job's image is the strongest evidence available here.

### Session 008 — Incident console built, and its render check

- **What was built.** `backend/app/api/incident_api.py` (FastAPI) is a **read-only** control plane: it parses `evidence/gitlab-ci-lifecycle-artifacts/`, `evidence/gitlab-pipeline-2932808602.json` and the Duo session record into typed models (`Incident`, `Detection`, `SafetyDecision`, `Approval`, `VerificationResult`, `DuoSession`, `TimelineEvent`) and serves `GET /healthz`, `GET /api/incidents`, `GET /api/incidents/{id}` plus the built console at `/`. `dashboard/` is React + TypeScript + Tailwind with six views; the Overview shows the p95 ratio and error rate per window against the baseline, Approval centre renders all 18 gate checks, and Verification shows why `independent=True` is provable (window starts after `executed_at`).
- **Two deliberate honesty mechanisms, not decorations.** A missing or unparseable artifact is named in `missing_artifacts` instead of being defaulted, and every incident response carries the fixed `fault_nature` (v1 and v2 share one image digest; the fault is injected deployment configuration) and `code_rollback_note` (a code rollback does not restore deleted data) so no consumer can present the incident as something it was not.
- **Persistence decision.** `ROLLBACKIQ_BUILD.md` §9 permits SQLite "unless a simpler proven design suffices"; here it does. The artifacts *are* the record, and a second copy could only drift from what the pipeline wrote. Recorded in the README rather than silently skipped.
- **Tests: 90 → 98 passed**, the 8 new ones covering the API's real behaviour: detection parsed from the committed artifact, all 18 safety checks present, the approver and proposal hash, `independent=True` only with a post-rollback window, and `missing_artifacts` naming a file the API cannot read.
- **The render check is the point.** `scripts/screenshot_dashboard.py` drives Chromium over every view, waits for real content in each, and **exits non-zero on any uncaught page error or `console.error`** — so "it built" is never mistaken for "it renders". Result: six views captured, **no page or console errors**, one fix applied during the pass (a React type import and a missing tag in `Report.tsx`).
- Console screenshots: `docs/screenshots/{overview,timeline,investigation,approval-centre,verification,incident-report}.png`.
- Tests **98 passed**; next: five diagrams, the documentation set, the video.

### Session 007 — Custom Duo flow executes end-to-end; its audit corrects the record

- **The §5 obligation is met for real.** The project's flow trigger (`AiFlowTrigger` `3013795`, event types mention/assign) starts sessions when the flow's service account is mentioned. Session `9288744` reached `FINISHED` and posted an investigation note to issue #2.
- **Why earlier trigger sessions failed.** Sessions `9283600` and `9288721` died with `Error: KeyError`. Root cause, proven by reading the consumer's pinned version back: `aiCatalogFlowUpdate` **silently ignores `definition` unless `versionBump` and `release` are supplied** — no new version, `errors: []`. Every session had therefore been running the *original* revision. `scripts/duo_provision_catalog.py` now passes `versionBump: "PATCH"` + `release: true`, prints the read-back, and exits non-zero when the stored content differs from the repository.
- **The flow YAML also needed real fixes** (server-validated): `OneOffComponent` exposes only `tool_responses`/`tool_calls`/`execution_result` — not `final_answer` — so both steps are `AgentComponent`s; inline prompts need `unit_primitives: []` and `placeholder: history`; and `params` must be a **string or list of strings**, so the documented mapping example is rejected by this build and was removed. `project_id` is passed to every GitLab-API component and each prompt ends with an explicit stop instruction.
- **The flow's first successful audit found a real error in my own record.** It refused to accept "recovery verified" without a readable artifact and flagged mismatched ratios, hash and digest. Confirmed: the issue and this file had mis-transcribed `6.31x/6.43x`, `sha256:211383c1…` and `d17d4968d76a71c9`. Corrected to the artifact values `8.59x/8.75x`, `sha256:72a3cc17…` (the same digest as v2 — injected config, one image) and `70f980983c184108`, in both the issue body and here; a reconciliation comment (note `3990226434`) is on the issue and `evidence/gitlab-pipeline-2932808602.json` was corrected with its `source` field set.
- **New tooling:** `scripts/duo_trigger_flow.py` — fires the mention trigger, polls the platform's own session record, and writes the whole observation to `evidence/duo-flow-trigger-session.json`; it exits non-zero unless the session is `FINISHED`.
- Tests: **90 passed**. Guard: clean (148 units). Next: dashboard, diagrams, video.

### Session 006 — Real OpenTelemetry export to GitLab Observability
- User enabled Observability for the workspace group (144345494) and supplied the collector endpoints (`https://144345494.otel.gitlab-o11y.com:14318` for OTLP/HTTP, `:14317` for gRPC).
- Spike result: a trace POSTed to `:14318/v1/traces` returned **HTTP 200 with `{"partialSuccess":{}}`**, i.e. accepted with nothing rejected, both with and without an auth header (no secret is needed in this configuration).
- Implemented `demo/service/otel_setup.py` (OTLP/HTTP exporter, GitLab resource attributes, FastAPI instrumentation, guarded so telemetry can never break the workload) and wired it into `demo/service/app.py` with `/otel`, `/admin/flush-telemetry`, and release/fault attributes on each span. Added `demo/otel.env.example`, Compose passthrough, pinned OTel deps, `scripts/otel_export_evidence.py` and a manual `telemetry-spike` CI job.
- Verified: `scripts/otel_export_evidence.py` against the real collector → **64 spans accepted, 0 failures** from 12 real requests, recorded in `evidence/otel-export-spike.json`; with no collector configured the workload serves normally and `/otel` reports `telemetry_enabled: false`. Test suite now **57 passed**. `.gitlab-ci.yml` validated by GitLab's own CI lint API (`valid: true`).
- Verified **on a GitLab runner**, not just locally: manual job `telemetry-spike` (job `17073367648`, pipeline `2932245570`) was played on `k8s.saas-linux-small-amd64.runners-manager.gitlab.com/default`, succeeded in 21.5 s, and its artifact reports **64 spans exported, 0 failures** to the group collector. Because the job runs in CI, its resource attributes carry the real pipeline context: `service.version` = `8869c5766202042b362b641a44a5231fcd0452ea` (from `CI_COMMIT_SHA`) and `gitlab.project.name` = `showcase` (from `CI_PROJECT_NAME`). Evidence: `evidence/otel-export-ci.json`, `evidence/gitlab-job-telemetry-spike.log`.
- Not verified: that the spans render in the GitLab Observability UI. There is no public trace-query REST API (probes at `/api/v4/projects/87424071/observability*` all return 404), so collector acceptance is the strongest evidence obtainable from this host.
- Note for later: the group's Observability page mentions an **MCP server** endpoint that is being provisioned. That is directly relevant to the GitLab MCP requirement — check it when it appears.

### Session 005 — Showcase project adopted, CI green in it
- Completed: force push refused by GitLab's protected-branch rule and worked around properly with a non-force merge; local `main` fast-forwarded to the merged commit; `showcase` made `origin` with the dedicated project kept as `rollbackiq-project`; showcase pipeline 2932220957 captured as evidence.
- Bug found and fixed this session: the `pre-push` hook built an invalid revision range when the remote tip did not exist locally (first push to an unrelated remote), aborting the push instead of checking it. It now scans every commit reachable from the local tip in that case. Verified against a throwaway unrelated remote: a footer commit was still blocked, while a clean push was allowed.
- Next exact action: the Duo capability spike on project 87424071 (showcase), capturing the real execution evidence.

### Session 004 — Repository pushed, first real pipeline green
- Completed: project `rollbackiq` (id 87449782) created in the workspace group; `main` pushed with the token supplied per-command only (verified absent from `.git/config` and from the remote URL); upstream set to the credential-free `origin`; first pipeline 2932203567 succeeded with the `attribution-guard` job on a shared runner; evidence captured by `scripts/capture_pipeline_evidence.py`.
- Notable: the `pre-push` hook scanned all 5 commits during the real push, and CI independently scanned 35 files plus the same 5 commit messages — local and server-side enforcement both observed.
- Errors made and fixed: (1) the earlier project-creation attempt failed with 403 `insufficient_granular_scope` and my parser reported it as empty output because it checked `message` while the API returns `error`; corrected by printing HTTP status and the raw body; (2) `git push origin main` failed with `could not read Username` because the credential-free remote cannot authenticate — fixed with an env-reading credential helper; (3) a pipeline poll read the previous pipeline because GitLab creates the new one a few seconds after the push, so polls now query by commit sha.
- Next exact action: run the Duo capability spike on project 87449782 and capture the execution evidence.

### Session 003 — GitLab access established
- Completed: token identity and permissions measured; workspace group and project identified; Duo flows confirmed enabled; `glab` authenticated; git-over-HTTPS auth verified read-only; README, MIT LICENSE and GitLab findings written.
- Decisions: the RollbackIQ repository will live in a **new** project `rollbackiq` inside the workspace group (chosen by the user), which matches Path A "start fresh"; the token will be passed per-push and never stored in `.git/config` or committed.
- Tests: 51 pytest tests still passing; no GitLab writes were made (verified: the workspace lists only `showcase`, and it still holds only its initial commit).
- Blockers: token lacks `Project: Create` (HTTP 403), so the new project cannot be created from this session yet.
- Next exact action: create/push `rollbackiq` once that permission exists, then watch the first pipeline.

### Session 002 — Phase 0 spike and Phase 1 environment
- Completed: capability matrix and blocker identification; demo workload with real metrics and fault injection; Docker image + Compose stack; detector, state machine, safety gate, verifier, collector; 51 tests; measured end-to-end regression and verified recovery.
- Decisions: measurement comes from the observer's own probes rather than the service's self-report; unknown migration compatibility is treated as unsafe; unknown rollback time means independence cannot be claimed; a failed git call is a hard error.
- Tests: 51 passed; demo regression run reproduced twice; Docker artifacts built and exercised.
- Blockers: GitLab project/token absent, so the Phase 0 gate and all GitLab integration remain unverified.
- Next exact action: push to the GitLab project once credentials exist, then run the Duo spike.

### Session 001 — Attribution guard
- Completed: repository initialised, attribution guard (scanner, hooks, installer, CI job) with positive/negative/bypass/broken-environment verification.
- Blockers: no `glab`/Duo tooling or GitLab remote at that time.

## Final checkpoint (session 008 close)
- Tree clean after `30f03d1`; the suite is **98 passed** locally and **98 passed** in the `test:pytest` image; the attribution guard is clean over **210 units**.
- Deliverables this session: the console (`dashboard/` + `backend/app/api/`), five diagrams (`docs/diagrams/`), the documentation set, the `test` stage, `scripts/demo_lifecycle_local.sh`, and `demo/videos/rollbackiq-demo.mp4`.
- Open: the final submission take (approval played by hand in the GitLab UI) and the push decision. Both need the user.

## Recovery procedure

At each manually resumed session:
1. Read all three root/progress Markdown files.
2. Recall `rollbackiq` memories from port 8888.
3. Inspect working tree, latest commits, active jobs, and actual source.
4. Reconcile this file with reality.
5. Continue the first unfinished action without restarting completed work.
6. Checkpoint every 15 minutes and before expiration if possible.

**Session expiry is a pause, not project completion.**
