# GitLab Duo reviewed my recovery agent four ways. It was right every time, and I was wrong once.

_Draft for a community post. Written for the GitLab Transcend hackathon, Path A. Every number
below is in the repository:
https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43178176/showcase_

## What I built

RollbackIQ handles one situation: a release makes a service slower or makes it fail, and
somebody must decide to roll back. The usual ending is a rollback job that turns green, and a
team that relaxes. Nobody measured whether the service recovered.

So the whole lifecycle runs in one GitLab CI/CD pipeline, and the last job is the one that
matters. It deploys the target release again and measures a **new** window of requests that
starts after the rollback. Recovery is declared only from that window. On one early run the
window was 1.1 seconds long, and the verifier refused to call it recovery. The pipeline failed,
and that failed job is still in the repository as evidence. I am more proud of that red job than
of the green ones.

A person approves each rollback, by the hash of one exact proposal, in a manual pipeline job.
Then a safety gate runs 18 checks. The agent cannot deploy, approve or roll back; it has no tool
for it.

## 1. A custom Duo flow audited my incident record

I defined a custom agent and a custom flow in the repository, registered them in the AI Catalog,
and started the flow with a mention on the incident issue. I expected a summary. I got an audit.

The flow refused to accept "recovery verified", because it could not retrieve the verification
artifact itself. Then it listed three values in my incident record that did not match the
pipeline artifacts: a latency ratio, a proposal hash and an image digest. All three were my
copying errors. It recommended HOLD and ESCALATE, because nothing in the evidence showed whether
the failed requests had damaged data.

I corrected the record. An agent that disagrees with its operator on the evidence is worth more
than one that agrees.

## 2. Duo Code Review found three defects in the first merge request

I asked for a review with `/request_review @GitLabDuo`. Three findings, all correct:

- The incident timeline sorted timestamps as text. The artifacts mix two formats, so the console
  listed the baseline measurement before the deployment it measured. My test could not see it,
  because it compared the output with a text sort of itself.
- One timeline line said "target release v1" as fixed text, in a module whose rule is to invent
  nothing.
- Two npm scripts pointed at files that did not exist.

After the fixes I requested a re-review, and it was clean. Later it caught a statement in my
compliance table that claimed more than I had verified. The reviews also say plainly when they
saw only part of a large diff, which I appreciated.

## 3. SAST found a real defect on its first run

I added GitLab's SAST and secret detection templates late. Secret detection found nothing. SAST
reported six findings. Five were the same pattern, and three of those were not reachable. But
one real defect produced the other two: my probe took its whole URL from the command line, and
`urllib` also opens `file://`. The probe produces the evidence for detection and for recovery, so it must measure an
HTTP service and nothing else. Now it refuses any other scheme.

The scanner still reports those two calls, because it matches the pattern and not the check
before it. I left them visible and wrote down what I did with each finding.

## 4. The bug I almost reported

Early in the project my trigger sessions failed, and I decided that the catalog API was at
fault: I wrote, in several documents, that updating a flow without a version bump "returns no
errors and changes nothing".

Before I reported it to GitLab, I reproduced it. It was not true. The update made a new
released version with the new definition. The version history had shown it all along. The
defects were in my flow definition.

I withdrew the claim everywhere and kept the reproduction as evidence. The lesson is an old one:
reproduce it before you report it. It cost ten minutes, and it saved a maintainer's time and my
credibility.

## What I take from this

- Give the agent the evidence, and no power. Mine can read and recommend. It cannot act.
- Keep the refusals. A failed verification job is better evidence than a passed one.
- Let the tools disagree with you. The flow, the code review and the scanner each found
  something that I had missed.
- Write down what you did not verify. It is the part that readers trust most.

RollbackIQ does not restore deleted data, and its fault is injected configuration on one image,
not a code regression. The repository says so next to every set of numbers.

Video (2:36): https://youtu.be/rvs6M7xOTR0
