import "../../styles/rollbackiq/tokens.css";
import type { Timeline } from "videowright";
import defaultAudioTrack from "./audio/tracks/v1/track.js";

const timeline: Timeline = {
	meta: {
		title: "RollbackIQ: detect, decide, recover",
	},
	segments: [
		{ id: "title" },
		{ id: "baseline", transition: "fade" },
		{ id: "regression", transition: "fade" },
		{ id: "approval", transition: "fade" },
		{ id: "recovery", transition: "fade" },
		{ id: "duo", transition: "fade" },
		{ id: "evaluation", transition: "fade" },
		{ id: "outro", transition: "fade" },
	],
	default_audio_track: defaultAudioTrack,
};

export default timeline;
