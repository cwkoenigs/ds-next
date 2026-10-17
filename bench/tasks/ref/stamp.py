"""Reference `stamp`: proves the checks pass on a correct solution."""
from __future__ import annotations

import argparse
import json
import keyword
import re
import shlex
import subprocess
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def lit(s: str) -> str:
    return json.dumps(s, ensure_ascii=False).replace("\x7f", "\\u007f")


def git(target: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=target, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {(r.stderr or r.stdout).strip().splitlines()[-1:]}")
    return r.stdout.strip()


def main() -> None:
    p = argparse.ArgumentParser(prog="stamp")
    p.add_argument("target")
    p.add_argument("--name", required=True)
    p.add_argument("--purpose", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--check", default="uv run pytest -q")
    a = p.parse_args()
    try:
        run(a)
    except (ValueError, RuntimeError, OSError) as e:
        print(f"stamp: {e}", file=sys.stderr)
        sys.exit(1)


def run(a) -> None:
    if not NAME_RE.match(a.name):
        raise ValueError(f"name {a.name!r}: lowercase letters, digits and single dashes, starting with a letter")
    pkg = a.name.replace("-", "_")
    if keyword.iskeyword(pkg) or keyword.issoftkeyword(pkg):
        raise ValueError(f"name {a.name!r}: {pkg!r} is a Python keyword")
    target = Path(a.target)
    if target.is_symlink():
        raise ValueError(f"{target} is a symbolic link")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError(f"{target} exists and is not empty")
    files = {
        "pyproject.toml": f'[project]\nname = {lit(a.name)}\ndescription = {lit(a.purpose)}\n'
                          f'authors = [{{name = {lit(a.owner)}}}]\nversion = "0.1.0"\n',
        f"src/{pkg}/__init__.py": f"{lit(a.purpose)}\n",
        ".gitlab-ci.yml": f"test:\n  variables:\n    PURPOSE: {lit(a.purpose)}\n  script:\n    - {lit(a.check)}\n",
        "README.md": f"# {a.name}\n\n{a.purpose}\n",
    }
    target.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        (target / rel).write_text(text)
    git(target, "init", "-q")
    git(target, "add", ".")
    git(target, "commit", "-q", "-m", "Initial project from stamp")
    hooks = Path(git(target, "rev-parse", "--git-path", "hooks"))
    hooks = hooks if hooks.is_absolute() else target / hooks
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-push"
    hook.write_text(f"#!/bin/sh\nexec sh -c {shlex.quote(a.check)}\n")
    hook.chmod(0o755)
