# Diagrams

Five diagrams, built with the [`diagram-design`](https://github.com/cathrynlavery/diagram-design)
skill (installed into `.agents/skills/diagram-design/`, MIT). Each is one
self-contained HTML file with an inline SVG, and each `.png` is rendered from that HTML —
the PNGs are generated artifacts, not hand editing surfaces.

| Diagram | Type | What it shows |
| --- | --- | --- |
| [`architecture.html`](architecture.html) | Architecture | The path from a regressed deployment to an authorized rollback, with the control plane drawn as a boundary that nothing crosses without the gate. |
| [`duo-flow-sequence.html`](duo-flow-sequence.html) | Sequence | Session 9288744 as it ran: mention → trigger → session → repository reads → report on issue #2, quoting the run's own words. |
| [`incident-state-machine.html`](incident-state-machine.html) | State machine | The nine states and the legal transitions from `backend/app/models/incident.py`, including the refusal path that converges on `ESCALATED`. |
| [`trust-boundary-layers.html`](trust-boundary-layers.html) | Layer stack | Where each control is enforced, from the agent's proposal down to the container, with the six refusals that the real gate produced. |
| [`pipeline-timeline.html`](pipeline-timeline.html) | Timeline | Pipeline 2932808602 measured: seven jobs positioned by cumulative runtime, with the two manual gates marked. |

## Regenerating

```bash
.venv/bin/python scripts/render_diagrams.py          # self-check + render all
.venv/bin/python scripts/render_diagrams.py architecture.html
.venv/bin/python scripts/check_diagram_geometry.py   # geometry audit
```

`render_diagrams.py` runs the skill's own `self_check.py` (accessible-SVG contract:
`role="img"`, a prefixed `<title>` first, no bare `title`/`desc` ids) and then screenshots
**only the `<svg>` node** in Chromium at 2×, matching the skill's export rule that the
editorial wrapper is dropped. It fails on any uncaught page error or `console.error`.

`check_diagram_geometry.py` measures the four connector rules that can be checked
mechanically, because the skill's `verify-geometry.py` is not part of the installed package:
no two text elements overlap, no text escapes the canvas, every `<line>` is axis-aligned
(diagonals are a hard fail), and no label mask sits on a node box. It found a real collision
on the first run — the sequence diagram's actor name and sublabel were 0.3 px apart — and
that was fixed by raising the actor boxes rather than by relaxing the check.

## Skin

The diagrams use the skill's shipped editorial skin — paper `#f5f5f5`, ink `#2d3142`,
accent `#bf4520` — rather than a re-skin, because this project has no brand system of
its own: the incident console is a product UI, and borrowing its Tailwind palette would
give the documentation a skin it does not own. Say the word and the five files can be
re-skinned to any palette; the skill keeps every colour as a semantic role, so it is a
token change, not a redraw.
