#!/usr/bin/env bash
#
# Install the RollbackIQ attribution-guard Git hooks and wire the repo to the
# versioned hooks directory (repo-local configuration only; global Git config
# is never touched, per AGENTS.md section 10).
#
# Usage: scripts/install-git-hooks.sh
set -euo pipefail

root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "install-git-hooks: not inside a Git repository" >&2
  exit 1
}
cd "$root"

chmod +x scripts/check_no_attribution.sh scripts/git-hooks/commit-msg \
         scripts/git-hooks/pre-commit scripts/git-hooks/pre-push \
         scripts/install-git-hooks.sh

git config --local core.hooksPath scripts/git-hooks

echo "Installed attribution-guard hooks (core.hooksPath=scripts/git-hooks):"
echo "  commit-msg  message footer check"
echo "  pre-commit  staged content check"
echo "  pre-push    pushed commit-message range check"
