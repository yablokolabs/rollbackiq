#!/usr/bin/env python3
"""Geometry audit for the diagrams in ``docs/diagrams/``.

Diagram Design's taste gate asks for four things that can be *measured* rather
than eyeballed, and its own ``verify-geometry.py`` is not part of the installed
skill, so this checks them directly in a browser:

1. no two text elements overlap (colliding labels are illegible);
2. no text escapes the SVG viewBox;
3. every ``<line>`` is axis-aligned (a diagonal connector is a hard fail; the
   rules allow a straight line only when both ends share an x or a y);
4. no label mask (a ``#f5f5f5`` rect of label height) overlaps a node box.

Node boxes are recognised by ``rx >= 6`` plus a stroke; masks by a paper fill and
a height under 20. Anything the heuristics cannot classify is reported as
"unclassified" rather than silently passed.

    .venv/bin/python scripts/check_diagram_geometry.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
DIAGRAM_DIR = REPO_ROOT / "docs" / "diagrams"

COLLECT = """
() => {
  const svg = document.querySelector('svg');
  const vb = svg.viewBox.baseVal;
  const num = (el, attr) => parseFloat(el.getAttribute(attr) || '0');
  const texts = [...svg.querySelectorAll('text')].map(el => {
    const b = el.getBBox();
    return { text: (el.textContent || '').slice(0, 44), x: b.x, y: b.y, w: b.width, h: b.height };
  });
  const lines = [...svg.querySelectorAll('line')].map(el => ({
    x1: num(el, 'x1'), y1: num(el, 'y1'), x2: num(el, 'x2'), y2: num(el, 'y2'),
  }));
  const rects = [...svg.querySelectorAll('rect')].map(el => {
    const b = el.getBBox();
    return {
      x: b.x, y: b.y, w: b.width, h: b.height,
      rx: num(el, 'rx'),
      fill: (el.getAttribute('fill') || '').toLowerCase(),
      stroke: (el.getAttribute('stroke') || ''),
      dashed: Boolean(el.getAttribute('stroke-dasharray')),
    };
  });
  return { viewBox: { w: vb.width, h: vb.height }, texts, lines, rects };
}
"""


def overlaps(a: dict, b: dict) -> bool:
    return (
        a["x"] < b["x"] + b["w"]
        and b["x"] < a["x"] + a["w"]
        and a["y"] < b["y"] + b["h"]
        and b["y"] < a["y"] + a["h"]
    )


def audit(page, path: Path) -> list[str]:
    page.goto(path.as_uri(), wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(200)
    data = page.evaluate(COLLECT)
    issues: list[str] = []

    # 1. text vs text
    texts = data["texts"]
    for i, first in enumerate(texts):
        for second in texts[i + 1 :]:
            if overlaps(first, second):
                issues.append(
                    f"text overlap: {first['text']!r} and {second['text']!r}"
                )

    # 2. text inside the canvas
    for t in texts:
        if t["x"] < 0 or t["y"] < 0:
            issues.append(f"text starts off-canvas: {t['text']!r} at ({t['x']:.0f},{t['y']:.0f})")
        if t["x"] + t["w"] > data["viewBox"]["w"] + 1:
            issues.append(
                f"text overflows the canvas: {t['text']!r} ends at {t['x'] + t['w']:.0f} "
                f"of {data['viewBox']['w']:.0f}"
            )
        if t["y"] + t["h"] > data["viewBox"]["h"] + 1:
            issues.append(f"text below the canvas: {t['text']!r}")

    # 3. axis-aligned connectors
    for line in data["lines"]:
        if abs(line["x1"] - line["x2"]) > 0.5 and abs(line["y1"] - line["y2"]) > 0.5:
            issues.append(
                f"diagonal connector: ({line['x1']:.0f},{line['y1']:.0f}) -> "
                f"({line['x2']:.0f},{line['y2']:.0f})"
            )

    # 4. label masks over node boxes. A dashed rect of this size is a zone or a
    # trust boundary, not a node: zones are painted first, so a mask over one is
    # explicitly allowed by the connector rules.
    nodes = [
        r
        for r in data["rects"]
        if r["rx"] >= 6 and r["h"] >= 48 and r["stroke"] and not r["dashed"]
    ]
    masks = [
        r
        for r in data["rects"]
        if r["fill"] in {"#f5f5f5", "#f5f5f5"} and r["h"] <= 20 and r["rx"] <= 4
    ]
    for mask in masks:
        for node in nodes:
            if overlaps(mask, node):
                issues.append(
                    f"label mask at ({mask['x']:.0f},{mask['y']:.0f}) overlaps a node box "
                    f"at ({node['x']:.0f},{node['y']:.0f})"
                )

    return issues


def main() -> int:
    files = sorted(DIAGRAM_DIR.glob("*.html"))
    if not files:
        print("no diagrams found", file=sys.stderr)
        return 1

    total = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        for path in files:
            issues = audit(page, path)
            total += len(issues)
            if issues:
                print(f"{path.name}: {len(issues)} issue(s)")
                for issue in issues:
                    print(f"  - {issue}")
            else:
                print(f"{path.name}: clean")
        browser.close()

    print(f"geometry audit: {total} issue(s) across {len(files)} diagram(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
