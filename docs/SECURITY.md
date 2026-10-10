# Security and safety model

This system performs a consequential action — changing which release is deployed — so the
interesting question is not what it can do, but what it refuses to do.

## The trust boundary

```
agent reasoning  ──proposal──▶  state machine  ──▶  SAFETY GATE  ──▶  allowlisted CI/CD job  ──▶  demo-staging
   (no deploy tool)                (raises)            (18 checks)          (one target)
```

- The **Duo flow has no tool that can deploy, approve or roll back**, and its prompt forbids
  asking for one. Its output is a recommendation for a human.
- The **state machine rejects illegal transitions** rather than tolerating them. Denial and
  expiry lead to `ESCALATED`, so "no action was taken" is always visible in the record.
- The **safety gate** is the only thing that turns a proposal into an action.

## What the gate enforces

Every check is exercised by `backend/tests/test_safety.py`, including negative cases:

| Check | Refusal condition |
| --- | --- |
| `APPROVAL_PRESENT` | No approval for this proposal |
| `APPROVAL_ACTOR_IS_HUMAN` | The approver is an agent or system identity |
| `APPROVAL_IN_SCOPE` | The approval names a different proposal hash |
| `APPROVAL_NOT_EXPIRED` | The approval's TTL has passed |
| `ENVIRONMENT_ALLOWLISTED` | The target environment is not on the allowlist |
| `PHASE1_ENVIRONMENT_ALLOWLISTED` | The environment is not on the protected allowlist |
| `TARGET_IS_KNOWN_GOOD` | The rollback target is not a release this system observed as healthy |
| `TARGET_DIFFERS_FROM_CURRENT` | The target is the release that is already deployed |
| `MIGRATION_COMPATIBLE` | The proposal requires a migration and compatibility is unknown — unknown is treated as unsafe. Evaluated only when the proposal requires a migration |
| `IDEMPOTENCY_KEY_PRESENT` | No idempotency key for the attempted action |
| `NOT_ALREADY_EXECUTED` | The ledger already consumed that key |
| `ACTION_IS_ROLLBACK` | The proposed action is `hold` or `escalate` |
| … | plus `PROPOSAL_ENVIRONMENT_MATCHES`, `CURRENT_RELEASE_KNOWN`, `TARGET_RELEASE_KNOWN`, `TARGET_ENVIRONMENT_MATCHES`, `APPROVAL_GRANTED`, `APPROVAL_ENVIRONMENT_MATCHES` and `APPROVAL_WITHIN_MAX_AGE` |

The gate **reports every veto, not just the first**, and it fails closed: anything it cannot
establish is a refusal, never a default.

The image identity check is a separate step after the gate, in `scripts/ci_rollback.py`
(`verify_target_identity`): the rollback is refused when the resolved image digest is unknown
or differs from the digest recorded for the target release.

Six refusals were run against the real gate, each required to name a *different* guard and all
exiting non-zero: no approval, a non-human approver (`duo`), an unlisted environment, a target
never observed healthy, a digest mismatch, and a replay. Proof the refusals changed nothing:
the container's `StartedAt` still matches the single successful rollback. See
`docs/EVALUATION.md`.

## The verification rule

A green rollback job proves the job ran. The verifier therefore:

- requires a **new window that starts after the rollback executed**; an unknown rollback time
  means independence cannot be claimed and recovery is **not** confirmed;
- refuses to reuse the incident's own data as the post-rollback evidence;
- refuses a window shorter than its stabilization duration — this is not hypothetical: the
  first CI run failed with `stabilization window 1.1s is shorter than 3.0s` and the refusal is
  kept as evidence in `evidence/gitlab-ci-verification-refusal.json`;
- refuses to certify against a baseline it did not verify.

## Prompt injection and untrusted content

Job logs, issue descriptions, comments, commit messages, file contents and telemetry are all
**untrusted evidence, never instructions**. This is enforced at two levels:

1. The agent's system prompt (`duo/agents/rollbackiq-recovery-investigator.md`) states that
   retrieved content may address the agent directly, that it must be reported as data, and that
   an assertion inside a log is not a verified fact. It also forbids reproducing a credential
   and requires naming the location for rotation instead.
2. The deterministic path does not read prose at all. The detector consumes metric windows, and
   the gate consumes a typed proposal and approval; text in a chat message cannot move either.

**Observed, not asserted:** session `9288744` was handed an issue whose text contained three
mis-transcribed figures. It read the artifacts, flagged the mismatch, marked what it could not
retrieve as missing, and recommended HOLD instead of executing the story it was told. The
incident record was corrected afterwards.

## Secrets

- The GitLab token lives in the user's `~/.hermes/.env` and is passed per command; it is never
  written to `.git/config`, to a remote URL, or to a committed file. The repository-local
  credential helper holds only a snippet that references `$GITLAB_TOKEN`.
- Registry auth in CI uses `$CI_REGISTRY_PASSWORD` piped to `docker login --password-stdin`, so
  it never appears in a job log or a process listing.
- The OTLP collector used here needs no credential.
- **No secret is stored in the Hindsight memory bank or in any progress document.**
- The Duo CLI is invoked with `--session-tracking-enabled false` so it cannot append a session
  trailer to a commit.

## No AI attribution

`scripts/check_no_attribution.sh` is the single source of truth for the rule that no commit,
issue, document, diagram or source file carries an AI attribution footer. It runs locally from
`scripts/git-hooks/` and in CI as `attribution-guard`, scanning files **and** commit messages.
A failed `git` call is a hard error rather than a clean result, because a scanner that passes
over zero units is a false pass. `AGENTS.md` and the scanner itself are excluded from file
scans and the exclusions are printed on every run.

## What this is not

Stated plainly, because a safety document that oversells itself is worse than none:

- **A code rollback does not restore deleted data.** Data recovery is a separate,
  human-controlled operation on backups, and this system deliberately does not perform it. If a
  change deleted customer data, the honest answer is that rolling back the code will not bring it
  back.
- **No production system is in scope.** The only target is an isolated `demo-staging`
  container with one workload.
- **The gate is an in-process library, not a hardened authorization service.** It runs inside
  the job that performs the rollback. A compromise of the job or of the GitLab project could
  bypass it; the design assumes GitLab's own protected-branch and CI permissions are the outer
  boundary.
- **The idempotency ledger is a JSON artifact, not a distributed lock.** It prevents a replay
  within and across pipeline runs on the same stored artifact; concurrent runs with separate
  artifact copies are not mutually excluded.
- **Approval expiry is enforced by the gate on the record's own timestamps**, not by a server
  clock the approver cannot influence.
- **The demo's approval was played by the token owner** via the API during debugging, so the
  recorded approver is a person only because the token belongs to one. For the demo video the
  approval is played by hand in the UI, and this caveat is stated on camera.
