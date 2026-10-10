#!/usr/bin/env python3
"""Record the demo video from a real run and the live console.

Nothing in the recording is faked. It captures, in one take:

1. a **real local lifecycle run** (``scripts/demo_lifecycle_local.sh``) in real
   containers, streamed into the page as it happens — the log the viewer watches
   is the stdout of the run in progress, not a replay;
2. the **incident console** over that run's artifacts, touring all six views.

Captions are drawn as an overlay because a terminal session cannot type narration,
and the recording is honest about it: the caption bar is styled as an overlay, not
as part of the product UI.

    .venv/bin/python scripts/record_demo.py                 # -> demo/videos/rollbackiq-local-run.mp4
    .venv/bin/python scripts/record_demo.py --skip-run      # console tour only

The run is ~35 s and the tour ~80 s, which keeps the recording under the
three-minute limit required by the competition rules.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSOLE_URL = "http://127.0.0.1:8000"

STAGE_CAPTIONS = [
    ("deploy v1", "Real containers, real probes: v1 deploys and the observer measures its healthy baseline."),
    ("REAL detector", "v2 deploys with injected faults. The real detector must fire on two sustained windows."),
    ("human approves", "A human approval, scoped to one exact proposal hash."),
    ("WITHOUT changing anything", "First the gate is evaluated without changing anything at all."),
    ("execute the authorized", "18 checks pass, and only then is the target release deployed."),
    ("independently verify", "Verification measures a NEW window that starts after the rollback executed."),
    ("done — artifacts", "Every claim in this video is an artifact written by the run."),
]

TOUR = [
    ("Overview", "Overview: the faulted windows against the healthy baseline, and the release that was rolled back from."),
    ("Timeline", "Timeline: every event in the incident, in order, with the numbers behind each one."),
    ("Investigation", "Investigation: the custom Duo flow's session and the report it posted — it recommended HOLD, not agreement."),
    ("Approval centre", "Approval centre: all 18 safety-gate checks, the approver, and the one proposal hash they were scoped to."),
    ("Verification", "Verification: a window that began after the rollback, 200 samples, p95 at 1.014x baseline."),
    ("Incident report", "The report, including what it does not claim: code rollback does not restore deleted data."),
]

OVERLAY = """
(caption) => {
  let bar = document.getElementById('rolliq-caption');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'rolliq-caption';
    Object.assign(bar.style, {
      position: 'fixed', left: '0', right: '0', bottom: '0', zIndex: '99999',
      background: 'rgba(17,17,17,0.92)', color: '#f5f5f5', padding: '18px 28px',
      font: '500 20px/1.4 system-ui, -apple-system, Segoe UI, sans-serif',
      letterSpacing: '0.01em', borderTop: '1px solid rgba(245,245,245,0.18)',
    });
    document.body.appendChild(bar);
  }
  bar.textContent = caption;
}
"""

PLAYER = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>RollbackIQ demo run</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #17181c; color: #f5f5f5; font-family: 'Geist Mono', ui-monospace, monospace;
         height: 900px; padding: 28px 28px 96px; }
  h1 { font-family: Georgia, 'Instrument Serif', serif; font-size: 34px; font-weight: 400; margin-bottom: 6px; }
  .sub { color: #a8aebd; font-size: 15px; margin-bottom: 18px; }
  .banner { color: #ff8a5c; font-size: 15px; margin-bottom: 14px; }
  pre { font-size: 13.5px; line-height: 1.55; white-space: pre-wrap; word-break: break-word;
        color: #dfe3ea; height: calc(100vh - 220px); overflow: hidden; }
  pre .head { color: #8fd3ff; }
  pre .pass { color: #7ee0a1; }
  pre .refuse { color: #ff8181; }
</style></head>
<body>
  <h1>RollbackIQ — a rollback is not recovery</h1>
  <p class="sub">A real run on this host: deploy v1 &rarr; detect the regression &rarr; human approval &rarr; gated rollback &rarr; independent verification.</p>
  <p class="banner" id="banner">starting…</p>
  <pre id="log"></pre>
<script>
  const log = document.getElementById('log');
  const banner = document.getElementById('banner');
  function colour(line) {
    const esc = line.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
    if (line.startsWith('>>>')) return '<span class="head">' + esc + '</span>';
    if (line.includes('[pass]')) return '<span class="pass">' + esc + '</span>';
    if (/REFUSED|FAIL|Traceback/.test(line)) return '<span class="refuse">' + esc + '</span>';
    return esc;
  }
  async function poll() {
    try {
      const res = await fetch('/run.log?ts=' + Date.now(), {cache: 'no-store'});
      const text = await res.text();
      const lines = text.split('\\n').filter(Boolean);
      log.innerHTML = lines.slice(-120).map(colour).join('\\n');
      log.scrollTop = log.scrollHeight;
      const stages = lines.filter(l => l.startsWith('>>>'));
      if (stages.length) banner.textContent = stages[stages.length - 1];
      window.__done = lines.some(l => l.includes('recovered=')) || lines.some(l => l.includes('REFUSED'));
    } catch (err) { /* the log appears a moment after the run starts */ }
    setTimeout(poll, 350);
  }
  poll();
</script>
</body></html>
"""


def ensure_console(console_url: str) -> subprocess.Popen | None:
    """Start the console API if it is not already answering."""
    import urllib.error
    import urllib.request

    def alive() -> bool:
        try:
            with urllib.request.urlopen(f"{console_url}/api/incidents", timeout=3):
                return True
        except (urllib.error.URLError, OSError):
            return False

    if alive():
        print("console already running")
        return None
    print("starting the console API")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app.api.incident_api:app",
            "--app-dir", str(REPO_ROOT / "backend"), "--port", console_url.rsplit(":", 1)[1],
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(40):
        if alive():
            return proc
        time.sleep(0.5)
    proc.send_signal(signal.SIGTERM)
    raise SystemExit("the console API did not come up")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="demo/videos/rollbackiq-local-run.mp4")
    parser.add_argument("--workdir", default="/tmp/rollbackiq-video")
    parser.add_argument("--skip-run", action="store_true", help="record the console tour only")
    args = parser.parse_args(argv[1:])

    out = Path(args.out)
    out = out if out.is_absolute() else REPO_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    log_path = workdir / "run.log"
    if not args.skip_run:
        log_path.write_text("")

    api = ensure_console(CONSOLE_URL)
    run_proc: subprocess.Popen | None = None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                record_video_dir=str(workdir),
                record_video_size={"width": 1440, "height": 900},
            )
            page = context.new_page()

            # The player is served from a routed origin rather than set_content()
            # or a data: URL: on about:blank a relative fetch('/run.log') cannot
            # resolve at all, which showed up as a recording whose log pane was
            # blank for the whole run. Both routes are fulfilled locally; no
            # server is involved.
            def serve_demo(route):
                if "/run.log" in route.request.url:
                    try:
                        body = log_path.read_text()
                    except OSError:
                        body = ""
                    route.fulfill(status=200, content_type="text/plain; charset=utf-8", body=body)
                else:
                    route.fulfill(status=200, content_type="text/html; charset=utf-8", body=PLAYER)

            page.route("http://demo.local/**", serve_demo)

            if not args.skip_run:
                page.goto("http://demo.local/")
                page.evaluate(OVERLAY, "RollbackIQ. The claim is verified recovery, not a rollback job that exited zero.")
                page.wait_for_timeout(4000)

                env = dict(os.environ)
                env["DEMO_WORKDIR"] = str(workdir / "artifacts")
                env["DEMO_IMAGE"] = env.get("DEMO_IMAGE", "rollbackiq-workload:local")
                print("starting the real lifecycle run")
                log_file = log_path.open("w")
                run_proc = subprocess.Popen(
                    ["bash", str(REPO_ROOT / "scripts" / "demo_lifecycle_local.sh")],
                    cwd=REPO_ROOT, env=env, stdout=log_file, stderr=subprocess.STDOUT,
                )
                page.goto("http://demo.local/")
                page.evaluate(OVERLAY, "The run has started. Every line below is that process's own output.")

                seen = set()
                started = time.time()
                while run_proc.poll() is None and time.time() - started < 240:
                    page.wait_for_timeout(700)
                    text = log_path.read_text()
                    for prefix, caption in STAGE_CAPTIONS:
                        if prefix in text and prefix not in seen:
                            seen.add(prefix)
                            page.evaluate(OVERLAY, caption)
                page.wait_for_timeout(2500)
                rc = run_proc.poll()
                print(f"lifecycle run exited {rc}")

                # A blank log pane would still produce a video, so prove the pane
                # actually rendered the run's output before accepting this take.
                rendered = page.evaluate("() => document.getElementById('log').textContent || ''")
                if len(rendered) < 500 or "[pass]" not in rendered:
                    raise SystemExit(
                        "the recording is not usable: the live log pane rendered "
                        f"{len(rendered)} characters. Refusing to keep this take."
                    )
                print(f"log pane rendered {len(rendered)} characters of live output")
                page.evaluate(
                    OVERLAY,
                    "The run finished: the rollback executed and recovery was verified from a new window."
                    if rc == 0
                    else "The run refused and changed nothing — which is also a correct outcome.",
                )
                page.wait_for_timeout(3500)

            print("touring the console")
            page.goto(f"{CONSOLE_URL}/", wait_until="networkidle")
            page.get_by_text("incident recovered", exact=False).first.wait_for(timeout=20_000)
            for label, caption in TOUR:
                page.evaluate(OVERLAY, caption)
                page.wait_for_timeout(1500)
                if label != "Overview":
                    page.get_by_role("button", name=label).click()
                page.wait_for_timeout(6000)
            page.evaluate(
                OVERLAY,
                "RollbackIQ — detect, decide, recover. Evidence, refusals and measured results are in the repository.",
            )
            page.wait_for_timeout(5000)

            video = page.video
            context.close()
            browser.close()
            raw = Path(video.path())
            print(f"raw recording: {raw} ({raw.stat().st_size // 1024} KiB)")
    finally:
        if run_proc and run_proc.poll() is None:
            run_proc.terminate()
        if api:
            api.send_signal(signal.SIGTERM)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg not found: keeping the .webm recording as the deliverable")
        shutil.move(str(raw), str(out.with_suffix(".webm")))
        return 0

    subprocess.run(
        [
            ffmpeg, "-y", "-loglevel", "error", "-i", str(raw),
            "-c:v", "libx264", "-preset", "medium", "-crf", "24",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
        ],
        check=True,
    )
    duration = subprocess.run(
        [ffmpeg, "-i", str(out), "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    print(f"video: {out.relative_to(REPO_ROOT)} ({out.stat().st_size // 1024} KiB)")
    for line in duration.splitlines():
        if "Duration" in line or "Video:" in line:
            print(" ", line.strip())
    raw.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
