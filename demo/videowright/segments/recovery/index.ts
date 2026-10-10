import { defineScene } from "../../components/scene.js";

export default defineScene({
	id: "recovery",
	advances: [6.9333, 13.9667, 20.5833],
	voiceover:
		"Here the gate passes, and the rollback puts version one back. But a green job proves nothing. So a separate step measures a new window that starts after the rollback: two hundred requests, over six seconds. Latency is back at the baseline, with zero errors. Recovered, from independent evidence.",
	html: `
		<div class="rq-scene tight">
			<div>
				<div class="kicker">Recover</div>
				<div class="headline small">A green job proves nothing. A new measurement does.</div>
			</div>
			<div class="footage" data-beat="0" data-footage="recovery"></div>
			<div class="beside-footage">
				<div class="panel" data-beat="0">
					<div class="panel-title">Recorded live</div>
					The gate, the rollback and the verification, from the same run. Shown at 1.25x speed.
				</div>
				<div class="panel" data-beat="1">
					<div class="panel-title">Independent window</div>
					200 requests over 6.01 s. It starts after the rollback executed.
				</div>
				<div class="alert good" data-beat="2">recovered=True independent=True</div>
			</div>
			<div class="source-note">An earlier pipeline run was refused: its window was 1.1 s, shorter than 3.0 s.</div>
		</div>
	`,
});
