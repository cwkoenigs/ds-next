#!/bin/sh
# Prepare a rebuild for a Claude subagent builder: a fresh repo from the python-cli scaffold,
# made by ds-next's deterministic /new code (no model). Usage: claude_prep.sh <run-number>
set -eu
N="$1"; HERE="$(cd "$(dirname "$0")" && pwd)"; DSN="$HERE/../../.venv/bin/ds-next"
NAME="rb-claude-$N"; OUT="$HERE/runs/claude-$N"; mkdir -p "$OUT"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rebuild-claude-$N-XXXX")"
cat > "$WORK/answers.toml" <<TOML
name = "$NAME"
purpose = "A Claude-Code-style terminal over Cortex Code for the team's knowledge system, rebuilt from the canon."
scaffold = "python-cli"
owner = "cwkoenigs"
tags = ["cortex"]
TOML
(cd "$WORK" && "$DSN" new "$NAME" --answers answers.toml >/dev/null)
echo "$WORK/$NAME" > "$OUT/repo.txt"; date +%s > "$OUT/start.txt"
echo "$WORK/$NAME"
