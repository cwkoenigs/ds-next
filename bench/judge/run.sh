#!/bin/sh
# One build for the honest test. Usage: run.sh <task> <with|without> <run> [model]
# Both start from `uv init --package`. "with" also gets a copy of the canon beside the repo: its
# lessons (gotchas and standards) and canon-lib. Nothing else differs. ~/Developer is unreadable to
# the builder (the judge's tests, my checks, the references). Scored by the blind judge's tests.
set -eu
TASK="$1"; COND="$2"; N="$3"; MODEL="${4:-haiku}"
HERE="$(cd "$(dirname "$0")" && pwd)"; DEV="$HOME/Developer"; CANON="${DS_CANON:-$DEV/canon}"
OUT="$HERE/runs/$TASK-$COND-$N"; rm -rf "$OUT"; mkdir -p "$OUT"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/honest-$TASK-$COND-$N-XXXX")"; REPO="$WORK/$TASK"
(cd "$WORK" && uv init -q --package --name "$TASK" "$TASK" >/dev/null && cd "$TASK" && uv add -q --dev pytest ruff >/dev/null)
KB=""; ADD=""
if [ "$COND" = with ]; then
  mkdir -p "$WORK/canon"
  cp -R "$CANON/gotchas" "$WORK/canon/"; cp "$CANON"/*.md "$WORK/canon/"
  [ -d "$CANON/adr" ] && cp -R "$CANON/adr" "$WORK/canon/"
  rsync -a --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache "$CANON/lib" "$WORK/canon/"
  KB="Your team's knowledge base is at $WORK/canon. It has lessons: gotchas/*.md are mistakes already made once and the rules that prevent them; the other *.md files are standards. And it has canon-lib (lib/), the team's accepted, tested code: add it with \`uv add --editable $WORK/canon/lib\` and import from canon_lib instead of writing that code yourself (lib/src/canon_lib/__init__.py lists the modules). Read the lessons that apply before you start."
  ADD="--add-dir $WORK/canon"
fi
echo "$REPO" > "$OUT/repo.txt"
PROMPT="You are building a small Python command from a ticket, in the repository you are in. Work only inside it.
$KB
Bash is limited to \`uv\` and \`git\`; use \`uv run ...\` for Python, pytest and ruff. Do not commit.

=== TICKET ===
$(cat "$HERE/../tasks/$TASK/ticket.md")
=== END TICKET ===

When you finish, reply with what you built and the final output of \`uv run pytest -q\` and \`uv run ruff check .\`."
START=$(date +%s)
# shellcheck disable=SC2086
(cd "$REPO" && claude -p "$PROMPT" --model "$MODEL" --output-format stream-json --verbose $ADD \
  --strict-mcp-config --mcp-config '{"mcpServers": {}}' --setting-sources project \
  --allowedTools Read Write Edit Glob Grep TodoWrite "Bash(uv:*)" "Bash(git:*)" \
  --disallowedTools "Read(/$DEV/**)" "Grep(/$DEV/**)" "Glob(/$DEV/**)" "Edit(/$DEV/**)" "Write(/$DEV/**)" \
                    WebFetch WebSearch Task Agent \
  < /dev/null > "$OUT/build.jsonl" 2>&1) || true
SECS=$(( $(date +%s) - START ))
"$HERE/../../.venv/bin/python" "$HERE/score.py" "$TASK" "$REPO" > "$OUT/score.json" 2>"$OUT/score.err" || true
"$HERE/../../.venv/bin/python" - "$OUT" "$COND" "$N" "$MODEL" "$SECS" <<'PYEOF'
import json, sys
from pathlib import Path
out, cond, n, model, secs = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4], int(sys.argv[5])
s = json.loads((out / "score.json").read_text() or "{}")
final = {}
for line in (out / "build.jsonl").read_text().splitlines():
    try:
        m = json.loads(line)
    except ValueError:
        continue
    if m.get("type") == "result":
        final = m
res = {**s, "cond": cond, "run": n, "model": model, "seconds": secs, "cost_usd": final.get("total_cost_usd"),
       "turns": final.get("num_turns")}
(out / "result.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res))
PYEOF
