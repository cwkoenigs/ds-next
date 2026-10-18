#!/bin/sh
# One build for the honest test. Usage: run.sh <task> <without|lessons|lib|both|code> <run> [model]
# Every arm starts from the same `uv init --package` repo and the same ticket; only the knowledge differs.
#   without  nothing but the ticket
#   lessons  the canon's gotchas and standards, copied beside the repo (no code)
#   lib      canon-lib, the accepted code as one package, copied beside the repo (no lessons)
#   both     lessons + lib  ("with" in the first round)
#   code     the function library over MCP: code_search/code_get/code_add, plus canon_list/canon_read
# ~/Developer is unreadable to the builder (the judge's tests, my checks, the references).
# Scored by the blind judge's tests (score.py). RUN_LABEL names the run directory (default: the arm);
# DS_CANON points at the canon to use.
set -eu
TASK="$1"; COND="$2"; N="$3"; MODEL="${4:-haiku}"
[ "$COND" = with ] && COND=both
HERE="$(cd "$(dirname "$0")" && pwd)"; DEV="$HOME/Developer"; CANON="${DS_CANON:-$DEV/canon}"
OUT="$HERE/runs/$TASK-${RUN_LABEL:-$COND}-$N"; rm -rf "$OUT"; mkdir -p "$OUT"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/honest-$TASK-$COND-$N-XXXX")"; REPO="$WORK/$TASK"
(cd "$WORK" && uv init -q --package --name "$TASK" "$TASK" >/dev/null && cd "$TASK" && uv add -q --dev pytest ruff >/dev/null)
ARM="$COND"; COPY=1; . "$HERE/arms.sh"
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
  --strict-mcp-config --mcp-config "$MCPCFG" --setting-sources project \
  --allowedTools $ALLOW Read Write Edit Glob Grep TodoWrite "Bash(uv:*)" "Bash(git:*)" \
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
res = {**s, "cond": cond, "label": __import__("os").environ.get("RUN_LABEL", cond), "run": n, "model": model, "seconds": secs, "cost_usd": final.get("total_cost_usd"),
       "turns": final.get("num_turns")}
(out / "result.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res))
PYEOF
