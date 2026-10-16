"""The browser view, rendered by docs-ds. ds-next stages a content tree and points the shell
at it with environment variables; the shell is never modified.

Inside a repo the site is that repo's docs with every [[pointer]] turned into a link to the
standard's page. Outside one it is the knowledge base itself: every standard and every skill.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .kb import POINTER_RE, Canon, Skills, docs_shell_path


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
        sid = m.group(1)
        std = canon.standards.get(sid)
        return f"[{std.title}]({prefix}standards/{sid}.md)" if std else m.group(0)
    return POINTER_RE.sub(sub, text)


def stage(stage_dir: Path, canon: Canon, skills: Skills, repo: Path | None = None) -> tuple[Path, str]:
    """Write the content tree. Returns (docs dir, site title)."""
    docs = Path(stage_dir) / "docs"
    shutil.rmtree(docs, ignore_errors=True)
    if repo:
        title = repo.name
        for i, (fname, label) in enumerate([("README.md", "Overview"), ("AGENTS.md", "Agents"),
                                            ("DECISIONS.md", "Decisions")], start=1):
            f = repo / fname
            if f.is_file():
                body = f.read_text().split("\n", 1)[1] if f.read_text().startswith("# ") else f.read_text()
                target = docs / ("index.md" if i == 1 else f"{fname.lower()}")
                _page(target, title if i == 1 else label, _link_pointers(body, canon, ""), i)
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
