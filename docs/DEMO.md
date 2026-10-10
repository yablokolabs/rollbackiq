# Demo and reproduction

Two audiences: a reviewer who wants to reproduce the result, and whoever records the video.

## 1. Reproduce it in one command

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt -r demo/service/requirements.txt
.venv/bin/python scripts/demo_regression.py
```

That drives the whole story on one machine with real HTTP traffic: a healthy `v1` baseline, a
deliberately faulted `v2`, the real detector firing on the second sustained window, a rollback,
and an independent verification window. Raw record: `evidence/phase1-regression.json`.

## 2. Reproduce the CI lifecycle (the part that matters)

The pipeline is `verify → test → build → deploy → operate`, and three of its jobs are **manual
by design** — they are the human gates:

1. Push to `main`. `attribution-guard` and `test:pytest` run automatically.
2. Play **`deploy:regressed`**. It deploys v2 and measures it; if the detector does not fire it
   exits non-zero and writes no incident bundle.
3. Play **`approval:grant`**. The approver is taken from `GITLAB_USER_LOGIN`, so the person who
   plays the job is the person who approved, and the approval is scoped to one proposal hash.
4. Play **`rollback:managed`**. It runs the control plane's `SafetyGate` over the bundle; any
   veto refuses and changes nothing.
5. `verify:recovery` runs automatically and **fails the pipeline** unless recovery is proven from
   a new window that began after the rollback executed.

To evaluate the gate without changing anything, set `ROLLBACK_DRY_RUN=1` on `rollback:managed`.

Artifacts land in `evidence/` in each job: the baseline window, the detection, the bundle, the
approval, the rollback record and the verification. Those are the files the console reads.

## 3. The console

```bash
.venv/bin/uvicorn app.api.incident_api:app --app-dir backend --port 8000
#  http://127.0.0.1:8000/                     the console (needs dashboard/dist)
#  http://127.0.0.1:8000/api/incidents        the typed incident list

cd dashboard && npm install && npm run build
.venv/bin/python scripts/screenshot_dashboard.py    # renders every view; fails on any page/console error
```

The console has no write path. Anything the API cannot read is named in `missing_artifacts`
rather than filled in, and every response carries the two fixed statements — the fault is
injected deployment configuration, and a code rollback does not restore deleted data.

## 4. Re-running the Duo investigation

```bash
.venv/bin/python scripts/duo_trigger_flow.py     # fires the mention trigger, polls, exits non-zero unless FINISHED
.venv/bin/python scripts/duo_provision_catalog.py  # re-assert the agent + flow from duo/ and verify by SHA-256
```

Both need `GITLAB_TOKEN` in the environment; the token is never stored in the repository.

## 5. The recording that exists today

`docs/demo/rollbackiq-demo.mp4` — **1:44, 1440×900, real data, captions and no narration**, produced by
`scripts/record_demo.py` at 18:19 UTC.

What is in it:

- **A real lifecycle run on this host**, streamed live into the frame as it happened: real containers,
deploy v1 and a measured baseline, the real detector firing on v2, an approval scoped to one proposal
hash, the gate evaluated by dry run, the authorized rollback, and verification of a **new** window that
started after the rollback. The recorder refuses to keep a take whose log pane did not render the run
(that guard is in the script, after an earlier take produced a blank pane that still looked like a video).
- **The incident console over that run's artifacts**, touring all six views.

What is deliberately **not** in it, so it must not be mistaken for the final submission take:

- **The approval is not played by hand in the GitLab UI.** It is the local run's approval, recorded by
  `scripts/demo_lifecycle_local.sh` with the container host's user. The required final take plays
  `deploy:regressed`, `approval:grant` and `rollback:managed` in the GitLab UI so the approver is a person
  clicking Approve, which is the one thing this host cannot do.
- The pipeline's job logs are not on screen; the console and the local run are.

Captions are drawn as an overlay and the overlay is styled as one: the viewer is always told which layer
they are looking at.

## 6. The video: under three minutes

The rules require an under-3-minute video showing the automation actually running. This
storyboard is written to fit **2:50**, and every shot is something that genuinely exists.

| Time | On screen | What is said (beats, not a script) |
| --- | --- | --- |
| 0:00–0:20 | Console **Overview**: the faulted windows at 8.59× / 8.75× the 27.24 ms baseline | The problem: a deploy regressed latency and errors, and the usual answer is a rollback nobody proved. The claim here is *verified* recovery. |
| 0:20–0:40 | GitLab **pipeline 2932808602** job graph | The lifecycle is real CI/CD: guard, tests, build with an immutable digest, health-gated deploy of v1, then a deliberate v2. |
| 0:40–1:00 | Play **`deploy:regressed`** in the UI; its log shows the detector firing | The regression is not staged in a slide: the job fails closed unless the real detector fires on measured windows. |
| 1:00–1:25 | Type the comment that mentions the flow's service account on issue #2; the session link appears | The GitLab-native investigation: a **custom Duo agent and flow** in the AI Catalog, triggered from the issue. It reads the repository's evidence and reports back. |
| 1:25–1:45 | Issue #2: the flow's report, recommending **HOLD** | Point out that it refused the incident's numbers without artifacts — and that the mismatch it flagged was a real error in our own record. That is the behaviour worth trusting. |
| 1:45–2:05 | Play **`approval:grant`** **by hand in the UI** | This is the gate: a named human approves one exact proposal hash. No approval, no action — and the wait is the point. |
| 2:05–2:25 | Play **`rollback:managed`**; the log shows 18 checks passed, `veto_codes: []`, then the deploy | The agent cannot do this. The gate checks environment, target, approval scope and expiry, migration safety, digest and idempotency before anything changes. |
| 2:25–2:45 | `verify:recovery` log and the console **Verification** view: 6.01 s window, 200 samples, p95 1.014×, 0.0% errors, window started *after* the rollback | The point of the whole project: a green rollback job is not recovery. A new window measured after the action is. |
| 2:45–2:50 | Console **Approval centre** or the issue's evidence links | Close on the audit trail: every claim in the video is an artifact in the repository. |

Rules for the recording:

- **Play the three manual jobs by hand in the UI.** Do not trigger them through the API: the
  point of `approval:grant` is that a person decided, and an API-triggered job records the token
  owner instead.
- **Say these two things out loud**, because leaving them out would be misleading: the fault is
  **injected deployment configuration** — v1 and v2 are the same image digest — and a **code
  rollback does not restore deleted data**, which is why writing the fault to delete data was
  never done.
- **Do not imply the Duo flow orchestrates the lifecycle.** It investigates and recommends. The
  execution path is the CI/CD safety gate, and that separation is the design.
- If the console is on screen, use the real incident; do not build a mock view for the video.

## 7. What a reviewer should check first

| Claim | Check |
| --- | --- |
| The recording is real | `scripts/record_demo.py`, and `evidence/demo-run/` artifacts from the recorded run (`verification.json`: `recovered=True`, `independent=True`, 200 samples, 6.01 s) |
| The gate refuses | `backend/tests/test_safety.py`, and `evidence/local-ci-lifecycle/` for the six real refusals |
| Recovery is independently verified | `evidence/gitlab-ci-lifecycle-artifacts/verification.json` against `baseline-window.json`; compare its window start with the rollback's `executed_at` |
| The detector cannot be talked into firing | the behaviour of `deploy:regressed` when the window is healthy, and `backend/tests/test_detector.py` |
| Duo genuinely ran | `evidence/duo-flow-trigger-session.json`, and the report it posted as note 3990222263 on issue #2 |
| The console shows real data | `docs/screenshots/*.png`, produced by `scripts/screenshot_dashboard.py` against the committed artifacts |
