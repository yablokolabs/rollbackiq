#!/usr/bin/env python3
"""Put the recording of the real run into the rendered scenes.

`videowright render` draws the scenes and the narration. Two scenes have an empty
`.footage` box. This script places the matching part of `footage/run.mp4` (recorded
by `scripts/record_run_footage.py` from a live lifecycle run) into that box, at the
moment its scene reveals the box. The clip is not scaled, and its last frame stays until
the scene ends. A clip plays at real speed unless PLACEMENTS gives it a speed factor; a
scene with a factor other than 1 must state that factor on screen.

    python3 scripts/composite_footage.py

Reads build/scenes.mp4, footage/run.mp4, footage/marks.json and the segment timing in
audio/tracks/v1/track.ts. Writes ../videos/rollbackiq-demo.mp4 and prints its duration.
Exits non-zero if the result is three minutes or longer.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
VIDEO = PROJECT / "videos" / "rollbackiq-demo"
SCENES = PROJECT / "build" / "scenes.mp4"
OUT = PROJECT.parent / "videos" / "rollbackiq-demo.mp4"

# Position and size of `.rq-scene .footage` in components/scene.css.
FOOTAGE_BOX = {"x": 96, "y": 236, "w": 1216, "h": 684}
REVEAL_S = 0.5  # the box fades in for this long; the clip fades in with it
END_GAP_S = 0.25  # the clip leaves this long before the scene ends, under the cross-fade
MAX_SECONDS = 180.0

# scene -> (index of the reveal that shows the box, or None for the scene start,
#           first mark of the clip, last mark of the clip, seconds shown before the first mark,
#           seconds shown after the last mark, speed factor)
PLACEMENTS = {
    "regression": (0, "regress", "approve", 0.4, 0.05, 1.0),
    "recovery": (None, "rollback", "end", 0.2, 1.5, 1.25),
}


def segment_timing() -> dict[str, list[float]]:
    source = (VIDEO / "audio" / "tracks" / "v1" / "track.ts").read_text()
    return {
        name: [float(value) for value in values.split(",") if value.strip()]
        for name, values in re.findall(r"^\t\t\t(\w+): \[([^\]]*)\],$", source, re.MULTILINE)
    }


def duration(path: Path) -> float:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(probe.stdout)


def main() -> int:
    timing = segment_timing()
    marks = json.loads((VIDEO / "footage" / "marks.json").read_text())
    missing = [scene for scene in PLACEMENTS if scene not in timing]
    if missing:
        raise SystemExit(f"no timing for {missing} in track.ts")

    starts, clock = {}, 0.0
    for name, values in timing.items():
        starts[name] = clock
        clock += values[-1]

    inputs = ["-i", str(SCENES)]
    filters = []
    last = "0:v"
    for index, (scene, (reveal, first, final, lead, tail, speed)) in enumerate(PLACEMENTS.items(), start=1):
        scene_start = starts[scene]
        show_at = scene_start + (timing[scene][reveal] if reveal is not None else 0.0)
        hide_at = scene_start + timing[scene][-1] - END_GAP_S
        clip_from = max(0.0, marks[first] - lead)
        source_len = marks[final] - clip_from + tail
        clip_len = source_len / speed
        on_screen = hide_at - show_at
        inputs += ["-ss", f"{clip_from:.3f}", "-t", f"{source_len:.3f}", "-i", str(VIDEO / "footage" / "run.mp4")]
        filters.append(
            f"[{index}:v]setpts=PTS/{speed},fps=60,scale={FOOTAGE_BOX['w']}:{FOOTAGE_BOX['h']},format=yuva420p,"
            f"tpad=stop_mode=clone:stop_duration={max(0.0, on_screen - clip_len) + 1:.3f},"
            f"trim=duration={on_screen:.3f},"
            f"fade=t=in:st=0:d={REVEAL_S}:alpha=1,fade=t=out:st={on_screen - 0.2:.3f}:d=0.2:alpha=1,"
            f"setpts=PTS-STARTPTS+{show_at:.3f}/TB[clip{index}]"
        )
        filters.append(
            f"[{last}][clip{index}]overlay={FOOTAGE_BOX['x']}:{FOOTAGE_BOX['y']}:"
            f"enable='between(t,{show_at:.3f},{hide_at:.3f})':eof_action=pass[v{index}]"
        )
        last = f"v{index}"
        print(
            f"{scene:10s} {clip_from:.2f}-{clip_from + source_len:.2f} s of the run at {speed}x "
            f"({clip_len:.1f} s), shown {show_at:.2f}-{hide_at:.2f} s"
        )
        if clip_len > on_screen:
            raise SystemExit(f"{scene}: the clip is {clip_len:.1f} s but the scene shows it for {on_screen:.1f} s")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
         "-map", f"[{last}]", "-map", "0:a", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
         "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "copy", "-movflags", "+faststart", str(OUT)],
        check=True,
    )
    length = duration(OUT)
    print(f"wrote {OUT} ({length:.1f} s, {int(length // 60)}:{length % 60:04.1f})")
    if length >= MAX_SECONDS:
        print(f"the video is {length:.1f} s; it must be shorter than {MAX_SECONDS:.0f} s", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
