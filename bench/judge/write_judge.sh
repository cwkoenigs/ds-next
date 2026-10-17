#!/bin/sh
# A blind judge: a separate Claude Code run, in an empty folder outside ~/Developer, sees only the
# ticket and writes hidden acceptance tests. It cannot read the canon, the checks or anything else
# under ~/Developer, and has no shell. Usage: write_judge.sh <task>
set -eu
TASK="$1"; HERE="$(cd "$(dirname "$0")" && pwd)"; DEV="$HOME/Developer"
TICKET="$HERE/../tasks/$TASK/ticket.md"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/judge-$TASK-XXXX")"
PROMPT="You are a careful senior reviewer. Below is a ticket that someone else will implement. Write hidden acceptance tests for it: a single pytest file, test_judge.py, in the current directory, checking what a careful senior reviewer would check before accepting this work, both correctness and robustness.

How the tests reach the implementation: it is a console command whose absolute path is in the environment variable TARGET_BIN. Call it with subprocess; never import the implementation. Use pytest's tmp_path for all files. Each test must be independent. If a test needs git, give it an identity through the environment (for example GIT_CONFIG_GLOBAL pointing to a file you write in tmp_path) rather than relying on the machine's git config. Do not test the implementer's own tests or lint. Do not depend on the exact wording of messages unless the ticket specifies the output format. Aim for 12 to 20 tests. Only write the file; you cannot run anything.

=== TICKET ===
$(cat "$TICKET")
=== END TICKET ==="
(cd "$WORK" && claude -p "$PROMPT" --strict-mcp-config --mcp-config '{"mcpServers": {}}' --setting-sources project \
  --allowedTools Write Edit Read \
  --disallowedTools "Read(/$DEV/**)" "Grep(/$DEV/**)" "Glob(/$DEV/**)" "Edit(/$DEV/**)" "Write(/$DEV/**)" Bash WebFetch WebSearch Task Agent \
  < /dev/null > "$WORK/judge.log" 2>&1) || true
mkdir -p "$HERE/$TASK"
cp "$WORK/test_judge.py" "$HERE/$TASK/test_judge.py"
cp "$WORK/judge.log" "$HERE/$TASK/judge.log"
echo "$TASK: $(grep -c '^def test_\|^    def test_' "$HERE/$TASK/test_judge.py") tests"
