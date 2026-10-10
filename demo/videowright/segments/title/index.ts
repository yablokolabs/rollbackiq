import { arrowIcon, defineScene } from "../../components/scene.js";

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
				<div>
					<div class="wordmark">RollbackIQ</div>
					<div class="lede">A recovery engineer for release regressions, on GitLab</div>
				</div>
			</div>
			<div class="flow" data-beat="1">${flowSteps}</div>
			<div class="promise" data-beat="2">
				A green rollback job is not success. <em>Measured recovery is.</em>
			</div>
		</div>
	`,
});
