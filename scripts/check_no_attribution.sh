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
# Exit status: 0 clean, 1 violation(s) found, 2 usage or environment error.
#
# A failing git command is always a hard error (exit 2): scanning zero units
# because git refused to run must never be reported as a clean result.
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

VIOLATIONS=0
SCANNED=0
GREP_ARGS=()
TMP_DIR=""

usage() {
  sed -n '13,22p' "$0"
  exit 2
}

cleanup() {
  [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ] && rm -rf "$TMP_DIR"
  return 0
}
trap cleanup EXIT

fail() {
  printf '%sattribution guard: ERROR%s — %s\n' "$RED" "$RESET" "$*" >&2
  exit 2
}

# Run git, writing stdout to $1; any failure is fatal so a broken git call can
# never be mistaken for "nothing to scan".
git_to_file() {
  local out="$1"; shift
  if ! git "$@" >"$out" 2>"$out.err"; then
    printf '%sattribution guard: ERROR%s — git %s failed:\n' "$RED" "$RESET" "$*" >&2
    sed 's/^/  /' "$out.err" >&2
    printf 'Refusing to report a clean scan from a failed git command.\n' >&2
    exit 2
  fi
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

add_pattern_args() {
  local p
  GREP_ARGS=()
  for p in "${COMMON_PATTERNS[@]}"; do GREP_ARGS+=(-e "$p"); done
}

add_commit_pattern_args() {
  local p
  for p in "${COMMIT_PATTERNS[@]}"; do GREP_ARGS+=(-e "$p"); done
}

flush_violations() {
  local label="$1" output="$2"
  [ -z "$output" ] && return 0
  printf '%sVIOLATION%s in %s\n' "$RED" "$RESET" "$label"
  printf '%s\n' "$output"
  VIOLATIONS=$((VIOLATIONS + 1))
}

scan_file() {
  local file="$1" rel="${1#./}"
  local reason output
  if reason=$(exclusion_reason "$rel"); then
    printf '%s[skip]%s %s (%s)\n' "$YELLOW" "$RESET" "$rel" "$reason"
    return 0
  fi
  [ -f "$file" ] || return 0
  output=$(grep -nIE -i "${GREP_ARGS[@]}" -- "$file" 2>/dev/null) || true
  SCANNED=$((SCANNED + 1))
  flush_violations "$rel" "$output"
}

mode_files() {
  local root inside_git=0 gerr
  root=$(repo_root)
  cd "$root" || exit 2
  add_pattern_args
  report_exclusions
  echo "--- scanning working tree in $root ---"

  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    inside_git=1
  elif [ -e .git ]; then
    # A .git directory exists but git refuses to use it (for example the
    # "dubious ownership" check). Falling back to find here would report a
    # clean tree from a repository the guard could not actually read, so fail.
    gerr=$(git rev-parse --is-inside-work-tree 2>&1 | head -3)
    fail "a .git directory is present but git cannot read this repository:
$gerr"
  fi

  local file
  if [ "$inside_git" -eq 1 ]; then
    TMP_DIR=$(mktemp -d) || fail "cannot create a temporary directory"
    git_to_file "$TMP_DIR/files" ls-files --cached --others --exclude-standard -z
    while IFS= read -r -d '' file; do
      scan_file "./$file"
    done < "$TMP_DIR/files"
  else
    echo "(not a git repository: scanning all files under $root)"
    while IFS= read -r -d '' file; do
      scan_file "$file"
    done < <(find . -type f -not -path './.git/*' -print0)
  fi
}

mode_staged() {
  local root reason output file
  root=$(repo_root)
  cd "$root" || exit 2
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || fail "not a git repository: staged mode requires git"
  add_pattern_args
  report_exclusions
  echo "--- scanning staged content ---"

  TMP_DIR=$(mktemp -d) || fail "cannot create a temporary directory"
  git_to_file "$TMP_DIR/staged" diff --cached --name-only --diff-filter=ACM -z
  while IFS= read -r -d '' file; do
    if reason=$(exclusion_reason "$file"); then
      printf '%s[skip]%s %s (%s)\n' "$YELLOW" "$RESET" "$file" "$reason"
      continue
    fi
    git_to_file "$TMP_DIR/blob" show ":$file"
    output=$(grep -nIE -i "${GREP_ARGS[@]}" "$TMP_DIR/blob") || true
    SCANNED=$((SCANNED + 1))
    flush_violations "$file (staged)" "$output"
  done < "$TMP_DIR/staged"
}

mode_commit_msg() {
  local msgfile="${1:-}"
  [ -n "$msgfile" ] || usage
  [ -f "$msgfile" ] || fail "commit-msg: no such file: $msgfile"
  add_pattern_args
  add_commit_pattern_args
  local output
  # Git comment lines (starting with #) are stripped before comparing.
  output=$(sed '/^[[:space:]]*#/d' "$msgfile" | grep -nIE -i "${GREP_ARGS[@]}") || true
  SCANNED=$((SCANNED + 1))
  flush_violations "commit message ($msgfile)" "$output"
}

mode_range() {
  local range="${1:-}" rev output commits=0
  [ -n "$range" ] || usage
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || fail "not a git repository: range mode requires git"
  add_pattern_args
  add_commit_pattern_args

  TMP_DIR=$(mktemp -d) || fail "cannot create a temporary directory"
  git_to_file "$TMP_DIR/revs" rev-list "$range"
  while IFS= read -r rev; do
    [ -n "$rev" ] || continue
    commits=$((commits + 1))
    git_to_file "$TMP_DIR/msg" log -1 --format=%B "$rev"
    output=$(grep -nIE -i "${GREP_ARGS[@]}" "$TMP_DIR/msg") || true
    SCANNED=$((SCANNED + 1))
    flush_violations "commit $rev" "$output"
  done < "$TMP_DIR/revs"
  echo "(scanned $commits commit message(s) in range: $range)"
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
    *) fail "unknown mode: $mode (try --help)" ;;
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
