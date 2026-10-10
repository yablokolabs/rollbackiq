import { defineScene, fact, shot } from "../../components/scene.js";
import noteUrl from "../../videos/rollbackiq-demo/assets/gitlab-duo-note.png";

export default defineScene({
	id: "duo",
	advances: [11.95, 17.5667, 26.8],
	voiceover:
		"Then a custom GitLab Duo flow investigates the incident. It is defined in this repository, registered in the AI Catalog, and started by a mention on the incident issue. It has no tool that can deploy or approve. Its note was not flattering. It found three values in our incident record that did not match the artifacts, and it recommended hold and escalate. We corrected the record.",
	html: `
		<div class="rq-scene tight">
			<div>
				<div class="kicker">GitLab Duo Agent Platform</div>
				<div class="headline small">A custom Duo flow investigates. It cannot deploy.</div>
			</div>
			<div class="stage wide-narrow">
				${shot(noteUrl, "Incident issue 2 on GitLab: the note posted by the RollbackIQ Recovery Investigator flow, with supported and contradicted hypotheses, discrepancies, and the recommendation hold and escalate", 0, "fit")}
				<div class="panel" data-beat="1">
					<div class="panel-title">Session 9288744</div>
					<div class="facts">
						${fact("Catalog flow", "1016482")}
						${fact("Trigger", "mention")}
						${fact("Status", "FINISHED", "ok")}
						${fact("Deploy tools", "none", "ok")}
					</div>
				</div>
			</div>
			<div class="row" data-beat="2">
				<div class="alert warn">Recommendation: HOLD, and ESCALATE the data question.</div>
				<span class="chip">3 record values corrected</span>
			</div>
		</div>
	`,
});
