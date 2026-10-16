"""The browser view, rendered by docs-ds. ds-next stages a content tree and points the shell
at it with environment variables; the shell is never modified.

Inside a repo the site is that repo's docs with every [[pointer]] turned into a link to the
standard's page. Outside one it is the knowledge base itself: every standard and every skill.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import reconcile
from .kb import POINTER_RE, Canon, Skills, docs_shell_path

RESERVED = {"standards", "skills"}
README_LINK_RE = re.compile(r"\]\(((?:\./|(?:\.\./)+)?)README\.md")


def _page(path: Path, title: str, body: str, position: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = {"title": title} | ({"sidebar_position": position} if position is not None else {})
    head = "".join(f"{k}: {json.dumps(v)}\n" for k, v in fm.items())
    path.write_text(f"---\n{head}---\n\n{body}")


def _category(d: Path, label: str, position: int) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "_category_.json").write_text(json.dumps({"label": label, "position": position}))


def _link_pointers(text: str, canon: Canon, prefix: str) -> str:
    def sub(m):
        sid, pin = m.group(1), m.group(2)
        std = canon.standards.get(sid)
        if std is None:
            return m.group(0)
        # the site holds only the current text, so a pin to an older version says so instead of
        # silently presenting the newer standard as the one this repo chose
        note = f" (pinned v{pin}; the canon is now v{std.version})" if pin and int(pin) != std.version else ""
        return f"[{std.title}]({prefix}standards/{sid}.md){note}"
    return POINTER_RE.sub(sub, text)


def stage(stage_dir: Path, canon: Canon, skills: Skills, repo: Path | None = None) -> tuple[Path, str]:
    """Write the content tree. Returns (docs dir, site title)."""
    docs = Path(stage_dir) / "docs"
    shutil.rmtree(docs, ignore_errors=True)
    if repo:
        title = repo.name
        # Every Markdown file the repo has, at its own relative path, so the links between them
        # keep working on the site. README.md becomes the home page, and links to it follow.
        order = {"README.md": ("index.md", title, 1), "AGENTS.md": ("AGENTS.md", "Agents", 2),
                 "DECISIONS.md": ("DECISIONS.md", "Decisions", 3)}
        for f in reconcile._docs(repo):
            rel = f.relative_to(repo).as_posix()
            if rel.split("/")[0] in RESERVED:
                continue                       # the site's own sections; the repo's copy would collide
            text = f.read_text(errors="replace")
            heading = text.split("\n", 1)[0][2:].strip() if text.startswith("# ") else ""
            body = text.split("\n", 1)[1] if heading else text
            target, label, position = order.get(rel, (rel, heading or f.stem.replace("-", " ").capitalize(), None))
            depth = target.count("/")
            body = README_LINK_RE.sub(lambda m: f"]({m.group(1) or ''}index.md", body)
            _page(docs / target, label, _link_pointers(body, canon, "../" * depth), position)
    else:
        title = "Knowledge base"
        rows = "\n".join(f"| [{s.id}](standards/{s.id}.md) | {s.title} | v{s.version} | {s.status} |"
                         for s in canon.standards.values())
        _page(docs / "index.md", title,
              "The canon says what is true; skills-os says how we work; this site renders both.\n\n"
              f"| Standard | Title | Version | Status |\n|---|---|---|---|\n{rows}\n", 1)
    _category(docs / "standards", "Standards", 10)
    for s in canon.standards.values():
        body = canon.read(s.id)
        body = body.split("\n", 1)[1] if body.startswith("# ") else body
        _page(docs / "standards" / f"{s.id}.md", s.title, _link_pointers(body, canon, "../"))
    if skills.all:
        _category(docs / "skills", "Skills", 20)
        for sk in skills.all.values():
            body = sk.read()
            body = body.split("\n", 1)[1] if body.startswith("# ") else body
            _page(docs / "skills" / f"{sk.name}.md", sk.name, f"> {sk.description}\n\n{body}")
    return docs, title


def build(docs: Path, title: str, out: Path) -> subprocess.CompletedProcess:
    shell = docs_shell_path()
    if shell is None or not (shell / "node_modules").is_dir():
        raise FileNotFoundError("docs-ds not found or not installed: clone it to ~/Developer/docs-ds "
                                "and run `npm ci` there, or set DS_DOCS_SHELL")
    env = {**os.environ, "DOCS_CONTENT_PATH": str(docs.resolve()), "SITE_BASE_URL": "/",
           "SITE_TITLE": title, "SITE_NAV_LABEL": title, "SITE_TAGLINE": "rendered by ds-next",
           "DOCS_STRICT": "0"}
    return subprocess.run(["npx", "docusaurus", "build", "--out-dir", str(Path(out).resolve())],
                          cwd=shell, env=env, capture_output=True, text=True, check=False)
