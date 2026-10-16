"""The knowledge base: three repositories on disk, read-only from here.

- canon     standards, one file each, indexed by index.json (what is true)
- skills-os SKILL.md procedures (how we work)
- docs-ds   the Docusaurus shell that renders both (how people read it)

Each is found by an environment variable, then beside the others under ~/Developer.
Nothing in this module writes.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path, PurePosixPath

POINTER_RE = re.compile(r"\[\[([a-z0-9-]+)(?:@(\d+))?\]\]")
CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)


def _find(env: str, name: str) -> Path | None:
    if os.environ.get(env):
        return Path(os.environ[env]).expanduser()
    for base in (Path.home() / "Developer", Path.home() / "code", Path.home() / ".ds"):
        if (base / name).is_dir():
            return base / name
    return None


def canon_path() -> Path | None:
    return _find("DS_CANON", "canon")


def skills_path() -> Path | None:
    return _find("DS_SKILLS", "skills-os")


def docs_shell_path() -> Path | None:
    return _find("DS_DOCS_SHELL", "docs-ds")


def _front_matter(text: str) -> tuple[dict[str, str], str]:
    """Flat `key: value` front matter. Enough for canon and SKILL.md; not a YAML parser."""
    if not text.startswith("---\n"):
        return {}, text
    head, _, body = text[4:].partition("\n---\n")
    meta = {}
    for line in head.splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith(" "):
            meta[key.strip()] = value.strip().strip('"')
    return meta, body.lstrip("\n")


@dataclass(frozen=True)
class Standard:
    id: str
    version: int
    title: str
    applies_to: tuple[str, ...]
    owner: str
    status: str
    path: str

    def applies(self, tags: list[str] | tuple[str, ...]) -> bool:
        return any(p == "*" or any(fnmatch.fnmatchcase(t, p) for t in tags) for p in self.applies_to)


@dataclass(frozen=True)
class Scaffold:
    """An accepted project shape from the canon: templates plus the tags it gives a repo."""
    id: str
    version: int
    title: str
    path: tuple[str, ...]        # menu path, e.g. ("python", "cli")
    tags: tuple[str, ...]
    status: str
    defaults: dict
    dir: str
    files: tuple[str, ...]
    hash: str = ""

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"


def json_str(s: str) -> str:
    """A string literal that is valid JSON, Python, TOML and YAML (double-quoted) at once, for
    text that came from a person. Raw Unicode is kept (TOML rejects JSON's surrogate escapes),
    and DEL, which JSON leaves raw but TOML and YAML refuse, is escaped."""
    return json.dumps(s, ensure_ascii=False).replace("\x7f", "\\u007f")


PLACEHOLDER_RE = re.compile(r"\{\{([a-z_]+)\}\}")


def _fill(text: str, values: dict[str, str]) -> str:
    """One pass over the template: a value is never searched again, so user text that happens to
    contain `{{test_cmd}}` stays literal instead of pulling in another, unescaped value."""
    return PLACEHOLDER_RE.sub(lambda m: values.get(m.group(1), m.group(0)), text)


class CanonError(ValueError):
    """The canon on disk does not match its own index."""


class Canon:
    def __init__(self, root: Path | None = None):
        root = root or canon_path()
        if root is None or not (root / "index.json").is_file():
            raise FileNotFoundError(
                "canon not found: set DS_CANON or clone it to ~/Developer/canon")
        self.root = Path(root)

    def _index(self) -> dict:
        """index.json, re-read whenever it changes on disk, so a long session sees canon updates."""
        path = self.root / "index.json"
        stamp = path.stat().st_mtime_ns
        if getattr(self, "_stamp", None) != stamp:
            data = json.loads(path.read_text())
            self._stamp = stamp
            self._standards = {
                s["id"]: Standard(s["id"], int(s["version"]), s["title"], tuple(s["applies_to"]),
                                  s.get("owner", ""), s.get("status", ""), s["path"])
                for s in data["standards"]}
            self._scaffolds = {
                s["id"]: Scaffold(s["id"], int(s["version"]), s["title"], tuple(s["path"]), tuple(s["tags"]),
                                  s.get("status", ""), dict(s.get("defaults", {})), s["dir"], tuple(s["files"]),
                                  s.get("hash", ""))
                for s in data.get("scaffolds", [])}
        return {"standards": self._standards, "scaffolds": self._scaffolds}

    @property
    def standards(self) -> dict[str, Standard]:
        return self._index()["standards"]

    @property
    def scaffolds(self) -> dict[str, Scaffold]:
        return self._index()["scaffolds"]

    def scaffold_about(self, sid: str) -> str:
        return _front_matter((self.root / self.scaffolds[sid].dir / "SCAFFOLD.md").read_text())[1]

    def scaffold_digest(self, sid: str) -> str:
        """The hash build_index.py writes: SCAFFOLD.md, then each template's path and bytes."""
        sc = self.scaffolds[sid]
        base = self.root / sc.dir
        digest = hashlib.sha256((base / "SCAFFOLD.md").read_bytes())
        for rel in sc.files:
            digest.update(f"files/{rel}".encode() + (base / "files" / rel).read_bytes())
        return digest.hexdigest()[:12]

    def render_scaffold(self, sid: str, values: dict[str, str]) -> dict[str, str]:
        """The scaffold's templates with {{placeholders}} filled. `__package__` in a path is the
        package name; a leading `dot-` becomes `.`, so templates never act on the canon itself.

        Refuses templates that no longer match the index (edited without a version bump), and
        template paths that could land outside the new repo."""
        sc = self.scaffolds[sid]
        if sc.hash and self.scaffold_digest(sid) != sc.hash:
            raise CanonError(f"scaffold {sid}: its templates changed since index.json was built; "
                             "run scripts/build_index.py in the canon (and bump its version)")
        out = {}
        for rel in sc.files:
            parts = PurePosixPath(rel).parts
            if PurePosixPath(rel).is_absolute() or any(p in ("..", ".", "") for p in parts):
                raise CanonError(f"scaffold {sid}: template path {rel!r} is not a plain relative path")
            text = (self.root / sc.dir / "files" / rel).read_text()
            target = "/".join(("." + p[4:]) if p.startswith("dot-") else p for p in parts)
            out[target.replace("__package__", values["package"])] = _fill(text, values)
        return out

    def applicable(self, tags: list[str] | tuple[str, ...]) -> list[Standard]:
        return sorted((s for s in self.standards.values() if s.applies(tags)), key=lambda s: s.id)

    def read(self, sid: str) -> str:
        if sid not in self.standards:
            raise KeyError(f"no standard {sid!r} in the canon")
        return _front_matter((self.root / self.standards[sid].path).read_text())[1]

    def pointer_problems(self, text: str) -> list[str]:
        """What is wrong with the [[pointers]] in prose: an id the canon does not have, or a
        pin to a version it never had. Code is skipped so a doc can talk about the syntax."""
        prose = CODE_RE.sub("", text)
        problems = set()
        for m in POINTER_RE.finditer(prose):
            sid, pin = m.group(1), m.group(2)
            std = self.standards.get(sid)
            if std is None:
                problems.add(f"[[{sid}]] is not in the canon")
            elif pin is not None and not 1 <= int(pin) <= std.version:
                problems.add(f"[[{sid}@{pin}]] pins a version the canon never had (current v{std.version})")
        return sorted(problems)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path

    def read(self) -> str:
        return _front_matter(self.path.read_text())[1]


class Skills:
    def __init__(self, root: Path | None = None):
        self.root = root or skills_path()

    @cached_property
    def all(self) -> dict[str, Skill]:
        if self.root is None or not self.root.is_dir():
            return {}
        out = {}
        for f in sorted(self.root.glob("*/SKILL.md")):
            meta, _ = _front_matter(f.read_text())
            name = meta.get("name", f.parent.name)
            out[name] = Skill(name, meta.get("description", ""), f)
        return out
