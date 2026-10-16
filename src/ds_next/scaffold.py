"""Answers in, a repository out. Deterministic: no model, no network.

The agent's job is the interview; this module's job is the files. Every file it writes is
either local (from an answer), inherited (a [[pointer]] into the canon, never its text), or
code skeleton. Provenance comments say which.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import __version__
from .kb import Canon, Skills

KINDS = ("cli", "package")
# skills-os procedures worth naming in a new repo's AGENTS.md, in the order a project meets them
RECOMMENDED_SKILLS = ("so-build-feature-interview", "so-bug-review-interview",
                      "so-best-practice-audit", "so-capture", "so-changes")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,40}$")


def _git_user() -> str:
    try:
        out = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, check=False)
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


@dataclass
class Answers:
    name: str
    purpose: str
    owner: str = field(default_factory=_git_user)
    kind: str = "cli"
    test_cmd: str = "uv run pytest -q"
    lint_cmd: str = "uv run ruff check ."
    tags: list[str] = field(default_factory=list)
    snowflake: str = ""          # DATABASE.SCHEMA, or empty
    notes: str = ""
    declines: dict[str, str] = field(default_factory=dict)   # standard id -> reason

    def __post_init__(self) -> None:
        if not NAME_RE.match(self.name):
            raise ValueError(f"name {self.name!r}: lowercase letters, digits and dashes, 2-41 chars")
        if self.kind not in KINDS:
            raise ValueError(f"kind {self.kind!r}: one of {', '.join(KINDS)}")
        if not self.purpose.strip():
            raise ValueError("purpose: one line on what the repo does")
        # The kind implies tags whatever else was given: a CLI ships as a package too, so it
        # inherits the package standards even when the interview only said "cli".
        implied = ["python", "package", *(["cli"] if self.kind == "cli" else []),
                   *(["snowflake"] if self.snowflake else [])]
        self.tags = list(dict.fromkeys([*implied, *(t.strip().lower() for t in self.tags if t.strip())]))

    @property
    def package(self) -> str:
        return self.name.replace("-", "_")

    @classmethod
    def from_toml(cls, path: Path) -> Answers:
        return cls(**tomllib.loads(Path(path).read_text()))


def _toml_str(s: str) -> str:
    return json.dumps(s)         # a JSON string is a valid TOML basic string


def render(a: Answers, canon: Canon, skills: Skills, today: dt.date | None = None) -> dict[str, str]:
    """Every file of the new repo, as {relative path: text}."""
    today = today or dt.date.today()
    stds = canon.applicable(a.tags)
    unknown = sorted(set(a.declines) - {s.id for s in stds})
    if unknown:
        raise ValueError(f"cannot decline {', '.join(unknown)}: not a standard that applies here")
    local = f"<!-- ds:local interview {today} -->"
    adopted = [s for s in stds if s.id not in a.declines]
    files: dict[str, str] = {}

    snow = f"\nIt reads and writes Snowflake in `{a.snowflake}`.\n" if a.snowflake else ""
    files["README.md"] = f"""# {a.name}

{local}
{a.purpose.strip()}
{snow}
Owner: {a.owner}

## Run

```bash
uv sync
{a.test_cmd}
```
{f"{chr(10)}## Notes{chr(10)}{chr(10)}{a.notes.strip()}{chr(10)}" if a.notes.strip() else ""}"""

    named = [n for n in RECOMMENDED_SKILLS if n in skills.all]
    skill_lines = "".join(f"- `/{n}`: {skills.all[n].description.split('. ')[0].rstrip('.')}.\n"
                          for n in named)
    files["AGENTS.md"] = f"""# AGENTS.md

{local}
{a.purpose.strip()}

- Test: `{a.test_cmd}`
- Lint: `{a.lint_cmd}`
- Before changing anything, read `.ds/manifest.toml`: it says which standards are in force here.

<!-- ds:inherited canon {today} -->
## Standards

This repo follows {", ".join(f"[[{s.id}]]" for s in adopted) or "no canon standards"}.
{"Declined, with reasons in the manifest: " + ", ".join(sorted(a.declines)) + "." if a.declines else ""}
{f"{chr(10)}## Skills{chr(10)}{chr(10)}From skills-os:{chr(10)}{chr(10)}{skill_lines}" if skill_lines else ""}"""

    files["DECISIONS.md"] = f"""# Decisions

{local}
Local decisions for this repo, numbered local-001 upward. Team-wide decisions belong in the
canon as standards; this file links them with `[[id]]` rather than restating them.

None yet.
"""

    lines = ["[repo]", f"name = {_toml_str(a.name)}",
             f"tags = [{', '.join(_toml_str(t) for t in a.tags)}]",
             f'created = "{today}"', 'interview = ".ds/interview.md"',
             f'ds_version = "{__version__}"', ""]
    revisit = today + dt.timedelta(days=90)
    for s in stds:
        lines += [f"[standards.{s.id}]"]
        if s.id in a.declines:
            lines += ['status = "declined"', f"version = {s.version}", f"by = {_toml_str(a.owner)}",
                      f'on = "{today}"', f"reason = {_toml_str(a.declines[s.id])}",
                      f'revisit = "{revisit}"']
        else:
            lines += ['status = "adopted"', f"version = {s.version}",
                      f"by = {_toml_str(a.owner)}", f'on = "{today}"']
        lines.append("")
    files[".ds/manifest.toml"] = "\n".join(lines)

    qa = "\n".join(f"- **{k}**: {v}" for k, v in asdict(a).items())
    files[".ds/interview.md"] = f"# Interview\n\n{local}\n{qa}\n"

    files["pyproject.toml"] = f"""[project]
name = "{a.name}"
version = "0.1.0"
description = {_toml_str(a.purpose.strip())}
requires-python = ">=3.12"
dependencies = [{'"typer>=0.12"' if a.kind == "cli" else ""}]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.6"]
{f'{chr(10)}[project.scripts]{chr(10)}{a.name} = "{a.package}.cli:app"{chr(10)}' if a.kind == "cli" else ""}
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{a.package}"]
"""
    files[f"src/{a.package}/__init__.py"] = f'"""{a.purpose.strip()}"""\n__version__ = "0.1.0"\n'
    if a.kind == "cli":
        files[f"src/{a.package}/cli.py"] = f'''import typer

from . import __version__

app = typer.Typer(help={_toml_str(a.purpose.strip())}, no_args_is_help=True)


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(__version__)


@app.command()
def hello(name: str = "world") -> None:
    """Say hello. Replace with the first real command."""
    typer.echo(f"hello, {{name}}")
'''
        files["tests/test_cli.py"] = f'''from typer.testing import CliRunner

from {a.package}.cli import app


def test_version():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0 and result.stdout.strip() == "0.1.0"
'''
    else:
        files["tests/test_package.py"] = f'''import {a.package}


def test_version():
    assert {a.package}.__version__ == "0.1.0"
'''
    files[".gitignore"] = ".venv/\n__pycache__/\n.pytest_cache/\n.ruff_cache/\ndist/\n.ds/site/\n"
    files[".gitlab-ci.yml"] = f"""# {"ds:inherited [[cicd]]" if "cicd" in {s.id for s in stds} else "ds:local"}
stages: [check]

test:
  stage: check
  image: ghcr.io/astral-sh/uv:python3.12-bookworm
  script:
    - uv sync
    - {a.test_cmd}
    - {a.lint_cmd}

reconcile:
  stage: check
  image: ghcr.io/astral-sh/uv:python3.12-bookworm
  script:
    - uvx --from ds-next ds-next reconcile
  allow_failure: true   # until ds-next is published where the runner can reach it
"""
    return files


PRE_PUSH = """#!/bin/sh
# ds:derived ds-next hooks. Pending standards never block; broken pointers and a bad manifest do.
command -v ds-next >/dev/null 2>&1 || exit 0
exec ds-next reconcile --quiet
"""


def install_hook(repo: Path) -> Path | None:
    hooks = repo / ".git" / "hooks"
    if not hooks.is_dir():
        return None
    hook = hooks / "pre-push"
    hook.write_text(PRE_PUSH)
    hook.chmod(0o755)
    return hook


def write(a: Answers, dest: Path, canon: Canon | None = None, skills: Skills | None = None,
          git: bool = True) -> list[str]:
    """Create the repo at dest. Refuses a directory that already has files in it."""
    dest = Path(dest).expanduser().resolve()
    if dest.exists() and any(p.name != ".git" for p in dest.iterdir()):
        raise FileExistsError(f"{dest} is not empty")
    files = render(a, canon or Canon(), skills or Skills())
    for rel, text in files.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    if git:
        run = lambda *c: subprocess.run(["git", *c], cwd=dest, capture_output=True, text=True, check=False)
        if not (dest / ".git").exists():
            run("init", "-q", "-b", "main")
        install_hook(dest)
        run("add", "-A")
        run("commit", "-q", "-m", f"Scaffold {a.name} from the canon with ds-next")
    return sorted(files)
