#!/bin/bash
# install.sh — Install rvoptkb-extract skill for Claude Code
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$HOME/.claude/skills/rvoptkb-extract"
SKILL_FILE="$SKILL_DIR/SKILL.md"
TARGET_FILE="$PROJECT_DIR/skill/SKILL.md"

echo "╔══ Installing rvoptkb-extract ═══════════════════════"
echo "║"
echo "║  Project: $PROJECT_DIR"

# ── Step 1: Verify SKILL.md exists ──────────────────────────────────────────

if [ ! -f "$TARGET_FILE" ]; then
    echo "║  Error: SKILL.md not found at $TARGET_FILE"
    echo "║  Run this script from the project root directory."
    exit 1
fi

# ── Step 2: Create symlink for Claude Code ──────────────────────────────────

mkdir -p "$SKILL_DIR"

if [ -L "$SKILL_FILE" ]; then
    CURRENT_TARGET="$(readlink -f "$SKILL_FILE" 2>/dev/null || readlink "$SKILL_FILE")"
    if [ "$CURRENT_TARGET" = "$TARGET_FILE" ]; then
        echo "║  Symlink already exists and points correctly"
    else
        echo "║  Warning: Existing symlink points to $CURRENT_TARGET"
        echo "║  Updating to $TARGET_FILE"
        ln -sf "$TARGET_FILE" "$SKILL_FILE"
    fi
elif [ -f "$SKILL_FILE" ]; then
    if [ ! -w "$(dirname "$SKILL_FILE")" ]; then
        echo "║  Error: Cannot replace $SKILL_FILE - directory not writable" >&2
        exit 1
    fi
    echo "║  Warning: SKILL.md exists as regular file, replacing with symlink"
    mv "$SKILL_FILE" "$SKILL_FILE.bak"
    ln -s "$TARGET_FILE" "$SKILL_FILE"
    echo "║  Backed up original to $SKILL_FILE.bak"
else
    ln -s "$TARGET_FILE" "$SKILL_FILE"
    echo "║  Created symlink: $SKILL_FILE"
fi

# ── Step 3: Make scripts executable ─────────────────────────────────────────

chmod +x "$PROJECT_DIR/scripts/"*.py "$PROJECT_DIR/scripts/"*.sh 2>/dev/null || true
echo "║  Made scripts executable"

# ── Step 4: Initialize empty idea pool ─────────────────────────────────────

POOL_FILE="$PROJECT_DIR/pool/idea-pool.json"
if [ ! -f "$POOL_FILE" ]; then
    mkdir -p "$PROJECT_DIR/pool"
    cat > "$POOL_FILE" << 'EOF'
{
  "version": "1.0",
  "ideas": []
}
EOF
    echo "║  Initialized empty idea pool"
else
    echo "║  Idea pool already exists ($(python3 -c "import json; print(len(json.load(open('$POOL_FILE'))['ideas']))" 2>/dev/null || echo "?") ideas)"
fi

echo "║"
echo "╚══ Installation Complete ════════════════════════════════"
echo ""
echo "Quick start:"
echo ""
echo "  1. Fetch a commit:"
echo "     $ python3 scripts/fetch-github.py \\"
echo "         https://github.com/uxlfoundation/oneDNN/commit/bd984d09dc5985a19fb427ac46d19d2cbd5558dd \\"
echo "         -o ./"
echo ""
echo "  2. Extract knowledge:"
echo '     Skill("rvoptkb-extract", "data/oneDNN_bd984d09dc5985a19fb427ac46d19d2cbd5558dd_input.json")'
echo ""
echo "  3. Check the pool:"
echo "     $ python3 scripts/check-idea-pool.py --verbose"