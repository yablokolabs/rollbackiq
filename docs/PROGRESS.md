# RollbackIQ — Development Progress

> Persistent checkpoint for Freebuff sessions (~1 hour). Update **at least every 15 minutes** and after milestones.  
> Hindsight bank: **`rollbackiq`** | Hindsight API port: **8888**

## Current phase
Phase 1 complete and verified locally. Phase 2 (detection/investigation service, GitLab context, Duo flow) is next, blocked at the GitLab step pending project access.

## Current task
Phase 0 is partially blocked: the local environment and the demo regression loop are done, but GitLab Duo and GitLab CI/CD cannot be verified without a GitLab project and credentials.

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

### Blocker requiring a human (cannot be worked around locally)
1. A GitLab hackathon project and its namespace/URL.
2. A Personal Access Token (or equivalent) with API scope, supplied as a **protected environment variable or CI variable** — never pasted into the repo, never printed, never stored in Hindsight.
3. Confirmation of whether the Duo Agent Platform (custom agents/flows) is available on that account/plan, since the hackathon prerequisite is genuine Duo use.

Until (1) and (2) exist, GitLab CI/CD deploy and rollback jobs and any Duo invocation cannot be verified, and per the specification's gate the architecture must not be built as if they were.

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
- No GitLab project, namespace, remote or token (see Phase 0 matrix). This blocks the Phase 0 gate, GitLab CI/CD jobs, and any Duo execution.
- Duo availability on the account/plan is unknown.
- `glab` is usable only through the container image here; a host install would need the prebuilt binary from the official releases page.

## Next three actions
1. Once the GitLab project and token exist: add the remote, push `main`, confirm the `attribution-guard` job runs on a real pipeline, and record the pipeline URL as evidence.
2. Run the Duo capability spike on that project: create the smallest supported custom agent or flow, invoke it, and capture the execution evidence (job log, session, artifact). This is the Phase 0 gate.
3. Then start Phase 2: control-plane API and SQLite persistence, GitLab context collection (commits, pipeline, deployment metadata), and wiring the existing detector into an evidence-producing incident investigation.

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
