#!/bin/sh
# One rebuild by headless Claude Code that reaches the canon only through `ds-next mcp`.
# ~/Developer is unreadable to it (canon files, ds-next, earlier rebuilds); Bash is uv and git.
# Usage: claude_mcp_build.sh <run-number>. Then scores it with the fake cortex.
set -eu
N="$1"; HERE="$(cd "$(dirname "$0")" && pwd)"; DEV="$HOME/Developer"
REPO="$("$HERE/claude_prep.sh" "$N")"; OUT="$HERE/runs/claude-$N"
CFG="$OUT/mcp.json"
printf '{"mcpServers": {"ds": {"type": "stdio", "command": "%s", "args": ["mcp"], "env": {"DS_CANON": "%s"}}}}\n' \
  "$HERE/../../.venv/bin/ds-next" "${DS_CANON:-$DEV/canon}" > "$CFG"
PROMPT="$(cat "$HERE/builder_head.md"; echo "=== SPEC (verbatim) ==="; cat "$HERE/spec.md"; cat "$HERE/builder_tail.md")"
(cd "$REPO" && claude -p "$PROMPT" --output-format stream-json --verbose \
  --mcp-config "$CFG" --strict-mcp-config --setting-sources project \
  --allowedTools mcp__ds__canon_list mcp__ds__canon_read mcp__ds__block_list mcp__ds__block_get mcp__ds__block_add \
                 mcp__ds__scaffold_list mcp__ds__scaffold_get mcp__ds__project_status \
                 Read Write Edit Glob Grep TodoWrite "Bash(uv:*)" "Bash(git:*)" \
  --disallowedTools "Read(/$DEV/**)" "Grep(/$DEV/**)" "Glob(/$DEV/**)" "Edit(/$DEV/**)" "Write(/$DEV/**)" \
                    "Bash(ds-next:*)" "Bash(cortex:*)" WebFetch WebSearch Task Agent \
  < /dev/null > "$OUT/build.jsonl" 2>&1) || true
"$HERE/claude_score.sh" "$N"
