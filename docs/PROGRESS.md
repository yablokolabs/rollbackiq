# RollbackIQ — Development Progress

> Persistent checkpoint for Freebuff sessions (~1 hour). Update **at least every 15 minutes** and after milestones.  
> Hindsight bank: **`rollbackiq`** | Hindsight API port: **8888**

## Current phase
**Phase 0 GitLab bootstrap complete.** The RollbackIQ repository exists in the hackathon workspace, `main` is pushed, and the first real GitLab pipeline ran green: job `attribution-guard` succeeded on a GitLab.com shared runner, scanning 35 files and 5 commit messages. Next: the Duo capability spike (the Phase 0 gate), then Phase 2. Phase 1 remains complete and verified locally.

## GitLab CI evidence (first real pipeline)

| Item | Value |
| --- | --- |
| Project | `gitlab-ai-hackathon/transcend-october-2026/43178176/rollbackiq` (id **87449782**), public |
| Duo on the project | `duo_foundational_flows_enabled = true`, `duo_remote_flows_enabled = true` |
| Pipeline | id **2932203567**, status **success**, ref `main`, sha `796df35a` |
| Job | id **17073050784**, `attribution-guard`, stage `verify`, status **success**, **8.93 s** |
| Runner | `k8s.saas-linux-small-amd64.runners-manager.gitlab.com/default` (GitLab.com shared runner, docker+machine executor) |
| What the job proved | `attribution guard: clean — 35 unit(s) scanned` for files, and `attribution guard: clean — 5 unit(s) scanned` after `(scanned 5 commit message(s) in range: 796df35…)` |
| Captured record | `evidence/gitlab-pipeline-2932203567.json` via `scripts/capture_pipeline_evidence.py` |

Pipeline URL: https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43178176/rollbackiq/-/pipelines/2932203567

## Current task
Complete the GitLab bootstrap: create the project in the hackathon workspace, push `main`, and get the first real pipeline (and the `attribution-guard` job) to run as evidence. Then the Duo capability spike.

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

The URL originally supplied (`…/2870391/showcase`) returns 404: the numeric segment in that link is not this user's id. The correct workspace project is the `43178176` one above.

## Last completed milestone
Deterministic healthy/faulty demo workload with **real measured regression**: v2 was detected at 6.72x baseline p95 and ~8.7% errors, then recovery was verified from independent post-rollback observations. Phase 1 gate (repeatable observed regression) is met.

## Phase 0 capability matrix (observed on this host, 2026-10-09)

| Capability | Observed result | How it was checked |
| --- | --- | --- |
| `glab` CLI | Works, version 1.122.0, but only via the documented `gitlab/glab` container image; not installed on the host | `docker run --rm --entrypoint glab gitlab/glab --version` |
| GitLab authentication | **None configured**; API returns 401 | `docker run --rm --entrypoint glab gitlab/glab auth status` |
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
- None for GitLab access: the token was upgraded to full access and project creation now returns 201. The remaining unverified area is **Duo execution** (flows are enabled but no flow has been invoked yet) and GitLab CI/CD deploy/rollback jobs, which are not written yet.
- `glab` is usable only through the container image here; a host install would need the prebuilt binary from the official releases page.

## Next three actions
1. Get `Project: Create` on the token (or an empty `rollbackiq` project created manually), then create/push: `git remote add origin …/43178176/rollbackiq.git` and push `main`.
2. Confirm the `attribution-guard` job runs on the first real pipeline and record the pipeline URL and job log as evidence.
3. Run the Duo capability spike on that project — the smallest supported custom agent or flow, invoked for real, with the execution evidence captured. This is the Phase 0 gate.

## Exact next command
```bash
cd /home/azureuser/rollbackiq && .venv/bin/python -m pytest && git log --oneline -5
```

## Latest Git commit
`dece1cf` Record the exact Hindsight synchronization state, plus this session's Phase 0/Phase 1 commit.

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

### Session 004 — Repository pushed, first real pipeline green
- Completed: project `rollbackiq` (id 87449782) created in the workspace group; `main` pushed with the token supplied per-command only (verified absent from `.git/config` and from the remote URL); upstream set to the credential-free `origin`; first pipeline 2932203567 succeeded with the `attribution-guard` job on a shared runner; evidence captured by `scripts/capture_pipeline_evidence.py`.
- Notable: the `pre-push` hook scanned all 5 commits during the real push, and CI independently scanned 35 files plus the same 5 commit messages — local and server-side enforcement both observed.
- Errors made and fixed: the earlier project-creation attempt failed with 403 `insufficient_granular_scope` and my parser reported it as empty output because it checked `message` while the API returns `error`; corrected by printing HTTP status and the raw body.
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
