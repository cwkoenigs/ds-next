#!/bin/sh
# One task build by headless Claude Code. Usage: build.sh <task> <with|without> <run> [model]
#   with     repo from the canon's python-cli scaffold; the canon reachable through `ds-next mcp`
#   code     as with, but the canon's code comes one function at a time (code_search/get/add)
#   without  repo from `uv init --package`; no canon at all
# Both: ~/Developer is unreadable (canon files, these checks, the references); Bash is uv and git.
# Then scores it with <task>/check.py. Results in runs/<task>-<cond>-<run>/.
set -eu
TASK="$1"; COND="$2"; N="$3"; MODEL="${4:-haiku}"; SPEC="${SPEC:-spec}"
HERE="$(cd "$(dirname "$0")" && pwd)"; DEV="$HOME/Developer"; DSN="$HERE/../../.venv/bin/ds-next"
OUT="$HERE/runs/$SPEC-$TASK-$COND-$N"; rm -rf "$OUT"; mkdir -p "$OUT"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/task-$TASK-$COND-$N-XXXX")"; REPO="$WORK/$TASK"
if [ "$COND" = with ] || [ "$COND" = code ]; then
  printf 'name = "%s"\npurpose = "The %s command."\nscaffold = "python-cli"\nowner = "cwkoenigs"\n' "$TASK" "$TASK" > "$WORK/answers.toml"
  (cd "$WORK" && "$DSN" new "$TASK" --answers answers.toml >/dev/null)
  printf '{"mcpServers": {"ds": {"type": "stdio", "command": "%s", "args": ["mcp"], "env": {"DS_CANON": "%s"}}}}\n' \
    "$DSN" "${DS_CANON:-$DEV/canon}" > "$OUT/mcp.json"
  KB="The team's knowledge base (the \"canon\") is reachable only through the \`ds\` MCP tools: canon_list and canon_read (standards, and gotchas: mistakes already made once), block_list, block_get and block_add (accepted, tested code to reuse instead of writing it), project_status (checks this repo against the canon). Use them."
  MCP="--mcp-config $OUT/mcp.json"; ALLOW_MCP="mcp__ds__canon_list mcp__ds__canon_read mcp__ds__block_list mcp__ds__block_get mcp__ds__block_add mcp__ds__project_status"
  if [ "$COND" = code ]; then
    KB="The team's knowledge base (the \"canon\") is reachable only through the \`ds\` MCP tools: code_search (find accepted, tested functions by what they do), code_get (read one, with only what it needs and its tests), code_add (add them to this repo instead of writing that code), canon_list and canon_read (standards, and gotchas: mistakes already made once), project_status (checks this repo against the canon). Use them."
    ALLOW_MCP="mcp__ds__code_search mcp__ds__code_get mcp__ds__code_add mcp__ds__canon_list mcp__ds__canon_read mcp__ds__project_status"
  fi
else
  (cd "$WORK" && uv init -q --package --name "$TASK" "$TASK" >/dev/null && cd "$TASK" && uv add -q --dev pytest ruff >/dev/null)
  echo '{"mcpServers": {}}' > "$OUT/mcp.json"; KB=""; MCP="--mcp-config $OUT/mcp.json"; ALLOW_MCP=""
fi
echo "$REPO" > "$OUT/repo.txt"
PROMPT="You are building a small Python command from a spec, in the repository you are in. Work only inside it.
$KB
Rules: Bash is limited to \`uv\` and \`git\`; use \`uv run ...\` for Python, pytest and ruff. Install only into this repo's virtualenv (\`uv add\` is fine). Do not commit.

=== SPEC ===
$(cat "$HERE/$TASK/$SPEC.md")
=== END SPEC ===

When you finish, reply with the spec walked item by item (done or not, and how), and the final output of \`uv run pytest -q\` and \`uv run ruff check .\`."
START=$(date +%s)
# shellcheck disable=SC2086
(cd "$REPO" && claude -p "$PROMPT" --model "$MODEL" --output-format stream-json --verbose \
  $MCP --strict-mcp-config --setting-sources project \
  --allowedTools $ALLOW_MCP Read Write Edit Glob Grep TodoWrite "Bash(uv:*)" "Bash(git:*)" \
  --disallowedTools "Read(/$DEV/**)" "Grep(/$DEV/**)" "Glob(/$DEV/**)" "Edit(/$DEV/**)" "Write(/$DEV/**)" \
                    "Bash(ds-next:*)" WebFetch WebSearch Task Agent \
  < /dev/null > "$OUT/build.jsonl" 2>&1) || true
SECS=$(( $(date +%s) - START ))
"$HERE/../../.venv/bin/python" "$HERE/$TASK/check.py" "$REPO" > "$OUT/check.txt" 2>&1 || true
"$HERE/../../.venv/bin/python" - "$OUT" "$TASK" "$COND" "$N" "$MODEL" "$SECS" <<'PYEOF'
import collections, json, re, sys
from pathlib import Path
out, task, cond, n, model, secs = Path(sys.argv[1]), *sys.argv[2:6], int(sys.argv[6])
res = json.loads(re.search(r"^RESULT (.+)$", (out / "check.txt").read_text(), re.M).group(1))
tools, final = collections.Counter(), {}
for line in (out / "build.jsonl").read_text().splitlines():
    try:
        m = json.loads(line)
    except ValueError:
        continue
    if m.get("type") == "assistant":
        tools.update(b["name"] for b in m["message"]["content"] if b.get("type") == "tool_use")
    if m.get("type") == "result":
        final = m
repo = Path(res["repo"])
manifest = repo / ".ds" / "manifest.toml"
blocks = re.findall(r"^\[blocks\.([a-z0-9-]+)\]", manifest.read_text(), re.M) if manifest.exists() else []
summary = {"task": task, "cond": cond, "run": int(n), "model": model, "seconds": secs,
           "turns": final.get("num_turns"), "cost_usd": final.get("total_cost_usd"),
           "behaviour_passed": res["behaviour_passed"], "behaviour_total": res["behaviour_total"],
           "static_ok": not {"uv sync", "its tests pass", "ruff clean"} & set(res["failed"]),
           "failed": res["failed"], "blocks": blocks,
           "kb_calls": {k[9:]: v for k, v in tools.items() if k.startswith("mcp__ds__")},
           "src_lines": sum(len(p.read_text().splitlines()) for p in (repo / "src").rglob("*.py"))}
(out / "result.json").write_text(json.dumps(summary, indent=1))
print(json.dumps(summary))
PYEOF
