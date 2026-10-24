#!/bin/sh
# Stop hook: block the turn from ending while tests fail (exit 2 feeds stderr back to Claude).
cd "$CLAUDE_PROJECT_DIR" || exit 0
out=$(python3 -m pytest -q -x 2>&1) && exit 0
printf '%s\n' "$out" | tail -15 >&2
exit 2
