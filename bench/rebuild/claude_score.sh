#!/bin/sh
# Score a subagent rebuild with the fake cortex (no Cortex requests). Usage: claude_score.sh <run-number>
set -eu
N="$1"; HERE="$(cd "$(dirname "$0")" && pwd)"; OUT="$HERE/runs/claude-$N"
REPO="$(cat "$OUT/repo.txt")"; NAME="$(basename "$REPO")"; SECS=$(( $(date +%s) - $(cat "$OUT/start.txt") ))
DSN="$HERE/../../.venv/bin/ds-next"; PY="$HERE/../../.venv/bin/python"
(cd "$REPO" && CORTEX_CODE_CLI_PATH="$HERE/fake_cortex.py" PATH="$(dirname "$DSN"):$PATH" "$PY" "$HERE/accept.py" . "$NAME" > "$OUT/accept.txt" 2>&1) || true
"$PY" - "$OUT" "$REPO" "$N" "$SECS" <<'PYEOF'
import json, re, sys, tomllib
from pathlib import Path
out, repo, n, secs = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
checks = re.findall(r"^(PASS|FAIL)  (.+?)  ", (out / "accept.txt").read_text() + "\n", re.M)
m = tomllib.loads((repo / ".ds" / "manifest.toml").read_text())
behaviour = [c for c in checks if c[1] != "uses the UI blocks"]
res = {"builder": "claude-subagent", "run": n, "repo": str(repo), "seconds": secs,
       "behaviour_passed": sum(c[0] == "PASS" for c in behaviour), "behaviour_total": len(behaviour),
       "failed": [c[1] for c in checks if c[0] == "FAIL"], "blocks_used": sorted(m.get("blocks", {})),
       "src_lines": sum(len(p.read_text().splitlines()) for p in (repo / "src").rglob("*.py"))}
(out / "result.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res))
PYEOF
