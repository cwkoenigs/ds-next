"""Checks for `stamp`. Run: python check.py <repo>"""
from __future__ import annotations

import ast
import os
import stat
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import case, git_env, no_traceback, run, static, summary, tmp  # noqa: E402

HOSTILE = 'He said "hi" \\ back\\slash \'single\' """triple""" {{name}} ü 😀 #not: a: comment - x'
OWNER = 'Siobhán O\'Brien "Bob" \\ ü'


def stamp(target: Path, name="demo-tool", purpose="A small tool.", owner="Ana", check=None, env=None):
    args = [str(target), "--name", name, "--purpose", purpose, "--owner", owner]
    if check is not None:
        args += ["--check", check]
    return run("stamp", *args, cwd=target.parent, env=env)


def read_all(target: Path, name: str):
    pkg = name.replace("-", "_")
    py = tomllib.loads((target / "pyproject.toml").read_text())
    doc = ast.get_docstring(ast.parse((target / "src" / pkg / "__init__.py").read_text()), clean=False)
    ci = yaml.safe_load((target / ".gitlab-ci.yml").read_text())
    readme = (target / "README.md").read_text()
    return py, doc, ci, readme


def hook_path(target: Path, env) -> Path:
    r = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=target, env=env, capture_output=True,
                       text=True, check=True)
    p = Path(r.stdout.strip())
    return (p if p.is_absolute() else target / p) / "pre-push"


static()


@case("creates the project with exact fields")
def _():
    t = tmp() / "proj"
    r = stamp(t)
    py, doc, ci, readme = read_all(t, "demo-tool")
    ok = (r.returncode == 0 and py["project"]["name"] == "demo-tool" and py["project"]["description"] == "A small tool."
          and py["project"]["authors"] == [{"name": "Ana"}] and doc == "A small tool."
          and ci["test"]["script"] == ["uv run pytest -q"] and ci["test"]["variables"]["PURPOSE"] == "A small tool."
          and readme.startswith("# demo-tool\n\nA small tool."))
    return ok, r.stderr.strip()[-150:]


@case("commits everything")
def _():
    t = tmp() / "proj"
    env = git_env()
    stamp(t, env=env)
    log = subprocess.run(["git", "log", "--oneline"], cwd=t, env=env, capture_output=True, text=True, check=False)
    st = subprocess.run(["git", "status", "--porcelain"], cwd=t, env=env, capture_output=True, text=True, check=False)
    return log.returncode == 0 and len(log.stdout.splitlines()) >= 1 and st.stdout.strip() == "", st.stdout[:100]


@case("hostile purpose survives exactly in TOML, Python, YAML and Markdown")
def _():
    t = tmp() / "proj"
    r = stamp(t, purpose=HOSTILE)
    py, doc, ci, readme = read_all(t, "demo-tool")
    got = {"toml": py["project"]["description"] == HOSTILE, "python": doc == HOSTILE,
           "yaml": ci["test"]["variables"]["PURPOSE"] == HOSTILE, "md": HOSTILE in readme}
    return r.returncode == 0 and all(got.values()), str(got)


@case("{{placeholders}} in user text stay literal")
def _():
    t = tmp() / "proj"
    stamp(t, purpose="uses {{name}} and {{package}} literally")
    return "uses {{name}} and {{package}} literally" in (t / "README.md").read_text(), ""


@case("hostile owner survives exactly")
def _():
    t = tmp() / "proj"
    stamp(t, owner=OWNER)
    return tomllib.loads((t / "pyproject.toml").read_text())["project"]["authors"] == [{"name": OWNER}], ""


@case("refuses names that are not valid or not importable")
def _():
    bad = ["class", "Bad-Name", "9lives", "a--b", "has_underscore", "-dash", "x/../y"]
    outs = []
    for n in bad:
        t = tmp() / "proj"
        r = stamp(t, name=n)
        outs.append((n, r.returncode != 0 and not t.exists() and no_traceback(r)))
    return all(ok for _, ok in outs), str([n for n, ok in outs if not ok])


@case("refuses a non-empty target and changes nothing in it")
def _():
    t = tmp() / "proj"
    t.mkdir()
    (t / "keep.txt").write_text("mine")
    r = stamp(t)
    return (r.returncode != 0 and [p.name for p in t.iterdir()] == ["keep.txt"]
            and (t / "keep.txt").read_text() == "mine" and no_traceback(r)), ""


@case("accepts an existing empty target")
def _():
    t = tmp() / "proj"
    t.mkdir()
    r = stamp(t)
    return r.returncode == 0 and (t / "pyproject.toml").is_file(), r.stderr.strip()[-150:]


@case("refuses a target that is a symlink to somewhere else")
def _():
    base = tmp()
    elsewhere = base / "elsewhere"
    elsewhere.mkdir()
    link = base / "proj"
    link.symlink_to(elsewhere)
    r = stamp(link)
    return r.returncode != 0 and list(elsewhere.iterdir()) == [] and no_traceback(r), ""


@case("hook goes where git runs hooks (core.hooksPath)")
def _():
    home = tmp()
    env = git_env(home)
    with open(home / ".gitconfig-test", "a") as f:
        f.write("[core]\n\thooksPath = .githooks\n")
    t = tmp() / "proj"
    r = stamp(t, env=env)
    h = t / ".githooks" / "pre-push"
    return r.returncode == 0 and h.is_file() and bool(h.stat().st_mode & stat.S_IXUSR), r.stderr.strip()[-150:]


@case("hook runs the check and blocks on failure")
def _():
    env = git_env()
    good, bad = tmp() / "good", tmp() / "bad"
    stamp(good, check="true", env=env)
    stamp(bad, check="exit 3", env=env)
    rg = subprocess.run([str(hook_path(good, env))], cwd=good, env=env, capture_output=True, check=False)
    rb = subprocess.run([str(hook_path(bad, env))], cwd=bad, env=env, capture_output=True, check=False)
    return rg.returncode == 0 and rb.returncode != 0, f"good={rg.returncode} bad={rb.returncode}"


QUOTED = 'test "it\'s a b" = "it\'s a b"'


@case("hook keeps a quoted check command intact")
def _():
    env = git_env()
    t = tmp() / "proj"
    stamp(t, check=QUOTED, env=env)
    r = subprocess.run([str(hook_path(t, env))], cwd=t, env=env, capture_output=True, check=False)
    ci = yaml.safe_load((t / ".gitlab-ci.yml").read_text())
    return r.returncode == 0 and ci["test"]["script"] == [QUOTED], f"hook={r.returncode}"


@case("a git failure is a failure (non-zero exit, one-line reason, no traceback)")
def _():
    home = tmp()
    env = git_env(home)
    shim = home / "bin"
    shim.mkdir()
    real = subprocess.run(["which", "git"], capture_output=True, text=True, check=True).stdout.strip()
    (shim / "git").write_text(f'#!/bin/sh\nfor a in "$@"; do [ "$a" = commit ] && {{ echo "fatal: no" >&2; exit 128; }}; done\n'
                              f'exec "{real}" "$@"\n')
    (shim / "git").chmod(0o755)
    env["PATH"] = f"{shim}{os.pathsep}{env['PATH']}"
    r = stamp(tmp() / "proj", env=env)
    return r.returncode != 0 and no_traceback(r) and r.stderr.strip() != "", f"exit {r.returncode}"


summary()
