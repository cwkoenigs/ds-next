"""Shared harness for the task checks: run a built console script, record PASS/FAIL, print a
JSON summary. Usage from a task: python check.py <repo>. Each check is independent and fast."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}"[:300], flush=True)


def case(name: str):
    """Decorator: run a check function; an exception in the check itself is a FAIL with its reason."""
    def wrap(fn):
        try:
            ok, detail = fn()
        except Exception as e:                      # noqa: BLE001 - a crash in a probe is a failed check
            ok, detail = False, f"{type(e).__name__}: {e}"
        check(name, ok, detail)
        return fn
    return wrap


def tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="task-")).resolve()


def git_env(home: Path | None = None) -> dict[str, str]:
    home = home or tmp()
    cfg = home / ".gitconfig-test"
    if not cfg.exists():
        cfg.write_text("[user]\n\tname = Check Bot\n\temail = check@example.com\n[init]\n\tdefaultBranch = main\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=str(cfg), GIT_CONFIG_NOSYSTEM="1", HOME=str(home))
    return env


def run(script: str, *args: str, cwd: Path | None = None, env: dict | None = None,
        timeout: int = 60) -> subprocess.CompletedProcess:
    exe = REPO / ".venv" / "bin" / script
    return subprocess.run([str(exe), *args], cwd=cwd or tmp(), env=env or git_env(), capture_output=True,
                          text=True, timeout=timeout, check=False)


def no_traceback(r: subprocess.CompletedProcess) -> bool:
    return "Traceback (most recent call last)" not in r.stdout + r.stderr


def static() -> None:
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    s = subprocess.run(["uv", "sync", "-q"], cwd=REPO, capture_output=True, text=True, env=env, check=False)
    check("uv sync", s.returncode == 0, s.stderr.strip()[-200:])
    t = subprocess.run(["uv", "run", "pytest", "-q"], cwd=REPO, capture_output=True, text=True, env=env, check=False)
    check("its tests pass", t.returncode == 0, (t.stdout.strip().splitlines() or [""])[-1])
    lint = subprocess.run(["uv", "run", "ruff", "check", "."], cwd=REPO, capture_output=True, text=True, env=env,
                          check=False)
    check("ruff clean", lint.returncode == 0, (lint.stdout.strip().splitlines() or [""])[-1])


def summary() -> None:
    behaviour = [r for r in results if r[0] not in ("uv sync", "its tests pass", "ruff clean")]
    out = {"repo": str(REPO), "passed": sum(ok for _, ok, _ in results), "total": len(results),
           "behaviour_passed": sum(ok for _, ok, _ in behaviour), "behaviour_total": len(behaviour),
           "failed": [n for n, ok, _ in results if not ok]}
    print(f"\n{out['passed']}/{out['total']} checks passed")
    print("RESULT " + json.dumps(out))


__all__ = ["REPO", "case", "check", "git_env", "no_traceback", "run", "static", "summary", "tmp", "traceback"]
