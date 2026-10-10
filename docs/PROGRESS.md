# RollbackIQ — Development Progress

> Persistent checkpoint for Freebuff sessions (~1 hour). Update **at least every 15 minutes** and after milestones.  
> Hindsight bank: **`rollbackiq`** | Hindsight API port: **8888**

## Current phase
**Phases 1, 3 and 4 now have real deployment control: the GitLab pipeline deploys, detects a regression, requires a human approval, runs a safety-gated rollback and verifies recovery independently.** OpenTelemetry is wired into both the workload and the control plane, and the telemetry export is proven from a GitLab runner. Two blockers remain and both need the user: the **Duo capability spike is still unrun** (the Phase 0 gate — `/home/azureuser/.local/bin/duo` is installed and real, but `duo run` needs a PAT with `api` scope and no token is present in this session), and **nothing is pushed** since my last commits, for the same reason. Everything committed so far is verified locally.

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
The exact next command, once a PAT with `api` scope is available in `GITLAB_TOKEN`:

```bash
cd /home/azureuser/rollbackiq && export GITLAB_TOKEN=... && export ORIGIN=$(git remote get-url origin)
export GITLAB_TOKEN=... && export REMOTE=$(git remote get-url origin)
# 1. Duo capability spike (the Phase 0 gate) — the CLI is installed and genuine:
duo run --goal "Summarise what the RollbackIQ pipeline verifies about a rollback" \
  --flow-config-id developer --output-format json \
  --gitlab-project-path gitlab-ai-hackathon/transcend-october-2026/43178176/showcase \
  --duo-workflow-project-id 87424071 2>/dev/null > evidence/duo-run.json
# 2. Then push and watch the new pipeline (all jobs above are new and unproven on a runner)
git push origin main && git push rollbackiq-project main
```

Known uncertainties to check on that first pipeline, in order: whether `docker:27-dind` is permitted on the shared runner; whether the container registry accepts the image; whether `apk add python3 py3-pip` + `pip install --break-system-packages -r backend/requirements.txt` works on the `docker:27` Alpine image; and whether `GITLAB_USER_LOGIN` is populated for the manual `approval:grant` job. Report whichever it actually is rather than assuming.

The Duo spike is the Phase 0 gate and remains the top priority; the deploy/rollback jobs are already built and locally verified.

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
Deterministic healthy/faulty demo workload with **real measured regression**: v2 was detected at 6.72x baseline p95 and ~8.7% errors, then recovery was verified from independent post-rollback observations. Phase 1 gate (repeatable observed regression) is met.

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
- [x] Unit, negative and integration tests (51 passing)
- [ ] Real GitLab Duo agent/flow execution
- [ ] Real GitLab CI/CD deploy and rollback jobs
- [ ] Evidence-based investigation via Duo with GitLab context
- [ ] Control-plane API and SQLite persistence
- [ ] Dashboard
- [ ] Diagrams, documentation set, demo video

## Work in progress
Nothing left running. `.venv` is installed locally; the demo workload is not running (Compose stack was torn down after verification).

## Last successful tests
`.venv/bin/python -m pytest` → **51 passed** in ~17s. Covers:

| Area | Tests |
| --- | --- |
| State machine | happy path, illegal transitions, denial escalates instead of executing, history/actor recording |
| Detector | empty/insufficient windows, unverified or missing baseline, environment mismatch, sustained-window requirement, cooldown suppression, counter reset, error-rate-only breach |
| Safety gate | fully authorized rollback allowed; 15 veto cases (missing/denied/expired/out-of-scope/over-age approval, non-human actor, environment, unknown target, not known-good, target equals current, migration unknown/incompatible, missing/duplicate idempotency key, hold/escalate actions) |
| Verifier | independent window required, unknown rollback time refused, reused incident data refused, wrong release, insufficient samples, short stabilization window, latency/error recovery limits |
| Detection chain (integration) | real requests through the demo app: healthy baseline → faulted v2 detected → v1 restored → recovery verified |

### Measured end-to-end run (`.venv/bin/python scripts/demo_regression.py`)
Raw record: `evidence/phase1-regression.json`. Reproduced twice with the same class of result.

| Phase | Measurement |
| --- | --- |
| Healthy v1 baseline | 150 samples, 0 errors, p95 35.6 ms |
| Faulty v2 windows | 11.3% then 8.7% error rate; p95 238.9 ms = **6.72x** baseline |
| Detection | breached P95_LATENCY and ERROR_RATE after the second sustained window; **time to detect 7.72 s** |
| Rollback | 0.51 s — **a local process restart standing in for the GitLab CI job, which is not implemented** |
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
- None for GitLab access: the token was upgraded to full access, project creation returns 201, and pushes to the protected `showcase` `main` work as ordinary fast-forwards.
- The remaining unverified area is **Duo execution** (flows are enabled on both projects but no flow has been invoked yet) and the GitLab CI/CD deploy/rollback jobs, which are not written yet.
- The duplicate `rollbackiq` project still exists; deleting it needs the user's explicit approval because project deletion is not reversible.
- `glab` is usable only through the container image here; a host install would need the prebuilt binary from the official releases page.

## Next three actions
1. Run the Duo capability spike on the showcase project (87424071) — the smallest supported custom agent or flow, invoked for real, with the execution evidence captured. This is the remaining Phase 0 gate. Also check whether the group's Observability **MCP server** endpoint has finished provisioning, since that is the sanctioned route for the GitLab MCP requirement.
2. Build the CI/CD deploy and rollback jobs so recovery runs through GitLab CI instead of the local restart stub, then re-measure the full detect-to-verified-recovery timeline including pipeline time.
3. Wire the control plane (FastAPI + SQLite) to GitLab issues/incidents so evidence links land in a real GitLab incident record.

Optional but cheap hackathon bonus noted from the onboarding issue: the workspace group supports its own observability stack via **Observe → Observability configuration → Enable Observability**. Not enabled and not required to submit; do not claim it unless it is turned on and observed.

Resolved this session: the token now has full access, project creation returns 201, `origin` is the showcase project and pushes to it succeed without force (protected `main`, non-force merge path).

## Exact next command
```bash
cd /home/azureuser/rollbackiq && .venv/bin/python -m pytest && git log --oneline -5
```

## Latest Git commit
`9ddce6a` "Refresh the checkpoint with the final commit and workspace observability note" — the commit that contains this line is a documentation-only follow-up on top of it, because a file cannot record its own hash. At the time of writing, local `main`, `origin/main` and `rollbackiq-project/main` were all at `9ddce6a` with the tree clean, and both pipelines for it were green.

## Hindsight synchronization status
Bank `rollbackiq` is active; Phase 0 findings, the Phase 1 verified results and the two fixed defects are retained this session. One earlier memory may still be extracting; re-check with `hindsight list_documents`. No secrets are stored.

## Coding standard: no attribution footers

Rule: commits, merge requests, issues, documentation, source files, diagrams, release notes and demo scripts never carry an AI attribution footer, trailer or assistant signature.

- `scripts/check_no_attribution.sh` is the single source of truth: modes `files`, `staged`, `commit-msg <file>`, `range <rev>`, `patterns`.
- Versioned hooks in `scripts/git-hooks/` call it. Run `scripts/install-git-hooks.sh` after a fresh clone: it sets `core.hooksPath` in the repository's local config only.
- `AGENTS.md` and the scanner itself are excluded from file scans (one quotes the prohibited examples as policy, the other defines the patterns); both exclusions are printed on every run.
- `git commit --no-verify` bypasses the message hook, which is why the `pre-push` hook and the `attribution-guard` CI job exist.

## Evidence links
- `evidence/phase1-regression.json` — raw windows, detection decision, verification result and timings.
- GitLab pipeline / Duo session / incident issue links are still to be created (blocked on Phase 0 access).

## Session log

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

## Recovery procedure

At each manually resumed session:
1. Read all three root/progress Markdown files.
2. Recall `rollbackiq` memories from port 8888.
3. Inspect working tree, latest commits, active jobs, and actual source.
4. Reconcile this file with reality.
5. Continue the first unfinished action without restarting completed work.
6. Checkpoint every 15 minutes and before expiration if possible.

**Session expiry is a pause, not project completion.**
