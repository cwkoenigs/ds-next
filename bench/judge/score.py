"""Score a built repo with a blind judge's tests. Usage: python score.py <task> <repo> -> JSON line."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

task, repo = sys.argv[1], Path(sys.argv[2]).resolve()
here = Path(__file__).resolve().parent
binp = repo / ".venv" / "bin" / task
env = {**{k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}, "TARGET_BIN": str(binp)}
if not binp.exists():
    subprocess.run(["uv", "sync", "-q"], cwd=repo, capture_output=True, env=env, check=False)
r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rA",
                    str(here / task / "test_judge.py")], cwd=here / task, capture_output=True, text=True, env=env,
                   timeout=900, check=False)
passed = re.findall(r"^PASSED \S+::(\S+)", r.stdout, re.M)
failed = re.findall(r"^(?:FAILED|ERROR) \S+::(\S+)", r.stdout, re.M)
src = "\n".join(p.read_text(errors="replace") for p in (repo / "src").rglob("*.py")) if (repo / "src").exists() else ""
uses = sorted(set(re.findall(r"^\s*(?:from canon_lib\.(\w+) import|import canon_lib\.(\w+))", src, re.M)))
print(json.dumps({"task": task, "passed": len(passed), "total": len(passed) + len(failed), "failed": sorted(failed),
                  "canon_lib": sorted({a or b for a, b in uses})}))
