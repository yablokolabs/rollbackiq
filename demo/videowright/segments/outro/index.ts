import { defineScene } from "../../components/scene.js";
import logoUrl from "../../videos/rollbackiq-demo/assets/rollbackiq-icon.png";

export default defineScene({
	id: "outro",
	advances: [12.9833, 16.3167],
	voiceover:
		"RollbackIQ does not restore deleted data, and it says so. It makes a rollback a decision with evidence: detected by measurement, approved by a person, verified independently. Detect. Decide. Recover.",
	html: `
		<div class="rq-scene centered">
			<div class="brand" data-beat="0">
				<img class="logo small" src="${logoUrl}" alt="">
				<div>
					<div class="wordmark small">Rollback<span class="iq">IQ</span></div>
					<div class="lede">A code rollback does not restore deleted data.</div>
				</div>
			</div>
			<div class="flow" data-beat="0">
				<div class="flow-step accent">GitLab CI/CD</div>
				<div class="flow-step accent">GitLab Duo Agent Platform</div>
				<div class="flow-step">Docker</div>
			</div>
			<div class="promise" data-beat="1">
				Detect. Decide. <em>Recover.</em>
			</div>
		</div>
	`,
});
