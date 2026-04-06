#!/bin/bash
# Installs git hooks for the ApiChain Backend repository.
# Run once after cloning: bash .claude/setup-hooks.sh

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)

if [ -z "$REPO_ROOT" ]; then
    echo "Error: Not inside a git repository."
    exit 1
fi

HOOKS_SRC="$REPO_ROOT/.claude/hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

if [ ! -d "$HOOKS_SRC" ]; then
    echo "Error: .claude/hooks/ directory not found."
    exit 1
fi

# Install post-merge hook
if [ -f "$HOOKS_SRC/post-merge" ]; then
    cp "$HOOKS_SRC/post-merge" "$HOOKS_DST/post-merge"
    chmod +x "$HOOKS_DST/post-merge"
    echo "Installed: post-merge hook"
else
    echo "Warning: post-merge hook template not found in .claude/hooks/"
fi

echo ""
echo "Git hooks installed successfully."
echo "The post-merge hook will auto-update .claude/CLAUDE.md after every git pull."
