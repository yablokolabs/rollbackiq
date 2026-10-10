#!/usr/bin/env bash
#
# Reproduce the CI lifecycle locally, with real containers.
#
# The pipeline's jobs cannot share a container (runners are ephemeral), so each
# job re-establishes its deployment and hands state forward as artifacts. This
# script does the same thing on one host, using the *same* scripts the jobs run —
# nothing here is a demo-only code path:
#
#   deploy v1 + baseline window      scripts/ci_release.py
#   deploy v2 + require detection    scripts/ci_incident.py regress
#   approve one hashed proposal      scripts/ci_incident.py approve
#   evaluate the gate, change nothing scripts/ci_rollback.py --dry-run
#   gated rollback                   scripts/ci_rollback.py
#   independent verification         scripts/ci_release.py verify
#
# Usage:
#   bash scripts/demo_lifecycle_local.sh
#
# Environment overrides: DEMO_IMAGE, DEMO_NETWORK, DEMO_CONTAINER, DEMO_WORKDIR,
# DEMO_ENVIRONMENT, DEMO_PYTHON, DEMO_APPROVER.
#
# The final verification step can legitimately FAIL: if the post-rollback window
# cannot demonstrate stability, the verifier refuses and this script exits
# non-zero. That is the behaviour that matters, not a bug.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

IMAGE="${DEMO_IMAGE:-rollbackiq-workload:local}"
NETWORK="${DEMO_NETWORK:-rollbackiq-local}"
CONTAINER="${DEMO_CONTAINER:-rollbackiq-local-workload}"
ENVIRONMENT="${DEMO_ENVIRONMENT:-demo-staging}"
WORKDIR="${DEMO_WORKDIR:-$REPO_ROOT/evidence/demo-run}"
PY="${DEMO_PYTHON:-$REPO_ROOT/.venv/bin/python}"
APPROVER="${DEMO_APPROVER:-${USER:-$(id -un)}}"
COMMIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo local)"
PIPELINE_ID="local-$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$WORKDIR"

stage() {
  printf '\n>>> %s\n' "$*"
}

say() {
  printf '    %s\n' "$*"
}

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "image $IMAGE not found; build it with:" >&2
  echo "  docker build -t $IMAGE --build-arg RELEASE_VERSION=v1 ./demo/service" >&2
  exit 1
fi

docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK" >/dev/null
# Remove anything left from an earlier attempt so the run starts clean.
"$PY" -u scripts/ci_release.py stop --container "$CONTAINER" --network "$NETWORK" \
  --out "$WORKDIR/cleanup.json" >/dev/null 2>&1 || true

DIGEST="$("$PY" scripts/ci_release.py digest --image "$IMAGE")"

stage "deploy v1 and capture the healthy baseline (the same probe the CI job runs)"
say "image $IMAGE @ ${DIGEST:0:24}…"
"$PY" -u scripts/ci_release.py deploy \
  --image "$IMAGE" --release v1 --container "$CONTAINER" --network "$NETWORK" \
  --environment "$ENVIRONMENT" --commit-sha "$COMMIT_SHA" --pipeline-id "$PIPELINE_ID" \
  --digest "$DIGEST" --out "$WORKDIR/deploy-healthy.json"
"$PY" -u scripts/ci_release.py probe \
  --target "$CONTAINER:8000" --in-container "$IMAGE" --network "$NETWORK" \
  --samples 150 --concurrency 8 --environment "$ENVIRONMENT" \
  --expect-release v1 --expect-healthy --out "$WORKDIR/baseline-window.json"

stage "deploy v2 and require the REAL detector to fire (no detection, no incident)"
"$PY" -u scripts/ci_incident.py regress \
  --image "$IMAGE" --network "$NETWORK" --environment "$ENVIRONMENT" \
  --commit-sha "$COMMIT_SHA" --pipeline-id "$PIPELINE_ID" --digest "$DIGEST" \
  --healthy-commit-sha "$COMMIT_SHA" --healthy-pipeline-id "$PIPELINE_ID" \
  --healthy-digest "$DIGEST" \
  --baseline "$WORKDIR/baseline-window.json" --workdir "$WORKDIR" \
  --deploy-out "$WORKDIR/deploy-regressed.json" \
  --detection-out "$WORKDIR/ci-detection.json" \
  --out "$WORKDIR/incident-bundle.json"

stage "a human approves one exact proposal hash (actor: $APPROVER)"
"$PY" -u scripts/ci_incident.py approve \
  --bundle "$WORKDIR/incident-bundle.json" --actor "$APPROVER" --ttl 900 \
  --note "played by $APPROVER in a local run" --out "$WORKDIR/approval.json"
"$PY" -u scripts/ci_incident.py combine \
  --bundle "$WORKDIR/incident-bundle.json" --approval "$WORKDIR/approval.json" \
  --out "$WORKDIR/incident-bundle-approved.json"

stage "evaluate the safety gate WITHOUT changing anything (dry run)"
"$PY" -u scripts/ci_rollback.py \
  --bundle "$WORKDIR/incident-bundle-approved.json" --image "$IMAGE" \
  --container "$CONTAINER" --network "$NETWORK" --environment "$ENVIRONMENT" \
  --allowed-environments "$ENVIRONMENT" --protected-environments "$ENVIRONMENT" \
  --state "$WORKDIR/rollback-state.json" \
  --out "$WORKDIR/rollback-dryrun.json" --post-window-out "$WORKDIR/rollback-dryrun-window.json" \
  --dry-run

stage "execute the authorized rollback"
"$PY" -u scripts/ci_rollback.py \
  --bundle "$WORKDIR/incident-bundle-approved.json" --image "$IMAGE" \
  --container "$CONTAINER" --network "$NETWORK" --environment "$ENVIRONMENT" \
  --allowed-environments "$ENVIRONMENT" --protected-environments "$ENVIRONMENT" \
  --state "$WORKDIR/rollback-state.json" \
  --out "$WORKDIR/rollback-execution.json" --post-window-out "$WORKDIR/rollback-post-window.json"

stage "independently verify recovery from a NEW window that starts after the rollback"
"$PY" -u scripts/ci_release.py deploy \
  --image "$IMAGE" --release v1 --container "$CONTAINER-verify" --network "$NETWORK" \
  --environment "$ENVIRONMENT" --commit-sha "$COMMIT_SHA" --pipeline-id "$PIPELINE_ID" \
  --digest "$DIGEST" --out "$WORKDIR/deploy-verify.json"
"$PY" -u scripts/ci_release.py probe \
  --target "$CONTAINER-verify:8000" --in-container "$IMAGE" --network "$NETWORK" \
  --samples 200 --concurrency 4 --environment "$ENVIRONMENT" --expect-release v1 \
  --min-duration 6 --out "$WORKDIR/verify-window.json"
"$PY" -u scripts/ci_release.py verify \
  --baseline "$WORKDIR/baseline-window.json" --after "$WORKDIR/verify-window.json" \
  --expected-release v1 --rollback-evidence "$WORKDIR/rollback-execution.json" \
  --out "$WORKDIR/verification.json"

stage "done — artifacts in ${WORKDIR#$REPO_ROOT/}"
ls -1 "$WORKDIR" | sed 's/^/    /'
