import { defineConfig } from "videowright";

/**
 * The demo is delivered at 1920x1080 / 16:9, which is the resolution the
 * competition asks for. 60 fps keeps the text reveals smooth and matches the
 * frame grid the audio timing is snapped to in `scripts/sync_audio.py`, so a
 * rounding error in the render cannot accumulate into audio drift.
 */
export default defineConfig({
  projectStructure: "v1",
  defaultStyle: "rollbackiq",
  defaults: {
    resolution: [1920, 1080],
    fps: 60,
    aspectRatio: "16:9",
  },
});
