#!/usr/bin/env bash
#
# RollbackIQ attribution guard.
#
# Rule (AGENTS.md section 10): never add an AI attribution footer, trailer,
# signature or assistant marker to commits, merge requests, issues,
# documentation, source files, diagrams, release notes or demo scripts.
#
# This script is the single source of truth for the rule. The versioned Git
# hooks in scripts/git-hooks/ and the `attribution-guard` CI job both call it,
# so local checks and CI enforcement cannot drift apart.
#
# Usage:
#   scripts/check_no_attribution.sh [files]           scan the working tree (default)
#   scripts/check_no_attribution.sh staged            scan staged blobs (pre-commit)
#   scripts/check_no_attribution.sh commit-msg FILE   scan one commit message
#   scripts/check_no_attribution.sh range REV         scan commit messages in REV
#   scripts/check_no_attribution.sh patterns          print the forbidden patterns
#
# Exit status: 0 clean, 1 violation(s) found, 2 usage error.
#
# Known limitation: this file defines the forbidden patterns and AGENTS.md
# quotes them as policy, so both are excluded from file scans. Exclusions are
# always reported, never silent.

set -uo pipefail

# --------------------------------------------------------------------------
# Forbidden patterns (case-insensitive extended regex, applied to every file,
# staged blob and commit message).
# --------------------------------------------------------------------------
COMMON_PATTERNS=(
  'co-authored-by'
  'generated-by[[:space:]]*:'
  'assisted-by[[:space:]]*:'
  '(generated|built|written|created|authored|assisted|powered|made)[[:space:]]+(with|by)[[:space:]]+(codebuff|freebuff|claude([[:space:]]+code)?|claude[[:space:]]*\.com|copilot|cursor|aider|chatgpt|openai|anthropic|gemini|gpt|an?[[:space:]]+ai|ai)([^[:alnum:]_-]|$)'
  'claude[[:space:]]+code'
  'claude\.com/claude'
  'anthropic\.com/claude'
  'codebuff'
  'noreply@(codebuff|anthropic|openai|cursor|sourcegraph)\.'
  'ai-generated'
  'ai[[:space:]]+generated[[:space:]]+by'
  'assistant-generated'
  'auto-?generated[[:space:]]+by'
  '🤖'
)

# Extra patterns that only make sense for commit messages: an assistant
# product name on its own, and any classic trailer line.
COMMIT_PATTERNS=(
  'codebuff|freebuff'
  '^[[:space:]]*(co-authored-by|generated-by|assisted-by|signed-off-by|reviewed-by|tested-by|authored-by|contributed-by|made-with|powered-by|built-with|generated-with|ai-assisted)[[:space:]]*:'
)

# Paths that cannot be scanned with the pattern list, with the reason why.
EXCLUDED_PATHS=(
  'AGENTS.md|policy document that quotes the prohibited examples verbatim'
  'scripts/check_no_attribution.sh|this scanner defines the prohibited patterns'
)

RED=''
GREEN=''
YELLOW=''
if [ -t 1 ] && [ "${NO_COLOR:-}" = "" ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
fi
RESET=''
if [ -n "$RED" ]; then RESET=$'\033[0m'; fi

usage() {
  sed -n '13,20p' "$0"
  exit 2
}

repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

exclusion_reason() {
  local rel="$1" entry pattern reason
  for entry in "${EXCLUDED_PATHS[@]}"; do
    pattern="${entry%%|*}"
    reason="${entry#*|}"
    if [ "$rel" = "$pattern" ]; then
      printf '%s' "$reason"
      return 0
    fi
  done
  return 1
}

report_exclusions() {
  local entry pattern reason
  for entry in "${EXCLUDED_PATHS[@]}"; do
    pattern="${entry%%|*}"
    reason="${entry#*|}"
    printf '%s[skip]%s %s (%s)\n' "$YELLOW" "$RESET" "$pattern" "$reason"
  done
}

VIOLATIONS=0
SCANNED=0

flush_violations() {
  local label="$1" output="$2"
  [ -z "$output" ] && return 0
  printf '%sVIOLATION%s in %s\n' "$RED" "$RESET" "$label"
  printf '%s\n' "$output"
  VIOLATIONS=$((VIOLATIONS + 1))
}

scan_file() {
  local file="$1" rel="${1#./}"
  local reason
  if reason=$(exclusion_reason "$rel"); then
    printf '%s[skip]%s %s (%s)\n' "$YELLOW" "$RESET" "$rel" "$reason"
    return 0
  fi
  [ -f "$file" ] || return 0
  local output
  output=$(grep -nIE -i "${GREP_ARGS[@]}" -- "$file" 2>/dev/null) || true
  SCANNED=$((SCANNED + 1))
  flush_violations "$rel" "$output"
}

add_pattern_args() {
  local p
  GREP_ARGS=()
  for p in "${COMMON_PATTERNS[@]}"; do GREP_ARGS+=(-e "$p"); done
}

mode_files() {
  local root; root=$(repo_root)
  cd "$root" || exit 2
  add_pattern_args
  report_exclusions
  echo "--- scanning working tree in $root ---"
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    local file
    while IFS= read -r -d '' file; do
      scan_file "./$file"
    done < <(git ls-files --cached --others --exclude-standard -z)
  else
    local file
    while IFS= read -r -d '' file; do
      scan_file "$file"
    done < <(find . -type f -not -path './.git/*' -print0)
  fi
}

mode_staged() {
  local root; root=$(repo_root)
  cd "$root" || exit 2
  add_pattern_args
  report_exclusions
  echo "--- scanning staged content ---"
  local file rel reason output
  while IFS= read -r -d '' file; do
    rel="$file"
    if reason=$(exclusion_reason "$rel"); then
      printf '%s[skip]%s %s (%s)\n' "$YELLOW" "$RESET" "$rel" "$reason"
      continue
    fi
    output=$(git show ":$file" 2>/dev/null | grep -nIE -i "${GREP_ARGS[@]}") || true
    SCANNED=$((SCANNED + 1))
    flush_violations "$rel (staged)" "$output"
  done < <(git diff --cached --name-only --diff-filter=ACM -z)
}

mode_commit_msg() {
  local msgfile="${1:-}"
  [ -n "$msgfile" ] || usage
  [ -f "$msgfile" ] || { echo "commit-msg: no such file: $msgfile" >&2; exit 2; }
  add_pattern_args
  local p
  for p in "${COMMIT_PATTERNS[@]}"; do GREP_ARGS+=(-e "$p"); done
  local output
  # Git comment lines (starting with #) are stripped before comparing.
  output=$(sed '/^[[:space:]]*#/d' "$msgfile" | grep -nIE -i "${GREP_ARGS[@]}") || true
  SCANNED=$((SCANNED + 1))
  flush_violations "commit message ($msgfile)" "$output"
}

mode_range() {
  local range="${1:-}" rev output
  [ -n "$range" ] || usage
  add_pattern_args
  local p
  for p in "${COMMIT_PATTERNS[@]}"; do GREP_ARGS+=(-e "$p"); done
  while IFS= read -r rev; do
    [ -n "$rev" ] || continue
    output=$(git log -1 --format=%B "$rev" | grep -nIE -i "${GREP_ARGS[@]}") || true
    SCANNED=$((SCANNED + 1))
    flush_violations "commit $rev" "$output"
  done < <(git rev-list "$range" 2>/dev/null)
}

mode_patterns() {
  printf 'Common patterns (files, staged content, commit messages):\n'
  printf '  %s\n' "${COMMON_PATTERNS[@]}"
  printf '\nCommit-message-only patterns:\n'
  printf '  %s\n' "${COMMIT_PATTERNS[@]}"
}

main() {
  local mode="${1:-files}"
  case "$mode" in
    files)     mode_files ;;
    staged)    mode_staged ;;
    commit-msg) shift; mode_commit_msg "${1:-}" ;;
    range)     shift; mode_range "${1:-}" ;;
    patterns)  mode_patterns; exit 0 ;;
    -h|--help|help) usage ;;
    *) echo "unknown mode: $mode" >&2; usage ;;
  esac
  echo
  if [ "$VIOLATIONS" -gt 0 ]; then
    printf '%sattribution guard: FAILED%s — %s violation(s) across %s unit(s) scanned.\n' \
      "$RED" "$RESET" "$VIOLATIONS" "$SCANNED"
    printf 'Remove the attribution footer/trailer before committing. See AGENTS.md section 10.\n'
    exit 1
  fi
  printf '%sattribution guard: clean%s — %s unit(s) scanned, no attribution footers.\n' \
    "$GREEN" "$RESET" "$SCANNED"
  exit 0
}

main "$@"
