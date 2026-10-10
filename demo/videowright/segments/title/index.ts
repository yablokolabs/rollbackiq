import { arrowIcon, defineScene } from "../../components/scene.js";
import logoUrl from "../../videos/rollbackiq-demo/assets/rollbackiq-icon.png";

const flowSteps = ["DETECT", "DECIDE", "RECOVER"]
	.map((step) => `<div class="flow-step">${step}</div>`)
	.join(`<div class="flow-arrow" aria-hidden="true">${arrowIcon}</div>`);

export default defineScene({
	id: "title",
	advances: [6.1833, 11.75, 18.55],
	voiceover:
		"A production bug once deleted customer data. Recovery took backups, and a war room. RollbackIQ is a recovery engineer for release regressions, built on GitLab. Its rule is simple: a green rollback job is not success. Measured recovery is.",
	html: `
		<div class="rq-scene centered">
			<div class="kicker bad" data-beat="0">A production bug deleted customer data. Recovery took a war room.</div>
			<div class="brand" data-beat="1">
				<img class="logo" src="${logoUrl}" alt="The RollbackIQ icon: a rollback arrow around a health trace">
				<div>
					<div class="wordmark">Rollback<span class="iq">IQ</span></div>
					<div class="lede">A recovery engineer for release regressions</div>
				</div>
			</div>
			<div class="flow" data-beat="1">${flowSteps}</div>
			<div class="promise" data-beat="2">
				A green rollback job is not success. <em>Measured recovery is.</em>
			</div>
		</div>
	`,
});
