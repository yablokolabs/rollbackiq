#!/usr/bin/env python3
"""Build the demo video's subtitles from the narration's own word timing.

The timings come from the provider's per-character alignment, so a subtitle appears
exactly when the words are spoken instead of being estimated from the length of the
text. Video time and audio time are the same timeline here: the render places each
segment at the running total of the previous segments' durations, which is how the
track was built.

Writes both formats, because the SRT is what most players want and the WebVTT is what
an HTML `<track>` wants:

    python3 scripts/build_subtitles.py

Reads videos/rollbackiq-demo/audio/originals/voiceovers/v1/{provider_script.md,timing.json}
and writes ../subtitles/rollbackiq-demo.{srt,vtt}.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
VOICEOVER = PROJECT / "videos" / "rollbackiq-demo" / "audio" / "originals" / "voiceovers" / "v1"
OUT = PROJECT.parent / "videos"

MAX_WORDS = 13  # a cue longer than this is hard to read before it disappears
MAX_CHARS = 88
LEAD_S = 0.05  # a cue appears just before its first word
TAIL_S = 0.30  # and lingers just after its last
WRAP = 44  # characters per subtitle line


def wrap(text: str) -> str:
    words, lines, line = text.split(), [], ""
    for word in words:
        if line and len(line) + 1 + len(word) > WRAP:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return "\n".join(lines)


def chunks(words: list[dict]) -> list[dict]:
    """Group words into readable cues, breaking at sentence ends when possible."""
    cues, current = [], []
    for word in words:
        current.append(word)
        sentence_end = word["word"].endswith((".", "!", "?"))
        long_enough = len(current) >= MAX_WORDS
        wide_enough = sum(len(w["word"]) + 1 for w in current) >= MAX_CHARS
        if long_enough or wide_enough or (sentence_end and len(current) >= 5):
            cues.append(current)
            current = []
    if current:
        cues.append(current)
    return [{"start": c[0]["start"] - LEAD_S, "end": c[-1]["end"] + TAIL_S,
             "text": " ".join(w["word"] for w in c)} for c in cues]


def stamp(seconds: float, comma: bool) -> str:
    ms = max(0, round(seconds * 1000))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    sep = "," if comma else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{ms:03d}"


def main() -> None:
    words = json.loads((VOICEOVER / "timing.json").read_text())["words"]
    script = (VOICEOVER / "provider_script.md").read_text().split("\n---\n", 1)[1]
    blocks = [block.split() for block in re.split(r"<break[^>]*/>", script)]
    if sum(len(block) for block in blocks) != len(words):
        raise SystemExit("timing.json and provider_script.md disagree; run sync_audio.py")

    cues: list[dict] = []
    offset = 0
    for block in blocks:
        cues.extend(chunks(words[offset : offset + len(block)]))
        offset += len(block)

    # A cue must never start before the previous one ends, or players show them stacked.
    for previous, cue in zip(cues, cues[1:]):
        if cue["start"] < previous["end"]:
            cue["start"] = previous["end"]

    OUT.mkdir(parents=True, exist_ok=True)
    srt = "".join(
        f"{index}\n{stamp(cue['start'], True)} --> {stamp(cue['end'], True)}\n{wrap(cue['text'])}\n\n"
        for index, cue in enumerate(cues, start=1)
    )
    (OUT / "rollbackiq-demo.srt").write_text(srt)
    vtt = "WEBVTT\n\n" + "".join(
        f"{stamp(cue['start'], False)} --> {stamp(cue['end'], False)}\n{wrap(cue['text'])}\n\n"
        for cue in cues
    )
    (OUT / "rollbackiq-demo.vtt").write_text(vtt)
    print(f"wrote {len(cues)} cues to {OUT}/rollbackiq-demo.srt and .vtt")


if __name__ == "__main__":
    main()
