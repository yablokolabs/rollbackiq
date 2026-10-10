import { defineScene, fact, shot } from "../../components/scene.js";
import approvalUrl from "../../videos/rollbackiq-demo/assets/approval-record.png";

export default defineScene({
	id: "approval",
	advances: [2.4833, 7.2833, 18.3333],
	voiceover:
		"A proposal changes nothing. A named person must approve that exact proposal, by its hash. Then the safety gate runs eighteen checks: the environment, the target release, the approver, the idempotency key. If one check fails, the rollback is refused.",
	html: `
		<div class="rq-scene tight">
			<div>
				<div class="kicker warn">Decide</div>
				<div class="headline small">A person approves one exact proposal.</div>
			</div>
			<div class="stage narrow-wide">
				${shot(approvalUrl, "The incident console, Approval centre: the approval record with actor yablokolabs, decision APPROVED, the proposal hash and how it was recorded", 0, "fit short on-dark")}
				<div class="panel warn" data-beat="1">
					<div class="panel-title">Approval record</div>
					<div class="facts">
						${fact("Approver", "yablokolabs")}
						${fact("Proposal", "70f980983c184108")}
						${fact("Valid for", "900 s")}
						${fact("Gate", "18 of 18 checks", "ok")}
					</div>
					<div class="caption">In this recorded pipeline, the token owner played the approval job through the API.</div>
				</div>
			</div>
			<div class="row" data-beat="2">
				<div class="alert bad">One failed check, and nothing is deployed.</div>
				<span class="chip">environment</span>
				<span class="chip">target release</span>
				<span class="chip">approver</span>
				<span class="chip">idempotency key</span>
			</div>
		</div>
	`,
});
