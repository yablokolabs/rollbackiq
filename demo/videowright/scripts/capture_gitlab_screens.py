#!/usr/bin/env python3
"""Capture the real GitLab pages and incident console views that the demo video shows.

The project is public, so the pages load without a login and no credential is used.
Each capture is the page as GitLab serves it; nothing is edited afterwards. The viewport
is narrow on purpose, so that the text is large enough to read in a video frame.

The console views come from the incident API, which this script starts on port 8011. It
reads the committed evidence artifacts and needs `dashboard/dist` (`npm run build`).

    ../../.venv/bin/python scripts/capture_gitlab_screens.py

Writes PNG files to videos/rollbackiq-demo/assets/. Exits non-zero if a page does not
show the text that proves it is the expected page.
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT = "https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43178176/showcase"
ASSETS = Path(__file__).resolve().parents[1] / "videos" / "rollbackiq-demo" / "assets"
REPO_ROOT = Path(__file__).resolve().parents[3]
CONSOLE = "http://127.0.0.1:8011"
VIEWPORT = {"width": 1180, "height": 740}

# name -> (url, text that must be visible, element to scroll to or None)
PAGES = {
    "gitlab-pipeline": (f"{PROJECT}/-/pipelines/2932808602", "rollback:managed", None),
    "gitlab-verify-job": (f"{PROJECT}/-/jobs/17076805681", "recovered=True", None),
    "gitlab-duo-note": (f"{PROJECT}/-/issues/2#note_3990222263", "Retrieval limits", "#note_3990222263"),
}

# (name, console tab, text that must be visible, heading of the column that is left out)
CONSOLE_VIEWS = [
    ("approval-record", "Approval centre", "Approval record", "Safety gate checks"),
]


def start_console() -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.api.incident_api:app",
         "--app-dir", str(REPO_ROOT / "backend"), "--port", CONSOLE.rsplit(":", 1)[1]],
        cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"{CONSOLE}/api/incidents", timeout=2):
                return proc
        except OSError:
            time.sleep(0.5)
    proc.terminate()
    raise SystemExit("the incident console did not start")


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    failures = 0
    console = start_console()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
            for name, (url, proof, anchor) in PAGES.items():
                page.goto(url, wait_until="domcontentloaded")
                try:
                    page.get_by_text(proof, exact=False).first.wait_for(timeout=45000)
                except Exception as exc:  # noqa: BLE001 - report which page failed and why
                    print(f"FAILED {name}: {proof!r} not visible at {page.url} ({type(exc).__name__})")
                    failures += 1
                    continue
                target = page.locator(anchor).first if anchor else page.get_by_text(proof, exact=False).first
                target.scroll_into_view_if_needed()
                page.wait_for_timeout(1500)
                page.screenshot(path=str(ASSETS / f"{name}.png"))
                print(f"captured {name}.png from {url}")

            page.goto(f"{CONSOLE}/", wait_until="networkidle")
            page.get_by_text("incident recovered", exact=False).first.wait_for(timeout=20000)
            for name, label, proof, right_of in CONSOLE_VIEWS:
                page.get_by_role("button", name=label).click()
                page.get_by_text(proof, exact=False).first.wait_for(timeout=10000)
                page.get_by_text(proof, exact=False).first.scroll_into_view_if_needed()
                page.wait_for_timeout(600)
                # Only the part left of the named column, so the capture is one readable card.
                edge = page.get_by_text(right_of, exact=False).first.bounding_box()["x"]
                clip = {"x": 0, "y": 0, "width": edge - 12, "height": VIEWPORT["height"]}
                page.screenshot(path=str(ASSETS / f"{name}.png"), clip=clip)
                print(f"captured {name}.png from the incident console, view {label!r}")
            browser.close()
    finally:
        console.terminate()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
