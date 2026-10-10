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

## 5. The demonstration video

`demo/videos/rollbackiq-demo.mp4` — **2:36, 1920×1080, narrated** (British English, female voice),
with subtitles in `demo/videos/rollbackiq-demo.srt` and `.vtt`. It is built in `demo/videowright/`;
`demo/videowright/README.md` lists the source of every picture and number, and the rebuild commands.

| Rule for the video | How this video meets it |
| --- | --- |
| Under three minutes | 2:36. `composite_footage.py` exits non-zero at 3:00 or more |
| Shows the automation running, not slides or a mockup | Two scenes carry a **recording of a real lifecycle run** (real containers, the real detector, safety gate and verifier), made while the run happened. The other scenes show the real GitLab pipeline, the `verify:recovery` job log and the Duo flow's note, as GitLab serves them |
| Explains the problem, the solution, and the use of GitLab | Problem: a rollback that nobody proved. Solution: detect by measurement, approve one exact proposal, verify from a new window. GitLab: one CI/CD pipeline for the lifecycle, and a custom Duo flow from the AI Catalog that investigates on the incident issue |

Eight scenes: the problem and the rule; the pipeline and the baseline; detection (live footage);
approval and the gate; rollback and independent verification (live footage, shown at 1.25x and
labelled so); the Duo investigation; the GitLab result and the repeated runs; the limits.

What the video does **not** show, and says so on screen:

- **A person playing the approval job in the GitLab UI.** In pipeline 2932808602 the token owner
  played `approval:grant` through the API. In the live footage the approver is the host user of
  the local run. A take with the three manual jobs played by hand in the GitLab UI needs a person.
- The Duo flow does not run the lifecycle. It investigates and recommends, and its note
  recommended HOLD and ESCALATE.

The narration says two things that must not be left out: the fault is **injected deployment
configuration** on the same image, and a **code rollback does not restore deleted data**.

`demo/videos/rollbackiq-local-run.mp4` is the earlier silent recording (1:44): one whole local run
and a tour of the six console views, made by `scripts/record_demo.py`.

## 6. A take with the approval played by hand

This is the one part that needs a person. Pipeline
[2934572189](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43178176/showcase/-/pipelines/2934572189)
on `main` has run its automatic jobs and waits at the manual ones. Job artifacts expire after one
week; a new pipeline on `main` gives the same starting point.

1. Start a screen recording of the pipeline page.
2. Play `deploy:regressed`. Its log must show the detector firing on window 2.
3. Play `approval:grant`. Your GitLab login is recorded against one proposal hash.
4. Play `rollback:managed`. Its log shows the 18 checks and the deployment of v1.
5. `verify:recovery` runs by itself. Its log must end with `recovered=True independent=True`.

Do not trigger the three jobs through the API: the point of `approval:grant` is that a person
decided. The recording can replace the two live-footage clips, or follow the video as a second file.

## 7. What a reviewer should check first

| Claim | Check |
| --- | --- |
| The recording is real | `scripts/record_demo.py`, and `evidence/demo-run/` artifacts from the recorded run (`verification.json`: `recovered=True`, `independent=True`, 200 samples, 6.01 s) |
| The gate refuses | `backend/tests/test_safety.py`, and `evidence/local-ci-lifecycle/` for the six real refusals |
| Recovery is independently verified | `evidence/gitlab-ci-lifecycle-artifacts/verification.json` against `baseline-window.json`; compare its window start with the rollback's `executed_at` |
| The detector cannot be talked into firing | the behaviour of `deploy:regressed` when the window is healthy, and `backend/tests/test_detector.py` |
| Duo genuinely ran | `evidence/duo-flow-trigger-session.json`, and the report it posted as note 3990222263 on issue #2 |
| The console shows real data | `docs/screenshots/*.png`, produced by `scripts/screenshot_dashboard.py` against the committed artifacts |
