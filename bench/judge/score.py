"""Score a built repo with a blind judge's tests. Usage: python score.py <task> <repo> -> JSON line.
Reports the judge's pass count, which canon code the repo uses (canon_lib imports and code_add
copies, by block), and how many lines the build wrote itself (src/, minus code_add copies)."""
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
                   timeout=1800, check=False)
passed = re.findall(r"^PASSED \S+::(\S+)", r.stdout, re.MULTILINE)
failed = re.findall(r"^(?:FAILED|ERROR) \S+::(\S+)", r.stdout, re.MULTILINE)
files = sorted((repo / "src").rglob("*.py")) if (repo / "src").exists() else []
texts = {p: p.read_text(errors="replace") for p in files}
src = "\n".join(texts.values())
uses = sorted({a or b for a, b in re.findall(r"^\s*(?:from canon_lib\.(\w+) import|import canon_lib\.(\w+))", src, re.MULTILINE)})
copied = {p for p, t in texts.items() if t.startswith("\"\"\"From the canon's block-")}
pulled = sorted({m for p in copied for m in re.findall(r"From the canon's (block-[a-z0-9-]+) v\d+", texts[p])})
own_lines = sum(len([ln for ln in texts[p].splitlines() if ln.strip()]) for p in files if p not in copied)
print(json.dumps({"task": task, "passed": len(passed), "total": len(passed) + len(failed), "failed": sorted(failed),
                  "canon_lib": uses, "code_add": pulled, "own_lines": own_lines}))
