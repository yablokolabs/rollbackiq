# Devpost submission text (draft)

Paste the sections below into the Devpost form. Every figure comes from an artifact in this
repository; `docs/COMPETITION_COMPLIANCE.md` maps each claim to its evidence. Two fields are
still empty and only the entrant can fill them: the **YouTube link** (the rules require the
video to be public on YouTube) and the final choice of prize category.

---

**Project name:** RollbackIQ

**Tagline:** Detect. Decide. Recover. A rollback is not recovery until a new measurement proves it.

**Path:** A — Start Fresh. **Level of autonomy:** Supervised.

**Repository:** https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43178176/showcase (public, MIT)

**Video:** _YouTube link — to be added_ (source file: `demo/videos/rollbackiq-demo.mp4`, 2:36)

---

## Inspiration

A production bug once deleted customer data. Recovery took backups and a room full of people
who spent most of their time on two questions: what changed, and did the fix work? The second
question is the one that gets skipped. A rollback job turns green, everybody relaxes, and nobody
measured whether the service is healthy again.

RollbackIQ is built around that gap. It does not restore deleted data, and it says so. It
handles the case that comes first and most often: a release that makes the service slower or
makes it fail, and a rollback that must be decided by a person and then proven.

## What it does

RollbackIQ runs the post-code lifecycle of a release on GitLab, from deployment to verified
recovery:

1. **Deploy and baseline.** A GitLab CI/CD pipeline builds one image, deploys the healthy
   release and measures a baseline from real HTTP requests.
2. **Detect.** When a faulty release is deployed, a detector compares new measurement windows
   with the baseline. It opens an incident only after a sustained breach on two windows. One bad
   window is not enough.
3. **Propose.** The incident carries one rollback proposal with a hash, the target release and
   the risks.
4. **Decide.** A named person approves that exact proposal hash in a manual pipeline job. The
   approval expires after 15 minutes.
5. **Gate.** Before anything changes, a safety gate runs 18 checks: environment allowlist,
   known-good target, approver identity, approval scope and age, idempotency key. One failed
   check refuses the rollback. The image digest is then compared with the digest that was verified.
6. **Roll back.** The pipeline job deploys the target release.
7. **Verify.** A separate job deploys the target again and measures a **new** window that starts
   after the rollback. Recovery is declared only from that window. A window that is too short is
   refused.
8. **Investigate.** A custom GitLab Duo flow, started by a mention on the incident issue, reads
   the evidence and posts supported and contradicted hypotheses, open questions and a
   recommendation.
9. **Report.** An incident console shows the timeline, the approval, the 18 checks and the
   verification, read from the pipeline's own artifacts.

The agent never changes a deployment. It has no tool that can deploy, approve or roll back.

## How we used GitLab

- **GitLab CI/CD** carries the whole lifecycle in one pipeline: an attribution guard, the test
  suite, the image build, the health-gated deployment, the regression, the approval, the gated
  rollback and the independent verification. Manual jobs are the human decision points.
  Evidence travels between jobs as artifacts.
- **GitLab Duo Agent Platform**: a custom agent and a custom flow, defined in the repository
  (`duo/`), registered in the AI Catalog by a script, enabled in the project, and started by a
  flow trigger when its service account is mentioned on an issue.
- **GitLab Duo Code Review** reviewed the merge requests of this project. Its first review found
  three real defects, which were fixed; the re-review was clean.
- **GitLab issues** hold the incident record, with links to the pipeline and to the Duo session.
- **GitLab Observability**: the workload exports OpenTelemetry traces to the group's collector.
- **Container registry and environments** hold the image and the `demo-staging` target.

DevSecOps stages touched by real workflows: plan (incident issue), code review, build, test,
compliance check, release, deploy, monitor, incident response and retrospective. Security
scanning is not used and not claimed.

## Results we measured

- **In GitLab, pipeline 2932808602**, on shared runners, every job green: the faulty release
  measured at 8.59 and 8.75 times the baseline p95 with 13.3% and 8.3% errors; the gate passed
  18 of 18 checks; the verification window had 200 requests over 6.01 s, p95 at 1.014 times the
  baseline, and no errors.
- **A refusal kept as evidence:** on an earlier run the verifier refused to declare recovery,
  because its window was 1.1 s long and the minimum is 3.0 s. The pipeline failed closed.
- **Repeated runs on one host, real containers:** 5 of 5 lifecycle runs recovered and were
  verified; 5 healthy control runs gave 0 false positives.
- **Six refusals**, each by a different guard: no approval, a non-human approver, a wrong
  environment, a target that was never observed healthy, a wrong image digest, and a replay.
- **110 automated tests**, run in the pipeline.

## The most useful thing the agent did

The Duo flow's first complete investigation was not flattering. It refused to accept "recovery
verified" from the incident issue, because it could not retrieve the verification artifact, and
it listed three values in our own incident record that did not match the artifacts. It was
right: the three values had been copied wrongly. We corrected the record. It also recommended
HOLD and ESCALATE, because nothing in the evidence shows whether the failed requests damaged
data. An agent that disagrees with its operators on the evidence is the behaviour we wanted.

## How we built it

Python and FastAPI for the detector, the safety gate, the verifier and the read-only incident
API. React, TypeScript and Tailwind for the console. Docker for the demo workload: one image,
where a release is a set of deployment inputs. GitLab CI/CD for the lifecycle, GitLab Duo Agent
Platform for the investigation, OpenTelemetry for traces. The same scripts run in the pipeline
jobs and on one host, so the lifecycle can be reproduced with one command in about 30 seconds.

## Challenges

- **A catalog update that did nothing.** Updating a flow in the AI Catalog returned success but
  kept serving the old definition until the update carried a version bump and a release. The
  provisioning script now reads the stored definition back and compares it by hash.
- **The headless CLI cannot select a custom flow.** We traced this to the CLI source, recorded
  it, and used the flow trigger, which is the supported path.
- **A recovery window that proved nothing.** The first probe finished in 1.1 s. The verifier was
  right to refuse it; the measurement was wrong. The probe now paces itself.
- **A test that passed locally and failed in CI.** Adding the test stage showed that the CI image
  lacked one dependency. The test was fixed at the cause, not skipped.

## What we are proud of

The system refuses more often than it acts, and the refusals are in the repository as evidence.
Every number in the video and in this text can be traced to an artifact.

## Limits, stated plainly

- The fault is **injected deployment configuration** on one image. It is not a code regression
  in a different binary.
- **A code rollback does not restore deleted data.** Data recovery is a separate, human-controlled
  operation that this project does not perform.
- One environment (`demo-staging`), one fault setting, small request volumes. Five runs are too
  few to state a rate.
- In the recorded pipeline, the approval job was played through the API by the token owner. The
  gate enforces a real, non-agent identity; the recording does not show a person clicking.
- The Duo flow investigates and recommends. It does not run the lifecycle.
- GitLab MCP and GitLab security scanners are not used. No Google Cloud deployment is claimed.

## What is next

Security scanning in the pipeline, an approval through GitLab protected environments, a fault
near the detection thresholds to measure false negatives, and a second service to test the
design beyond one workload.

## Built with

GitLab CI/CD, GitLab Duo Agent Platform, GitLab Duo Code Review, GitLab AI Catalog, GitLab
Observability, Python, FastAPI, React, TypeScript, Tailwind CSS, Docker, OpenTelemetry, pytest,
Playwright
