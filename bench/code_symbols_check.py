"""Every accepted code symbol in the canon must stand alone: code_add it (alone) into a fresh
scaffolded repo, then its cut-down tests pass and ruff is clean. Usage: python code_symbols_check.py"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from ds_next import code, scaffold
from ds_next.kb import Canon

canon = Canon()
base = Path(tempfile.mkdtemp(prefix="symbols-"))
a = scaffold.Answers(name="symcheck", purpose="Symbol check.", owner="bench")
repo = base / "symcheck"
scaffold.write(a, repo, canon, git=True)
subprocess.run(["uv", "sync", "-q", "--all-groups"], cwd=repo, check=True)
template = {p.relative_to(repo): p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".venv" not in p.parts
            and ".git" not in p.parts}
bad = []
symbols = [s for s in canon.code.values() if s["status"] == "accepted"]
for s in symbols:
    for rel, data in template.items():           # back to the fresh scaffold each time
        (repo / rel).write_bytes(data)
    for p in list((repo / "src" / "symcheck").glob("*.py")) + list((repo / "tests").glob("test_*.py")):
        if p.relative_to(repo) not in template:
            p.unlink()
    done = code.add(repo, [s["id"]], canon)
    subprocess.run(["uv", "sync", "-q", "--all-groups"], cwd=repo, capture_output=True, check=False)
    t = subprocess.run(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider"], cwd=repo, capture_output=True, text=True)
    lint = subprocess.run(["uv", "run", "ruff", "check", "."], cwd=repo, capture_output=True, text=True)
    ok = t.returncode == 0 and lint.returncode == 0
    tail = (t.stdout.strip().splitlines() or [""])[-1]
    print(f"{'ok  ' if ok else 'FAIL'} {s['id']:<48} {tail:<30} {'lint ok' if lint.returncode == 0 else lint.stdout.strip()[:200]}")
    if not ok:
        bad.append(s["id"])
print(f"\n{len(symbols) - len(bad)}/{len(symbols)} symbols stand alone" + (f"; failing: {bad}" if bad else ""))
sys.exit(1 if bad else 0)
