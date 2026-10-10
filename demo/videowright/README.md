# The demonstration video

`demo/videos/rollbackiq-demo.mp4` is built here with [VideoWright](https://github.com/scosman/videowright):
eight narrated scenes, real GitLab and console screenshots, and a recording of a real
lifecycle run placed inside two of the scenes.

## What is real in it

| On screen | Source | Made by |
| --- | --- | --- |
| The live terminal in the Detect and Recover scenes | A lifecycle run on one host with real containers, recorded while it ran | `scripts/record_run_footage.py` → `videos/rollbackiq-demo/footage/` (video, stage marks, full log, artifacts) |
| GitLab pipeline, `verify:recovery` job log, the Duo flow's note | The public GitLab pages, as served | `scripts/capture_gitlab_screens.py` |
| Approval record | The incident console over the committed pipeline artifacts | `scripts/capture_gitlab_screens.py` |
| Numbers beside a GitLab screenshot | `evidence/gitlab-ci-lifecycle-artifacts/` (pipeline 2932808602) | typed from the artifacts |
| Numbers in the two live scenes | `videos/rollbackiq-demo/footage/artifacts/` (that run) | typed from the artifacts |
| 5 of 5, 0 of 5 | `evidence/evaluation/summary.json` | typed from the summary |

The live terminal hides the `+ docker ...` command traces and the `written:` notes, and its
header says so. `footage/run.log` is the complete output.

What the video does not show: a person playing the approval job in the GitLab UI. In the
recorded pipeline the token owner played it through the API, and the Decide scene says so.

## Narration

ElevenLabs, voice Alice (British English, female), model `eleven_multilingual_v2`. The text is the
`voiceover` field of each segment, collected in
`videos/rollbackiq-demo/audio/originals/voiceovers/v1/provider_script.md`.

## Rebuild

```bash
cd demo/videowright
npm ci                                             # also applies the videowright 0.1.1 shim

# only when the pictures must change
../../.venv/bin/python scripts/capture_gitlab_screens.py   # needs dashboard/dist
../../.venv/bin/python scripts/record_run_footage.py       # needs the rollbackiq-workload:local image

# only when the words must change (uses ElevenLabs credits; needs ELEVENLABS_API_KEY, jq)
bash videos/rollbackiq-demo/audio/originals/voiceovers/v1/generate.sh
python3 scripts/sync_audio.py                      # scene timing from the word timestamps
python3 scripts/build_subtitles.py                 # ../videos/rollbackiq-demo.{srt,vtt}

npx videowright dev --port 5199 &                  # then, in another shell:
node scripts/check_scene_layout.mjs                # every scene fits the frame, nothing overlaps

npx videowright render rollbackiq-demo --output build/scenes.mp4
python3 scripts/composite_footage.py               # -> ../videos/rollbackiq-demo.mp4, fails at 3:00 or more
```

New narration words need matching cue words in `scripts/sync_audio.py`. A new footage
recording needs a look at the two live scenes: their side panels quote that run's values.
`videowright render` can exit 0 when a segment throws, so look at frames of the result.
