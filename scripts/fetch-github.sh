#!/bin/bash
# Fetch a GitHub commit and produce rvoptkb-extract input JSON.
# Requires: gh, jq
#
# Usage:
#   ./scripts/fetch-github.sh <github-commit-url> [-o output-dir]

set -euo pipefail

# ── Help & Usage ─────────────────────────────────────────────────────────────

usage() {
    cat >&2 <<'EOF'
Usage: fetch-github.sh <github-commit-url> [-o OUTPUT_DIR]

Fetch a GitHub commit and produce rvoptkb-extract input JSON.

Requires: gh (GitHub CLI), jq (JSON processor)

Examples:
  fetch-github.sh https://github.com/uxlfoundation/oneDNN/commit/bd984d09...
  fetch-github.sh https://github.com/numpy/numpy/commit/bea458cb... -o ./patches/
EOF
    exit 1
}

# ── Argument Parsing ─────────────────────────────────────────────────────────

[ $# -ge 1 ] || usage

URL="$1"
OUTPUT_DIR="."
if [ "${2:-}" = "-o" ] && [ -n "${3:-}" ]; then
    OUTPUT_DIR="$3"
fi

# ── URL Validation ───────────────────────────────────────────────────────────

if ! [[ "$URL" =~ ^https?://github\.com/([^/]+)/([^/]+)/commit/([0-9a-fA-F]{40})$ ]]; then
    echo "Error: Invalid GitHub commit URL" >&2
    echo "Expected format: https://github.com/{owner}/{repo}/commit/{40-char-SHA}" >&2
    exit 1
fi

OWNER="${BASH_REMATCH[1]}"
REPO="${BASH_REMATCH[2]}"
SHA="${BASH_REMATCH[3],,}"  # lowercase the SHA for consistency

# ── Dependency Check ─────────────────────────────────────────────────────────

if ! command -v gh &>/dev/null; then
    echo "Error: 'gh' (GitHub CLI) is required. Install from https://cli.github.com/" >&2
    exit 1
fi

if ! command -v jq &>/dev/null; then
    echo "Error: 'jq' (JSON processor) is required. Install via your package manager." >&2
    exit 1
fi

# ── Fetch Commit ─────────────────────────────────────────────────────────────

mkdir -p "$OUTPUT_DIR"

echo "Fetching commit ${SHA:0:10} from $OWNER/$REPO..." >&2
GH_STDERR=$(mktemp)
DATA=$(gh api "repos/$OWNER/$REPO/commits/$SHA" \
       --jq '{message: .commit.message, files: [.files[]? | {filename, patch, status}]}' 2>"$GH_STDERR") || {
    GH_ERR=$(cat "$GH_STDERR")
    rm -f "$GH_STDERR"
    echo "Error: Failed to fetch commit." >&2
    echo "  gh output: $GH_ERR" >&2
    echo "  Run 'gh auth status' to check authentication." >&2
    exit 1
}
rm -f "$GH_STDERR"

# Validate response
if [ -z "$DATA" ] || [ "$(echo "$DATA" | jq -r '.message')" = "null" ]; then
    echo "Error: GitHub API returned unexpected response. Check the commit URL." >&2
    exit 1
fi

# ── Extract Fields ───────────────────────────────────────────────────────────

PATCH_SUBJECT=$(echo "$DATA" | jq -r '.message | split("\n") | .[0]')
COMMIT_MESSAGE=$(echo "$DATA" | jq -r '.message')

CODE_DIFF=$(echo "$DATA" | jq -r '
    [.files[]?
    | select(.patch != null)
    | ("diff --git a/" + .filename + " b/" + .filename), .patch]
    | join("\n")
')

if [ -z "$CODE_DIFF" ]; then
    echo "Error: Empty diff -- this commit has no code changes (merge commit or revert)." >&2
    exit 1
fi

# ── Generate Input JSON ─────────────────────────────────────────────────────

INPUT_FILE="${OUTPUT_DIR}/${REPO}_${SHA}_input.json"
OUTPUT_FILE="${OUTPUT_DIR}/${REPO}_${SHA}_output.json"

jq -n \
    --arg ps "$PATCH_SUBJECT" \
    --arg cm "$COMMIT_MESSAGE" \
    --arg cd "$CODE_DIFF" \
    --arg op "$OUTPUT_FILE" \
    '{patch_subject: $ps, commit_message: $cm, code_diff: $cd, output_path: $op}' \
    > "$INPUT_FILE"

# ── Report ────────────────────────────────────────────────────────────────────

echo ""
echo "Input file created: $INPUT_FILE"
echo "Output will be written to: $OUTPUT_FILE"
echo ""
echo "To extract knowledge, invoke the skill:"
echo "  Skill(\"rvoptkb-extract\", \"$INPUT_FILE\")"