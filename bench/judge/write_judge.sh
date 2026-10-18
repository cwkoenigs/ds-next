#!/bin/sh
# A blind judge: a separate Claude Code run, in an empty folder outside ~/Developer, sees only the
# ticket and writes hidden acceptance tests. It cannot read the canon, the checks or anything else
# under ~/Developer, and has no shell. Usage: write_judge.sh <task> [model] [min-max tests]
set -eu
TASK="$1"; MODEL="${2:-opus}"; RANGE="${3:-30 to 45}"
HERE="$(cd "$(dirname "$0")" && pwd)"; DEV="$HOME/Developer"
TICKET="$HERE/../tasks/$TASK/ticket.md"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/judge-$TASK-XXXX")"
PROMPT="You are a careful, adversarial senior reviewer. Below is a ticket that someone else will implement. Write hidden acceptance tests for it: a single pytest file, test_judge.py, in the current directory. Test what a careful senior reviewer would check before accepting this work, and then try to break it: tricky but legal inputs, ordering and partial-failure behaviour the ticket implies, idempotent re-runs, path handling (relative paths, nested folders, links with .. and anchors), non-ASCII text, empty and malformed inputs, exit codes and output formats the ticket specifies.

Rules:
- Test only what the ticket specifies or clearly implies. Where the ticket leaves behaviour open, do not test it.
- Do not depend on the exact wording of messages unless the ticket specifies the format.
- The implementation is a console command whose absolute path is in the environment variable TARGET_BIN. Call it with subprocess; never import it.
- Use pytest's tmp_path for all files. Each test must be independent and deterministic, and must run on macOS and Linux.
- If a test needs git, give it an identity through the environment (for example GIT_CONFIG_GLOBAL pointing to a file you write in tmp_path) rather than relying on the machine's git config.
- Do not test the implementer's own tests or lint.
- Aim for $RANGE tests; use parametrize where it adds cases cheaply. Write small helpers so the tests stay readable.
- Only write the file; you cannot run anything, so keep each test simple enough to be right the first time.

=== TICKET ===
$(cat "$TICKET")
=== END TICKET ==="
(cd "$WORK" && claude -p "$PROMPT" --model "$MODEL" --strict-mcp-config --mcp-config '{"mcpServers": {}}' --setting-sources project \
  --allowedTools Write Edit Read \
  --disallowedTools "Read(/$DEV/**)" "Grep(/$DEV/**)" "Glob(/$DEV/**)" "Edit(/$DEV/**)" "Write(/$DEV/**)" Bash WebFetch WebSearch Task Agent \
  < /dev/null > "$WORK/judge.log" 2>&1) || true
mkdir -p "$HERE/$TASK"
cp "$WORK/test_judge.py" "$HERE/$TASK/test_judge.py"
cp "$WORK/judge.log" "$HERE/$TASK/judge.log"
echo "$TASK: $(grep -c '^def test_\|^    def test_' "$HERE/$TASK/test_judge.py") test functions ($MODEL)"
