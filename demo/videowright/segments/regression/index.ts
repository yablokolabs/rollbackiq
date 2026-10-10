import { defineScene } from "../../components/scene.js";

export default defineScene({
	id: "regression",
	advances: [6, 20.75, 26.7],
	voiceover:
		"Now watch it run. This is live output from the same scripts the pipeline jobs use. Version two deploys with an injected fault: the same image, with different configuration. One bad window is not enough. Window one: latency near nine times the baseline. Still no incident. Window two confirms it, and the detector opens an incident with a rollback proposal.",
	html: `
		<div class="rq-scene tight">
			<div>
				<div class="kicker bad">Detect</div>
				<div class="headline small">One bad window is not enough.</div>
			</div>
			<div class="footage" data-beat="1" data-footage="regression"></div>
			<div class="beside-footage">
				<div class="panel" data-beat="0">
					<div class="panel-title">Recorded live</div>
					A real run on one host, with real containers. The same scripts as the pipeline jobs.
				</div>
				<div class="panel" data-beat="1">
					<div class="panel-title">The fault</div>
					Injected deployment configuration. v1 and v2 are the same image.
				</div>
				<div class="alert bad" data-beat="2">Incident opened: P95_LATENCY, ERROR_RATE</div>
			</div>
			<div class="source-note">Rule: p95 above 3.0x the baseline, or errors above 5%, on two windows in sequence.</div>
		</div>
	`,
});
