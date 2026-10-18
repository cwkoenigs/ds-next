#!/bin/sh
# The maintenance test: apply the change ticket to a repo built in round 2, with the same knowledge
# access its arm had, then score it twice: the original judge (regressions) and the change judge.
# Also measures how much of src/ and tests/ changed against the snapshot in runs/<task>-<arm>-<n>/before.
# Usage: change.sh <without|lessons|lib|both|code> <n> [model]
set -eu
ARM="$1"; N="$2"; MODEL="${3:-haiku}"; TASK=publish; CHANGE=publish-change
HERE="$(cd "$(dirname "$0")" && pwd)"; DEV="$HOME/Developer"; CANON="${DS_CANON:-$DEV/canon}"
SRC="$HERE/runs/$TASK-$ARM-$N"; REPO="$(cat "$SRC/repo.txt")"; WORK="$(dirname "$REPO")"
[ -d "$SRC/before" ] || { echo "no snapshot in $SRC/before" >&2; exit 2; }
OUT="$HERE/runs/$CHANGE-$ARM-$N"; rm -rf "$OUT"; mkdir -p "$OUT"; echo "$REPO" > "$OUT/repo.txt"
COPY=0; . "$HERE/arms.sh"
PROMPT="You are changing an existing small Python command in the repository you are in, from a change request. Work only inside it. Read the code and its tests before you change anything.
$KB
Bash is limited to \`uv\` and \`git\`; use \`uv run ...\` for Python, pytest and ruff. Do not commit.

=== TICKET ===
$(cat "$HERE/../tasks/$CHANGE/ticket.md")
=== END TICKET ===

When you finish, reply with what you changed and the final output of \`uv run pytest -q\` and \`uv run ruff check .\`."
START=$(date +%s)
# shellcheck disable=SC2086
(cd "$REPO" && claude -p "$PROMPT" --model "$MODEL" --output-format stream-json --verbose $ADD \
  --strict-mcp-config --mcp-config "$MCPCFG" --setting-sources project \
  --allowedTools $ALLOW Read Write Edit Glob Grep TodoWrite "Bash(uv:*)" "Bash(git:*)" \
  --disallowedTools "Read(/$DEV/**)" "Grep(/$DEV/**)" "Glob(/$DEV/**)" "Edit(/$DEV/**)" "Write(/$DEV/**)" \
                    WebFetch WebSearch Task Agent \
  < /dev/null > "$OUT/build.jsonl" 2>&1) || true
SECS=$(( $(date +%s) - START ))
PY="$HERE/../../.venv/bin/python"
"$PY" "$HERE/score.py" "$TASK" "$REPO" > "$OUT/score_old.json" 2>"$OUT/score.err" || true
"$PY" "$HERE/score.py" "$CHANGE" "$REPO" "$TASK" > "$OUT/score_new.json" 2>>"$OUT/score.err" || true
"$PY" - "$OUT" "$SRC/before" "$REPO" "$ARM" "$N" "$MODEL" "$SECS" <<'PYEOF'
import json, subprocess, sys
from pathlib import Path
out, before, repo, arm, n, model, secs = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], int(sys.argv[5]), sys.argv[6], int(sys.argv[7])
def changed(sub):
    r = subprocess.run(["diff", "-rN", "-x", "__pycache__", str(before / sub), str(repo / sub)], capture_output=True, text=True, check=False)
    return sum(1 for ln in r.stdout.splitlines() if ln[:1] in "<>")
old = json.loads((out / "score_old.json").read_text() or "{}"); new = json.loads((out / "score_new.json").read_text() or "{}")
final = {}
for line in (out / "build.jsonl").read_text().splitlines():
    try:
        m = json.loads(line)
    except ValueError:
        continue
    if m.get("type") == "result":
        final = m
res = {"task": "publish-change", "arm": arm, "run": n, "model": model, "seconds": secs,
       "regression_passed": old.get("passed"), "regression_total": old.get("total"), "regression_failed": old.get("failed"),
       "change_passed": new.get("passed"), "change_total": new.get("total"), "change_failed": new.get("failed"),
       "canon_lib": new.get("canon_lib"), "code_add": new.get("code_add"), "own_lines": new.get("own_lines"),
       "src_lines_changed": changed("src"), "test_lines_changed": changed("tests"),
       "cost_usd": final.get("total_cost_usd"), "turns": final.get("num_turns")}
(out / "result.json").write_text(json.dumps(res, indent=1)); print(json.dumps(res))
PYEOF
