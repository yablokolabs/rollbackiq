import { defineScene, fact, shot } from "../../components/scene.js";
import jobUrl from "../../videos/rollbackiq-demo/assets/gitlab-verify-job.png";

export default defineScene({
	id: "evaluation",
	advances: [6.6, 15.3667],
	voiceover:
		"In GitLab, the same lifecycle ran on shared runners, and recovery was verified there too. On one host we repeated it five times. Five of five runs recovered, and five healthy controls gave zero false positives.",
	html: `
		<div class="rq-scene tight">
			<div>
				<div class="kicker">Evidence</div>
				<div class="headline small">Measured in GitLab, and repeated.</div>
			</div>
			<div class="stage wide-narrow">
				${shot(jobUrl, "The log of GitLab job verify:recovery, passed in 57 seconds: recovered=True independent=True reasons=[]", 0, "fit")}
				<div class="panel" data-beat="1">
					<div class="panel-title">Five runs, five healthy controls</div>
					<div class="facts">
						${fact("Recovered and verified", "5 of 5", "ok")}
						${fact("False positives", "0 of 5", "ok")}
						${fact("Tests", "108 passed", "ok")}
					</div>
					<div class="caption">One host and one fault setting. Too few runs to state a rate.</div>
				</div>
			</div>
		</div>
	`,
});
