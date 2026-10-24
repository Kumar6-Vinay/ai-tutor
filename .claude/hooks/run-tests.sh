#!/bin/sh
# Stop hook: block the turn from ending while tests fail (exit 2 feeds stderr back to Claude).
# Skips when nothing changed, and after one blocked retry so an unrelated failure can't loop.
input=$(cat)
case "$input" in *'"stop_hook_active":true'*|*'"stop_hook_active": true'*) exit 0 ;; esac
cd "$CLAUDE_PROJECT_DIR" || exit 0
[ -z "$(git status --porcelain 2>/dev/null)" ] && exit 0
out=$(python3 -m pytest -q -x 2>&1) && exit 0
printf '%s\n' "$out" | tail -15 >&2
exit 2
