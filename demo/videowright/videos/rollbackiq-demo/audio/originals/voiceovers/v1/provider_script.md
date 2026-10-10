# Provider Script

> Provider: ElevenLabs (eleven_multilingual_v2)
> Voice: Alice (Xb7hH8MSUJpSbSDYk0k2), British English, female. A premade voice.
> One block for each segment, in timeline order, with a break tag between blocks.
> The text of each block is the `voiceover` field of that segment.

---

A production bug once deleted customer data. Recovery took backups, and a war room. RollbackIQ is a recovery engineer for release regressions, built on GitLab. Its rule is simple: a green rollback job is not success. Measured recovery is.

<break time="0.6s" />

The whole lifecycle is one GitLab pipeline. The build job publishes one image. The deploy job starts version one in a demo staging environment, and measures a healthy baseline from real requests.

<break time="0.6s" />

Now watch it run. This is live output from the same scripts the pipeline jobs use. Version two deploys with an injected fault: the same image, with different configuration. One bad window is not enough. Window one: latency near nine times the baseline. Still no incident. Window two confirms it, and the detector opens an incident with a rollback proposal.

<break time="0.6s" />

A proposal changes nothing. A named person must approve that exact proposal, by its hash. Then the safety gate runs eighteen checks: the environment, the target release, the approver, the idempotency key. If one check fails, the rollback is refused.

<break time="0.6s" />

Here the gate passes, and the rollback puts version one back. But a green job proves nothing. So a separate step measures a new window that starts after the rollback: two hundred requests, over six seconds. Latency is back at the baseline, with zero errors. Recovered, from independent evidence.

<break time="0.6s" />

Then a custom GitLab Duo flow investigates the incident. It is defined in this repository, registered in the AI Catalog, and started by a mention on the incident issue. It has no tool that can deploy or approve. Its note was not flattering. It found three values in our incident record that did not match the artifacts, and it recommended hold and escalate. We corrected the record.

<break time="0.6s" />

In GitLab, the same lifecycle ran on shared runners, and recovery was verified there too. On one host we repeated it five times. Five of five runs recovered, and five healthy controls gave zero false positives.

<break time="0.6s" />

RollbackIQ does not restore deleted data, and it says so. It makes a rollback a decision with evidence: detected by measurement, approved by a person, verified independently. Detect. Decide. Recover.
