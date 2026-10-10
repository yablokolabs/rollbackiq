#!/usr/bin/env python3
"""Render the incident console in Chromium and capture one screenshot per view.

This is also the dashboard's render check, not just a screenshot tool: the script
fails when the page raises an uncaught error, logs a console error, or a view
never reaches its expected heading. A build that compiles but renders nothing is
a broken console, and this is what catches that.

The API must be running and serving the built dashboard first:

    .venv/bin/uvicorn app.api.incident_api:app --app-dir backend --port 8000

    .venv/bin/python scripts/screenshot_dashboard.py --url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent

#: (nav button text, a string that must be present once the view has rendered)
VIEWS = [
    ("Overview", "Latency across the incident"),
    ("Timeline", "Incident timeline"),
    ("Investigation", "GitLab Duo custom flow"),
    ("Approval centre", "Safety gate checks"),
    ("Verification", "Recovery verified"),
    ("Incident report", "What this report does not claim"),
]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--out", default="docs/screenshots")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1000)
    args = parser.parse_args(argv[1:])

    out = Path(args.out)
    out = out if out.is_absolute() else REPO_ROOT / out
    out.mkdir(parents=True, exist_ok=True)

    problems: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        page.on("pageerror", lambda exc: problems.append(f"pageerror: {exc}"))
        page.on(
            "console",
            lambda msg: problems.append(f"console.error: {msg.text}")
            if msg.type == "error"
            else None,
        )

        page.goto(args.url, wait_until="networkidle")
        page.get_by_text("incident recovered", exact=False).first.wait_for(timeout=20_000)

        for label, marker in VIEWS:
            if label != "Overview":
                page.get_by_role("button", name=label).click()
            page.get_by_text(marker, exact=False).first.wait_for(timeout=10_000)
            page.wait_for_timeout(250)
            target = out / f"{label.lower().replace(' ', '-')}.png"
            page.screenshot(path=str(target), full_page=True)
            print(f"captured {target.relative_to(REPO_ROOT)}")

        browser.close()

    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print("no page or console errors during render")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
