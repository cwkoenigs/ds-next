"""Answers in, a repository out. Deterministic: no model, no network.

The form (or the agent) gathers the answers; this module writes the files. The code skeleton is
an accepted scaffold from the canon, never a template held here. Every other file is either
local (from an answer) or inherited (a [[pointer]] into the canon, never its text), and
provenance comments say which.
"""
from __future__ import annotations

import datetime as dt
import json
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
    # the accepted code: a new repo starts on canon-lib when the canon ships it
    lib = canon.root / "lib"
    has_lib = (lib / "pyproject.toml").is_file()
    try:
        index_stamp = str(json.loads((canon.root / "index.json").read_text()).get("generated", ""))
    except (OSError, ValueError):
        index_stamp = ""

    snow = f"\nIt reads and writes Snowflake in `{a.snowflake}`.\n" if a.snowflake else ""
    outs = f"\nOutputs: {', '.join(sc.outputs)}.\n" if sc.outputs else ""
    files["README.md"] = f"""# {a.name}

{local}
{a.purpose.strip()}
{snow}{outs}
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
{f"- Accepted code: `canon-lib` is a dependency of this repo. Its modules are listed in `{lib / 'src' / 'canon_lib' / '__init__.py'}`; import from it before writing code of your own, and never copy or edit it here.{chr(10)}" if has_lib else ""}- The team's knowledge base is served by `ds-next mcp` (canon_list, canon_read, code_search, code_get, code_add) for any agent that can reach it.
- Query the code graph before reading files, and check a symbol's references with the LSP tools
  before changing it (ds-next registers both when they are installed).

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
             *([f"type = {_toml_str(sc.type)}"] if sc.type else []),
             f"outputs = [{', '.join(_toml_str(o) for o in sc.outputs)}]",
             f'ds_version = "{__version__}"', f"canon = {_toml_str(str(canon.root))}",
             f"canon_index = {_toml_str(index_stamp)}"]
    if has_lib:
        lines.append(f"canon_lib = {_toml_str(str(lib))}")
    lines.append("")
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
        "test_cmd_json": json_str(a.test_cmd), "lint_cmd_json": json_str(a.lint_cmd),
        "canon_lib_dep": '"canon-lib"' if has_lib else "",
        "canon_lib_source": (f"\n[tool.uv.sources]\ncanon-lib = {{ path = {json_str(str(lib))}, editable = true }}\n"
                             if has_lib else "")}))
    return files


HOOK_MARKER = "# ds:derived ds-next hooks."


def _hook_text() -> str:
    """The pre-push hook. It finds ds-next on PATH or where it ran from when the hook was made,
    and says so out loud when it cannot, instead of skipping the check in silence."""
    here = shutil.which("ds-next") or str(Path(sys.argv[0]).resolve())
    fallback = here if Path(here).name == "ds-next" else ""
    return f"""#!/bin/sh
{HOOK_MARKER} Pending standards never block; broken pointers and a bad manifest do.
# A pre-push hook that was here before ds-next is kept as pre-push.local and runs first.
HERE="$(dirname "$0")"
if [ -x "$HERE/pre-push.local" ]; then
  "$HERE/pre-push.local" "$@" || exit $?
fi
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
    if hook.exists() and HOOK_MARKER not in hook.read_text(errors="replace"):
        # someone else's hook (a template's, a team's): keep it and run it first, never drop it
        local = hooks / "pre-push.local"
        if local.exists() or local.is_symlink():
            return f"{hook} and {local} both exist, so ds-next left them alone"
        hook.rename(local)
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


def _add_to_list_line(text: str, key: str, items: list[str]) -> tuple[str, list[str]] | None:
    """Add items to a one-line TOML list `key = [...]` (the shape the scaffolds write). Returns the
    new text and what was added (nothing when all are present), or None if there is no such line."""
    pattern = re.compile(rf"^({re.escape(key)} = )\[(.*)\]$", re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return None
    current = tomllib.loads(f"x = [{m.group(2)}]")["x"]
    names = {re.split(r"[<>=!~\[ ;]", c, maxsplit=1)[0].lower() for c in current}
    added = [i for i in items if re.split(r"[<>=!~\[ ;]", i, maxsplit=1)[0].lower() not in names]
    if not added:
        return text, []
    line = f"{m.group(1)}[{', '.join(json_str(i) for i in [*current, *added])}]"
    return text[:m.start()] + line + text[m.end():], added


def add_block(repo: Path, bid: str, canon: Canon | None = None, by: str | None = None,
              today: dt.date | None = None) -> dict:
    """Copy an accepted canon block into a repo: its module into the package, its tests into
    tests/, its requirements into pyproject.toml, its version into the manifest. A file the block
    did not write before is never overwritten. Returns what was done."""
    canon = canon or Canon()
    repo = Path(repo).resolve()
    b = canon.blocks.get(bid)
    if b is None:
        raise ValueError(f"block {bid!r}: the canon has {', '.join(canon.blocks) or 'none'}")
    if not b.accepted:
        raise ValueError(f"block {bid} is {b.status}, not accepted: its owner approves it in the canon")
    manifest_path = repo / ".ds" / "manifest.toml"
    if not manifest_path.is_file():
        raise ValueError(f"{repo} has no .ds/manifest.toml; create it with ds-next new first")
    manifest_text = manifest_path.read_text()
    manifest = tomllib.loads(manifest_text)
    package = str(manifest.get("repo", {}).get("name", "")).replace("-", "_")
    if not package or not (repo / "src" / package).is_dir():
        raise ValueError(f"{repo} has no src/{package}/ package to add the block to")
    have = manifest.get("blocks", {}).get(bid, {}).get("version")
    if have == b.version:
        return {"block": bid, "version": b.version, "files": [], "requires": [], "manual": [],
                "note": "already at this version"}
    files = canon.block_files(bid, package)
    targets = {rel: _inside(repo, rel) for rel in files}
    if have is None:
        clash = [rel for rel, t in targets.items() if t.exists()]
        if clash:
            raise FileExistsError(f"not added: {', '.join(clash)} already exist and were not written by {bid}")
    for rel, text in files.items():
        targets[rel].parent.mkdir(parents=True, exist_ok=True)
        targets[rel].write_text(text)
    added: list[str] = []
    manual: list[str] = []
    pyproject = repo / "pyproject.toml"
    for key, wanted in (("dependencies", list(b.requires)), ("dev", list(b.test_requires))):
        if not wanted:
            continue
        text = pyproject.read_text() if pyproject.is_file() else ""
        result = _add_to_list_line(text, key, wanted)
        if result is None:                   # no one-line list to add to: say so, never skip in silence
            manual += [f"{w} ({key})" for w in wanted]
            continue
        new, got = result
        if got:
            pyproject.write_text(new)
        added += got
    today = today or dt.date.today()
    table = (f"[blocks.{bid}]\nversion = {b.version}\nby = {json_str(by or _git_user())}\n"
             f'on = "{today}"\nmodule = {json_str(f"src/{package}/{b.module}.py")}\n')
    existing = re.compile(rf"^\[blocks\.{re.escape(bid)}\]\n(?:(?!\[).*\n?)*", re.MULTILINE)
    if existing.search(manifest_text):
        manifest_text = existing.sub(table + "\n", manifest_text, count=1)
    else:
        manifest_text = manifest_text.rstrip("\n") + "\n\n" + table
    manifest_path.write_text(manifest_text)
    return {"block": bid, "version": b.version, "files": sorted(files), "requires": added, "manual": manual,
            "note": "updated" if have is not None else "added"}
