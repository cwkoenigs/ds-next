#!/bin/sh
# One controlled rebuild run. Usage: run.sh <with|without> <run-number>
#   with     the agent builds against the canon as it is (gotchas and blocks included)
#   without  the agent builds against a copy of the canon with gotchas/ and blocks/ removed
# Everything else is identical: ds-next, code tools, scaffolds, spec, acceptance (always scored
# against the full canon, so both products are judged the same way). Results land in runs/.
set -eu
COND="$1"; N="$2"
HERE="$(cd "$(dirname "$0")" && pwd)"
DSN="$HERE/../../.venv/bin/ds-next"; PY="$HERE/../../.venv/bin/python"
CANON="${DS_CANON:-$HOME/Developer/canon}"
OUT="$HERE/runs/$COND-$N"; mkdir -p "$OUT"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rebuild-$COND-$N-XXXX")"
if [ "$COND" = without ]; then
  BUILD_CANON="$WORK/canon"
  cp -R "$CANON" "$BUILD_CANON"; rm -rf "$BUILD_CANON/.git" "$BUILD_CANON/gotchas" "$BUILD_CANON/blocks"
  (cd "$BUILD_CANON" && python3 scripts/build_index.py >/dev/null)
else
  BUILD_CANON="$CANON"
fi
NAME="rb-$COND-$N"
echo "$(date +%T) probe" > "$OUT/log.txt"
(cd "$WORK" && "$DSN" ask "Reply with the single word ok." >> "$OUT/log.txt" 2>&1) || { echo "probe failed" >> "$OUT/log.txt"; exit 2; }
echo "$(date +%T) create $NAME against $BUILD_CANON" >> "$OUT/log.txt"
(cd "$WORK" && DS_CANON="$BUILD_CANON" "$DSN" ask --yes "Create a new project now from the python-cli scaffold. name: $NAME. purpose: A Claude-Code-style terminal over Cortex Code for the team's knowledge system, rebuilt from the canon. owner: cwkoenigs. extra tags: cortex. No Snowflake schema, no declines. It is confirmed; fetch the scaffold and create it. Reply in one line." >> "$OUT/log.txt" 2>&1)
START=$(date +%s)
echo "$(date +%T) build" >> "$OUT/log.txt"
(cd "$WORK/$NAME" && DS_CANON="$BUILD_CANON" PATH="$(dirname "$DSN"):$PATH" "$DSN" ask --yes-all --effort high "@$HERE/spec.md" > "$OUT/build.log" 2>&1) || true
END=$(date +%s)
echo "$(date +%T) accept (full canon)" >> "$OUT/log.txt"
(cd "$WORK/$NAME" && DS_CANON="$CANON" PATH="$(dirname "$DSN"):$PATH" "$PY" "$HERE/accept.py" . "$NAME" > "$OUT/accept.txt" 2>&1) || true
"$PY" - "$OUT" "$WORK/$NAME" "$COND" "$N" "$((END - START))" <<'PYEOF'
import json, re, sys, tomllib
from pathlib import Path
out, repo, cond, n, secs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4], int(sys.argv[5])
acc = (out / "accept.txt").read_text()
checks = re.findall(r"^(PASS|FAIL)  (.+?)  ", acc + "\n", re.M)
build = (out / "build.log").read_text()
tools = re.findall(r"^⏺ ([A-Za-z_.]+)\(?", build, re.M)
m = tomllib.loads((repo / ".ds" / "manifest.toml").read_text()) if (repo / ".ds" / "manifest.toml").exists() else {}
turns = re.findall(r"(\d+) turns? · ([\d.]+)s", build)
behaviour = [c for c in checks if c[1] != "uses the UI blocks"]
res = {"condition": cond, "run": int(n), "repo": str(repo), "build_seconds": secs,
       "turns": int(turns[-1][0]) if turns else None,
       "behaviour_passed": sum(c[0] == "PASS" for c in behaviour), "behaviour_total": len(behaviour),
       "failed": [c[1] for c in checks if c[0] == "FAIL"],
       "blocks_used": sorted(m.get("blocks", {})),
       "gotchas_read": sorted(set(re.findall(r"canon_read\((gotcha-[a-z-]+)\)", build))),
       "graph_calls": sum(t.startswith("graph.") for t in tools), "lsp_calls": sum(t.startswith("lsp.") for t in tools),
       "src_lines": sum(len(p.read_text().splitlines()) for p in (repo / "src").rglob("*.py")) if (repo / "src").exists() else 0,
       "capped": "maximum number of requests" in build + acc, "stalled": "sent nothing for" in build + acc}
(out / "result.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res))
PYEOF
echo "$(date +%T) done" >> "$OUT/log.txt"
