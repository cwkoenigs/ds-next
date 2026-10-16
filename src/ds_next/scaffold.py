"""Answers in, a repository out. Deterministic: no model, no network.

The form (or the agent) gathers the answers; this module writes the files. The code skeleton is
an accepted scaffold from the canon, never a template held here. Every other file is either
local (from an answer) or inherited (a [[pointer]] into the canon, never its text), and
provenance comments say which.
"""
from __future__ import annotations

import datetime as dt
import keyword
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
import unicodedata
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from . import __version__
from .kb import Canon, Skills, json_str

# skills-os procedures worth naming in a new repo's AGENTS.md, in the order a project meets them
RECOMMENDED_SKILLS = ("so-build-feature-interview", "so-bug-review-interview",
                      "so-best-practice-audit", "so-capture", "so-changes")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")


class ScaffoldError(RuntimeError):
    """The files were written but finishing the repo (git) failed; the message says where."""


def _one_line(label: str, value: str) -> None:
    """Every answer is a single line of printable text: it lands in Markdown, TOML, YAML and
    Python, and a newline or control character in any of them changes what the file says."""
    bad = next((c for c in value if unicodedata.category(c) in ("Cc", "Zl", "Zp")), None)
    if bad is not None:
        raise ValueError(f"{label}: one line of text, without control characters ({bad!r})")


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
    scaffold: str = "python-cli"   # a canon scaffold id
    owner: str = field(default_factory=_git_user)
    test_cmd: str = ""             # empty: the scaffold's default
    lint_cmd: str = ""
    tags: list[str] = field(default_factory=list)   # extra tags beyond the scaffold's own
    snowflake: str = ""            # DATABASE.SCHEMA, or empty
    notes: str = ""
    declines: dict[str, str] = field(default_factory=dict)   # standard id -> reason

    def __post_init__(self) -> None:
        if not NAME_RE.match(self.name) or self.name.endswith("-") or "--" in self.name:
            raise ValueError(f"name {self.name!r}: lowercase letters, digits and single dashes, 2-41 chars")
        if keyword.iskeyword(self.package) or keyword.issoftkeyword(self.package):
            raise ValueError(f"name {self.name!r}: {self.package!r} is a Python keyword, so it cannot be imported")
        if not self.purpose.strip():
            raise ValueError("purpose: one line on what the repo does")
        if not self.owner.strip():
            raise ValueError("owner: who answers for this repo")
        for label in ("name", "purpose", "scaffold", "owner", "test_cmd", "lint_cmd", "snowflake", "notes"):
            _one_line(label, getattr(self, label))
        self.tags = [t.strip().lower() for t in self.tags if t.strip()]
        for t in self.tags:
            if not TAG_RE.match(t):
                raise ValueError(f"tag {t!r}: lowercase letters, digits and dashes")
        for sid, why in self.declines.items():
            if not str(why).strip():
                raise ValueError(f"decline of {sid}: a decline needs a reason")
            _one_line(f"decline of {sid}", str(why))

    @property
    def package(self) -> str:
        return self.name.replace("-", "_")

    def resolve(self, canon: Canon) -> Answers:
        """Fill what the scaffold decides: its tags (always), and its commands when none were given.
        Refuses a scaffold the canon does not have or has not accepted."""
        sc = canon.scaffolds.get(self.scaffold)
        if sc is None:
            raise ValueError(f"scaffold {self.scaffold!r}: the canon has {', '.join(canon.scaffolds) or 'none'}")
        if not sc.accepted:
            raise ValueError(f"scaffold {sc.id} is {sc.status}, not accepted: its owner approves it in the canon")
        tags = [*sc.tags, *(["snowflake"] if self.snowflake else []), *self.tags]
        return replace(self, tags=list(dict.fromkeys(tags)),
                       test_cmd=self.test_cmd or sc.defaults.get("test_cmd", "uv run pytest -q"),
                       lint_cmd=self.lint_cmd or sc.defaults.get("lint_cmd", "uv run ruff check ."))

    @classmethod
    def from_toml(cls, path: Path) -> Answers:
        return cls(**tomllib.loads(Path(path).read_text()))


_toml_str = json_str             # a JSON string is a valid TOML basic string


def render(a: Answers, canon: Canon, skills: Skills, today: dt.date | None = None) -> dict[str, str]:
    """Every file of the new repo, as {relative path: text}: the knowledge docs from the answers,
    the code from the canon scaffold."""
    today = today or dt.date.today()
    a = a.resolve(canon)
    sc = canon.scaffolds[a.scaffold]
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
             f'scaffold = "{sc.id}"', f"scaffold_version = {sc.version}",
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

    files.update(canon.render_scaffold(sc.id, {
        "name": a.name, "package": a.package, "purpose": a.purpose.strip(),
        "purpose_json": json_str(a.purpose.strip()), "test_cmd": a.test_cmd, "lint_cmd": a.lint_cmd,
        "test_cmd_json": json_str(a.test_cmd), "lint_cmd_json": json_str(a.lint_cmd)}))
    return files


def _hook_text() -> str:
    """The pre-push hook. It finds ds-next on PATH or where it ran from when the hook was made,
    and says so out loud when it cannot, instead of skipping the check in silence."""
    here = shutil.which("ds-next") or str(Path(sys.argv[0]).resolve())
    fallback = here if Path(here).name == "ds-next" else ""
    return f"""#!/bin/sh
# ds:derived ds-next hooks. Pending standards never block; broken pointers and a bad manifest do.
DS="$(command -v ds-next 2>/dev/null)"
[ -z "$DS" ] && [ -x {shlex.quote(fallback)} ] && DS={shlex.quote(fallback)}
if [ -z "$DS" ]; then
  echo "ds: ds-next not found, so reconcile did not run. Install it (uv tool install ds-next) or put it on PATH." >&2
  exit 0
fi
exec "$DS" reconcile --quiet
"""


def install_hook(repo: Path) -> str | None:
    """Write the pre-push hook where git will actually run it. Returns why it could not, or None.

    Git decides where hooks live (core.hooksPath can move them), so ask git, and write only
    inside this repo's own .git, never through a symbolic link."""
    repo = repo.resolve()
    git_dir = repo / ".git"
    if git_dir.is_symlink() or not git_dir.is_dir():
        return f"{git_dir} is not this repo's own git directory"
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-path", "hooks"],
                       capture_output=True, text=True, check=False)
    hooks = (repo / r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else git_dir / "hooks"
    if hooks.is_symlink():
        return f"{hooks} is a symbolic link"
    hooks = hooks.resolve()
    if git_dir.resolve() not in (hooks, *hooks.parents):
        return f"git runs hooks from {hooks} (core.hooksPath), outside this repo, so it was not installed there"
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-push"
    if hook.is_symlink():          # never write through a link to somewhere else
        hook.unlink()
    hook.write_text(_hook_text())
    hook.chmod(0o755)
    return None


def _inside(dest: Path, rel: str) -> Path:
    """The path for rel under dest, refusing anything that would land elsewhere or pass
    through a symbolic link."""
    target = dest / rel
    if Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise ValueError(f"refusing to write {rel!r}: not a plain relative path")
    p = dest
    for part in Path(rel).parts:
        p = p / part
        if p.is_symlink():
            raise ValueError(f"refusing to write {rel!r}: {p} is a symbolic link")
    if dest not in target.resolve().parents:
        raise ValueError(f"refusing to write {rel!r}: it resolves outside {dest}")
    return target


def _git(dest: Path, *args: str) -> None:
    r = subprocess.run(["git", "-C", str(dest), *args], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise ScaffoldError(f"files are in {dest}, but `git {' '.join(args[:2])}` failed: "
                            f"{(r.stderr or r.stdout).strip()[:300]}")


def write(a: Answers, dest: Path, canon: Canon | None = None, skills: Skills | None = None,
          git: bool = True) -> list[str]:
    """Create the repo at dest. Refuses a directory that already has files in it, a symbolic
    link as the destination, and any file that would land outside it."""
    dest = Path(dest).expanduser()
    if dest.is_symlink():
        raise ValueError(f"refusing to write into {dest}: it is a symbolic link")
    dest = dest.resolve()
    if dest.exists() and any(p.name != ".git" for p in dest.iterdir()):
        raise FileExistsError(f"{dest} is not empty")
    if (dest / ".git").is_symlink():
        raise ValueError(f"refusing to write into {dest}: its .git is a symbolic link")
    files = render(a, canon or Canon(), skills or Skills())
    targets = {rel: _inside(dest, rel) for rel in files}      # check every path before writing any
    for rel, text in files.items():
        targets[rel].parent.mkdir(parents=True, exist_ok=True)
        targets[rel].write_text(text)
    if git:
        if not (dest / ".git").exists():
            _git(dest, "init", "-q", "-b", "main")
        top = subprocess.run(["git", "-C", str(dest), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=False).stdout.strip()
        if Path(top).resolve() != dest:     # never stage into a parent repository
            raise ScaffoldError(f"files are in {dest}, but git resolves it to {top or 'no repository'}")
        hook_problem = install_hook(dest)
        _git(dest, "add", "-A")
        _git(dest, "commit", "-q", "-m", f"Scaffold {a.name} from the canon with ds-next")
        if hook_problem:
            raise ScaffoldError(f"{dest} is created and committed, but the pre-push hook is not "
                                f"installed: {hook_problem}")
    return sorted(files)
