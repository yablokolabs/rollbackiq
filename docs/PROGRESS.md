# RollbackIQ — Development Progress

> Persistent checkpoint for Freebuff sessions (~1 hour). Update **at least every 15 minutes** and after milestones.  
> Hindsight bank: **`rollbackiq`** | Hindsight API port: **8888**

## Current phase
Phase 0 — Bootstrap and GitLab Duo capability verification.

## Current task
Verify GitLab hackathon project access, GitLab Duo Agent Platform capabilities, GitLab CLI/MCP integration, and execute a minimal real Duo custom agent/flow. (Not started: no GitLab remote or CLI on this host yet — see blockers.)

## Last completed milestone
Attribution guard enforced from local Git hooks and CI (commit messages, files, and pushes are all covered), with the guard tooling itself verified against positive and negative cases.

## Completed features
- [x] Repository initialized on branch `main` with an attribution guard that blocks AI attribution footers/trailers in commits, files and pushes
- [ ] GitLab hackathon namespace/project verified
- [ ] Real Duo agent/flow execution demonstrated
- [ ] Healthy/faulty service implemented
- [ ] Metrics baseline and regression detection
- [ ] Evidence-based investigation
- [ ] Human approval gate
- [ ] Controlled GitLab rollback
- [ ] Independent recovery verification
- [ ] Incident reporting
- [ ] Dashboard
- [ ] End-to-end tests
- [ ] Demo and submission

## Work in progress
Nothing in progress. Next session starts Phase 0 capability verification.

## Uncommitted changes
None at the time of writing; `scripts/check_no_attribution.sh` and `.gitlab-ci.yml` are committed after verification.

## Last successful tests
Attribution guard suite, run on this host (Git Bash-style bash 5.x, git 2.43.0) and re-run inside `alpine:3.20` containers:

| Case | Command | Expected | Observed |
| --- | --- | --- | --- |
| Clean tree | `scripts/check_no_attribution.sh files` | pass | `clean — 8 unit(s) scanned`, exit 0 |
| Footer in commit message | `git commit -m "…"` with an assistant trailer | blocked | exit 1, `HEAD` unchanged |
| Footer in a staged file | `git add` a file containing an assistant marker, then commit | blocked | exit 1, `HEAD` unchanged |
| Clean commit | `git commit --allow-empty -m "Add recovery verifier stage"` | allowed | exit 0 |
| Message-only footer | `scripts/check_no_attribution.sh range HEAD` | fail | `FAILED — 1 violation`, exit 1 |
| Bypass commit then push | `git commit --no-verify` a footer, then `git push` to a throwaway bare remote | push blocked | exit 1, remote refs unchanged |
| Broken git environment | guard run where git refuses the repo | **error** | exit 2 with the git cause, no "clean" result |
| CI job, clean repo | `.gitlab-ci.yml` script block in `alpine:3.20` | pass | exit 0, 1 commit message scanned |
| CI job, footer commit | same block against a repo copy with a footer commit | fail | exit 1 |

Also confirmed by that last pair: `files` mode alone reports clean when a footer exists only in a commit message, which is why the CI job scans commit messages as well as files.

## Current failures
None outstanding in the guard.

Fixed during this work: the scanner originally let a failed git call fall through to a "clean" result over zero scanned units (a false pass). A failed git command is now a hard error (exit 2) with the git cause printed.

## Known blockers
- `glab` / GitLab Duo CLI are not installed on this host (`which glab glab-duo duo` returns nothing), so GitLab access and Duo capability verification cannot start yet.
- No GitLab project or remote is configured; the repository is local only.
- Hindsight bank `rollbackiq` did not exist and was created this session; the project memories below are the first entries.

## Next three actions
1. Provision the GitLab hackathon project and a remote for this repository, then push `main` so the `attribution-guard` CI job runs on a real pipeline.
2. Install/verify the GitLab CLI and Duo tooling (`glab`, Duo CLI, MCP) as the first Phase 0 capability spike, and record exactly what works.
3. Run a minimal real GitLab Duo agent/flow and capture evidence (job log, Duo session, artifact), then wire it into the release/investigation design.

## Exact next command
```bash
pwd && git log --oneline -5 && command -v glab || echo "glab missing"
```

## Latest Git commit
`e83b7a1` Initialize RollbackIQ scaffold with the attribution guard

## Hindsight synchronization status
Bank `rollbackiq` created this session; the attribution guard decision, the false-pass bug and fix, and the Phase 0 blockers were retained. No secrets stored.

## Coding standard: no attribution footers

Rule: commits, merge requests, issues, documentation, source files, diagrams, release notes and demo scripts never carry an AI attribution footer, trailer or assistant signature.

- `scripts/check_no_attribution.sh` is the single source of truth and has four modes: `files`, `staged`, `commit-msg <file>`, `range <rev>`, plus `patterns` to print the rule set.
- The versioned hooks in `scripts/git-hooks/` (`commit-msg`, `pre-commit`, `pre-push`) call the scanner. Run `scripts/install-git-hooks.sh` after a fresh clone: it sets `core.hooksPath` in the repository's local config only (global Git config is never modified).
- `AGENTS.md` is excluded from file scans because it quotes the prohibited examples as policy, and the scanner excludes itself because it defines the patterns. Both exclusions are printed on every run rather than skipped silently.
- `git commit --no-verify` bypasses the message hook, which is why `pre-push` and the `attribution-guard` CI job exist as backstops.
- The CI job in `.gitlab-ci.yml` has not run on a GitLab runner yet (no remote); its exact script block was executed in `alpine:3.20` locally with the results above.

## Evidence links
Add actual GitLab pipeline, Duo session, issue, metric snapshot, test report, and demo links as created.

## Session log

### Session 001 — Attribution guard
- Started: repository contained only `AGENTS.md`, `ROLLBACKIQ_BUILD.md` and this progress file; no Git repository.
- Last checkpoint: end of session 001.
- Completed: repository initialized (`main`), attribution guard scanner + versioned hooks + installer, `.gitlab-ci.yml` guard job, guard test suite (positive, negative, bypass, broken-git, CI-equivalent).
- Decisions: one scanner shared by hooks and CI rather than duplicated patterns; git failures are fatal rather than fallbacks; hooks live in `scripts/git-hooks/` wired through repo-local `core.hooksPath` so they are versioned.
- Tests: see the table above.
- Blockers: no `glab`/Duo tooling and no GitLab remote.
- Hindsight memories written/verified: yes (bank `rollbackiq`).
- Next exact action: provision the GitLab project/remote and push `main`, then start the GitLab Duo capability spike.

## Recovery procedure

At each manually resumed session:
1. Read all three root/progress Markdown files.
2. Recall `rollbackiq` memories from port 8888.
3. Inspect working tree, latest commits, active jobs, and actual source.
4. Reconcile this file with reality.
5. Continue the first unfinished action without restarting completed work.
6. Checkpoint every 15 minutes and before expiration if possible.

**Session expiry is a pause, not project completion.**
