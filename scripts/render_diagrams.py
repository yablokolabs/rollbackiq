#!/usr/bin/env python3
"""Self-check and render the diagrams in ``docs/diagrams/``.

Each diagram is a self-contained HTML file with an inline SVG (Diagram Design).
This script:

1. runs the skill's own ``self_check.py`` against every file, which enforces the
   accessible-SVG contract (``role="img"``, a prefixed ``<title>`` first, no bare
   ``title``/``desc`` ids) and single-file safety;
2. opens the file in Chromium, waits for the webfonts to load, and screenshots the
   diagram only -- the editorial wrappers (header, cards, footer) are deliberately
   dropped, matching the skill's export rule;
3. fails on any uncaught page error or ``console.error``.

    .venv/bin/python scripts/render_diagrams.py            # all diagrams
    .venv/bin/python scripts/render_diagrams.py architecture.html
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
DIAGRAM_DIR = REPO_ROOT / "docs" / "diagrams"
SELF_CHECK = (
    REPO_ROOT / ".agents" / "skills" / "diagram-design" / "scripts" / "self_check.py"
)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*", help="specific .html files (default: all)")
    parser.add_argument("--scale", type=int, default=2, help="device scale factor")
    parser.add_argument("--skip-self-check", action="store_true")
    args = parser.parse_args(argv[1:])

    files = (
        [DIAGRAM_DIR / name for name in args.names]
        if args.names
        else sorted(DIAGRAM_DIR.glob("*.html"))
    )
    if not files:
        print("no diagrams found", file=sys.stderr)
        return 1

    failures: list[str] = []

    if not args.skip_self_check and SELF_CHECK.exists():
        for path in files:
            result = subprocess.run(
                [sys.executable, str(SELF_CHECK), str(path)],
                capture_output=True,
                text=True,
            )
            status = "ok" if result.returncode == 0 else "FAILED"
            print(f"self-check {path.name}: {status}")
            if result.returncode != 0:
                failures.append(f"self-check {path.name}:\n{result.stdout}{result.stderr}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(device_scale_factor=args.scale)
        problems: list[str] = []
        page.on("pageerror", lambda exc: problems.append(f"pageerror: {exc}"))
        page.on(
            "console",
            lambda msg: problems.append(f"console.error: {msg.text}")
            if msg.type == "error"
            else None,
        )

        for path in files:
            page.goto(path.as_uri(), wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(300)
            target = path.with_suffix(".png")
            page.locator("svg").first.screenshot(path=str(target))
            size = target.stat().st_size
            print(f"rendered {target.relative_to(REPO_ROOT)} ({size} bytes)")
            if size < 5_000:
                problems.append(f"{target.name} looks empty at {size} bytes")

        browser.close()

    failures.extend(problems)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("all diagrams rendered with no page or console errors")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
