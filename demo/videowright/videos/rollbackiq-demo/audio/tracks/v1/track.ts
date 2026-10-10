import type { AudioTrack } from "videowright";

// Written by scripts/sync_audio.py. Each array holds segment-relative seconds: one
// entry for each reveal after the first, then the end of the segment.
const track: AudioTrack = {
	audio_file: "./audio/tracks/v1/track.mp3",
	length_s: 155.79,
	timing: {
		perSegment: {
			title: [6.1833, 11.75, 18.55],
			baseline: [5.9667, 13.75],
			regression: [6, 20.75, 26.7],
			approval: [2.4833, 7.2833, 18.3333],
			recovery: [6.9333, 13.9667, 20.5833],
			duo: [11.95, 17.5667, 26.8],
			evaluation: [6.6, 15.3667],
			outro: [12.9833, 16.3167],
		},
	},
	audio_plan_path: "../../audio_plan.md",
	plan_snapshot_path: "./plan_snapshot.md",
	created_at: "2026-10-10T19:29:04Z",
};

export default track;
