import { defineScene, fact, shot } from "../../components/scene.js";
import pipelineUrl from "../../videos/rollbackiq-demo/assets/gitlab-pipeline.png";

export default defineScene({
	id: "baseline",
	advances: [5.9667, 13.75],
	voiceover:
		"The whole lifecycle is one GitLab pipeline. The build job publishes one image. The deploy job starts version one in a demo staging environment, and measures a healthy baseline from real requests.",
	html: `
		<div class="rq-scene tight">
			<div>
				<div class="kicker">GitLab CI/CD</div>
				<div class="headline small">One pipeline carries the whole lifecycle.</div>
			</div>
			<div class="stage wide-narrow">
				${shot(pipelineUrl, "GitLab pipeline 2932808602, passed: attribution-guard, build:workload-image, deploy:staging, deploy:regressed, approval:grant, rollback:managed and verify:recovery", 0, "fit")}
				<div class="panel" data-beat="1">
					<div class="panel-title">Healthy baseline, v1</div>
					<div class="facts">
						${fact("Requests", "150")}
						${fact("Errors", "0", "ok")}
						${fact("p95", "27.2 ms", "ok")}
						${fact("Runner", "GitLab.com shared")}
					</div>
					<div class="caption">Pipeline 2932808602. One image; a release is a set of deployment inputs.</div>
				</div>
			</div>
		</div>
	`,
});
