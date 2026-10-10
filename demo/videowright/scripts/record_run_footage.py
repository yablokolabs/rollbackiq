#!/usr/bin/env python3
"""Record a real lifecycle run as footage for the demo video.

The video must show the automation running, so this starts
`scripts/demo_lifecycle_local.sh` (real containers, the real detector, the real
safety gate, the real verifier) and records its output while it runs. Nothing is
replayed: the page polls the log file of the live process.

To stay readable at video size, the page hides two kinds of line and says so in
its header: the `+ docker ...` command traces and the `written: ...` file notes.
Every other line is the process's own output, in order and unedited.

    ../../.venv/bin/python scripts/record_run_footage.py

Writes to videos/rollbackiq-demo/footage/:
    run.mp4          the recording, 1216x684
    marks.json       seconds from the start of run.mp4 at which each stage began
    run.log          the complete, unfiltered output of the run
    artifacts/       every artifact the run wrote

Exits non-zero, and keeps nothing, if the run did not verify recovery or the log
pane did not render the run's output.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT.parents[1]
FOOTAGE = PROJECT / "videos" / "rollbackiq-demo" / "footage"
SIZE = {"width": 1216, "height": 684}

# mark name -> text of the stage line that starts it
STAGES = {
    "baseline": "deploy v1 and capture",
    "regress": "deploy v2 and require",
    "approve": "a human approves",
    "dry_run": "evaluate the safety gate",
    "rollback": "execute the authorized rollback",
    "verify": "independently verify recovery",
    "done": "done — artifacts",
}

PLAYER = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>RollbackIQ live run</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0b1626; color: #e8eef5; height: 684px; overflow: hidden;
         font-family: 'JetBrains Mono', 'DejaVu Sans Mono', ui-monospace, monospace; }
  header { display: flex; justify-content: space-between; align-items: center;
           padding: 12px 22px; background: #051d35; border-bottom: 1px solid #1d3a5c;
           font-size: 15px; color: #9fb4c9; }
  header b { color: #ffffff; font-weight: 600; }
  pre { padding: 14px 22px; font-size: 18px; line-height: 1.5; height: 636px; overflow: hidden;
        white-space: pre; }
  .head { color: #6cc0ff; font-weight: 600; }
  .pass { color: #63d08c; }
  .bad { color: #ff8a80; }
  .verdict { color: #ffffff; font-weight: 700; background: #17603a; }
</style></head>
<body>
  <header><span><b>live process output</b> &middot; scripts/demo_lifecycle_local.sh</span>
          <span>hidden: docker command traces, file notes</span></header>
  <pre id="log"></pre>
<script>
  const log = document.getElementById('log');
  const esc = (s) => s.replace(/[&<>]/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]));
  function show(line) {
    const text = line.length > 98 ? line.slice(0, 97) + '…' : line;
    if (line.startsWith('>>>')) return '\\n<span class="head">' + esc(text) + '</span>';
    if (/recovered=True/.test(line)) return '<span class="verdict">' + esc(text) + '</span>';
    if (line.includes('[pass]')) return '<span class="pass">' + esc(text) + '</span>';
    if (/triggered=True|REFUSED|refused|FAIL|recovered=False/.test(line)) return '<span class="bad">' + esc(text) + '</span>';
    return esc(text);
  }
  async function poll() {
    try {
      const res = await fetch('/run.log?ts=' + Date.now(), {cache: 'no-store'});
      const lines = (await res.text()).split('\\n')
        .filter((l) => l.trim() && !l.startsWith('+ ') && !l.trimStart().startsWith('written:'));
      window.__lines = lines;
      log.innerHTML = lines.map(show).join('\\n').split('\\n').slice(-22).join('\\n');
    } catch (err) { /* the log appears a moment after the run starts */ }
    setTimeout(poll, 200);
  }
  poll();
</script>
</body></html>
"""


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="rollbackiq-footage-"))
    log_path = work / "run.log"
    log_path.write_text("")
    marks: dict[str, float] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=SIZE, record_video_dir=str(work), record_video_size=SIZE
        )
        page = context.new_page()
        recording_started = time.monotonic()

        def serve(route):
            if "/run.log" in route.request.url:
                route.fulfill(status=200, content_type="text/plain; charset=utf-8", body=log_path.read_text())
            else:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=PLAYER)

        # Served from a routed origin: on about:blank a relative fetch cannot resolve.
        page.route("http://run.local/**", serve)
        page.goto("http://run.local/")
        page.wait_for_timeout(1000)

        env = dict(os.environ, DEMO_WORKDIR=str(work / "artifacts"), DEMO_CONTAINER="rollbackiq-footage-workload")
        with log_path.open("w") as log_file:
            run = subprocess.Popen(
                ["bash", str(REPO_ROOT / "scripts" / "demo_lifecycle_local.sh")],
                cwd=REPO_ROOT, env=env, stdout=log_file, stderr=subprocess.STDOUT,
            )
            while run.poll() is None and time.monotonic() - recording_started < 240:
                page.wait_for_timeout(100)
                shown = "\n".join(page.evaluate("() => window.__lines || []"))
                for name, text in STAGES.items():
                    if name not in marks and text in shown:
                        marks[name] = round(time.monotonic() - recording_started, 2)
        page.wait_for_timeout(1500)
        shown = "\n".join(page.evaluate("() => window.__lines || []"))
        for name, text in STAGES.items():
            if name not in marks and text in shown:
                marks[name] = round(time.monotonic() - recording_started, 2)
        marks["end"] = round(time.monotonic() - recording_started, 2)
        page.wait_for_timeout(2000)
        video = page.video
        context.close()
        browser.close()
        raw = Path(video.path())

    for name in ("rollbackiq-footage-workload", "rollbackiq-footage-workload-verify", "rollbackiq-workload-v2"):
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)

    verification = work / "artifacts" / "verification.json"
    recovered = verification.exists() and json.loads(verification.read_text())["result"]["recovered"]
    if run.returncode != 0 or not recovered:
        print(f"the run did not verify recovery (exit {run.returncode}); no footage kept. Log: {log_path}")
        return 1
    missing = [name for name in STAGES if name not in marks]
    if missing or "recovered=True" not in shown:
        print(f"the log pane did not render the run (missing stages: {missing}); no footage kept")
        return 1

    FOOTAGE.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-c:v", "libx264", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", "30", str(FOOTAGE / "run.mp4")],
        check=True,
    )
    (FOOTAGE / "marks.json").write_text(json.dumps(marks, indent=2) + "\n")
    shutil.copy(log_path, FOOTAGE / "run.log")
    shutil.rmtree(FOOTAGE / "artifacts", ignore_errors=True)
    shutil.copytree(work / "artifacts", FOOTAGE / "artifacts", ignore=shutil.ignore_patterns("*-state.json", "cleanup.json"))
    shutil.rmtree(work, ignore_errors=True)
    print(f"footage: {FOOTAGE / 'run.mp4'}")
    print(f"marks: {marks}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
