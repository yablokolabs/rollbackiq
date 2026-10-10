# Incident runbook

For the person on call when the `deploy:regressed` job, or a real regression in `demo-staging`,
opens an incident. Each step names the job or script that does the work and the file that
proves it. The scope is the isolated `demo-staging` environment only.

**Before you start, know the limit:** a rollback changes which release is deployed. It does
not restore deleted data. If the regressed release wrote or deleted data, start the separate,
human-controlled backup procedure. This system does not do it.

## 1. Confirm that the detection is real

| Look at | Where |
| --- | --- |
| Detection verdict, breaches, p95 ratio | `evidence/ci-detection.json` (artifact of `deploy:regressed`) |
| The measured windows | `evidence/faulty-window-N.json` |
| The healthy baseline | `evidence/baseline-window.json` (artifact of `deploy:staging`) |

The detector fires only after a sustained breach: p95 latency above 3.0x the baseline, or an
error rate above 5%, on consecutive windows with enough samples. If `triggered` is `false`,
no incident bundle exists and there is nothing to approve. Do not write one by hand.

## 2. Read the investigation, and treat it as evidence

Mention the flow's service account on the incident issue, or run:

```bash
GITLAB_TOKEN=... .venv/bin/python scripts/duo_trigger_flow.py --issue-iid <iid>
```

The Duo flow posts a note with supported and contradicted hypotheses, unknowns, and one of
roll back, hold or escalate. The note is a recommendation. It cannot deploy, approve or roll
back, and nothing in the control plane reads it to make a decision. If the script exits
non-zero, read `poll_errors` and `session` in its evidence file: a missing session means no
investigation was observed.

## 3. Decide

Open the Approval centre in the console, or read `evidence/incident-bundle.json`:

- the exact proposal and its hash,
- the target release and its image digest,
- the risks listed in the proposal.

Then choose one:

| Decision | Action | Result |
| --- | --- | --- |
| Approve | Play `approval:grant` in the GitLab pipeline | Your GitLab login is recorded against that one proposal hash, valid for 900 s |
| Deny | Do not play the job, or run `scripts/ci_incident.py approve --deny --actor <you>` | No rollback can execute; escalate |
| Not sure | Do nothing | The gate refuses without an approval; escalate |

The approver must be a person. The gate refuses an agent or system identity.

## 4. Check the gate before it acts (optional)

Play `rollback:managed` with the variable `ROLLBACK_DRY_RUN=1`. The job evaluates every safety
check and changes nothing. Read `evidence/rollback-execution.json`: `decision.allowed` and
`decision.veto_codes`.

## 5. Roll back

Play `rollback:managed`. It refuses, and changes nothing, when any check fails.

| Veto code | Meaning | What to do |
| --- | --- | --- |
| `APPROVAL_PRESENT`, `APPROVAL_GRANTED` | No approval, or a denial | Go back to step 3 |
| `APPROVAL_ACTOR_IS_HUMAN` | The approver is not a person | A person must play `approval:grant` |
| `APPROVAL_IN_SCOPE` | The approval is for a different proposal | Approve the current proposal |
| `APPROVAL_NOT_EXPIRED`, `APPROVAL_WITHIN_MAX_AGE` | The approval is too old | Approve again |
| `ENVIRONMENT_ALLOWLISTED`, `PHASE1_ENVIRONMENT_ALLOWLISTED` | The environment is not `demo-staging` | Stop. This system must not act there |
| `TARGET_IS_KNOWN_GOOD`, `TARGET_RELEASE_KNOWN` | The target was never observed healthy | Escalate; choose a target by hand |
| `TARGET_DIFFERS_FROM_CURRENT` | The target is already deployed | A rollback cannot help; escalate |
| `MIGRATION_COMPATIBLE` | A migration is involved and compatibility is unknown | Escalate to the owner of the schema |
| `NOT_ALREADY_EXECUTED` | This rollback already ran | Do not replay; go to step 6 |
| digest mismatch (after the gate) | The image is not the artifact that was verified | Stop and find out which image is tagged |

Do not edit a bundle or an approval file to make a veto go away.

## 6. Verify recovery

`verify:recovery` runs automatically. It deploys the target again and measures a new window
that starts after the rollback. Read `evidence/verification.json`.

- `recovered: true` and `independent: true`: the incident is recovered. Continue with step 7.
- `recovered: false`: the job fails and the incident stays open. Read `reasons`. A short
  stabilization window, too few samples, the wrong release, or a p95 or error rate above the
  recovery limit are all refusals. **A green rollback job is not recovery.** Escalate.

## 7. Record

Update the incident issue with links to the pipeline, the job artifacts and the Duo session.
Copy values from the artifacts; do not type them from memory. The console
(`.venv/bin/uvicorn app.api.incident_api:app --app-dir backend --port 8000`) shows the same
artifacts and lists any that are missing.

## When GitLab does not answer

- The pipeline jobs keep state in artifacts. Retry the failed job; do not skip a stage.
- `duo_trigger_flow.py` exits non-zero and keeps the trigger note in its evidence file. A
  rollback decision does not depend on the Duo investigation.
- If you cannot verify recovery, the incident is not recovered.

## Practice

`bash scripts/demo_lifecycle_local.sh` runs these steps on one host with real containers in
about 30 seconds. See `docs/DEMO.md`.
