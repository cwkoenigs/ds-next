"""Reference `stage`: proves the checks pass on a correct solution."""
from __future__ import annotations

import argparse
import os
import posixpath
import re
import shutil
import sys
from pathlib import Path

SKIP = {".git", "node_modules", ".venv"}
MARKER = ".staged-by-stage"
LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\))")


def check_out(repo: Path, out: Path) -> None:
    for danger, why in ((repo, "is the repo"), (Path.home().resolve(), "is the home directory"), (Path("/"), "is /")):
        if out == danger:
            raise ValueError(f"--out {out} {why}")
    if repo.is_relative_to(out):
        raise ValueError(f"--out {out} contains the repo")
    if out.exists() and (not out.is_dir() or (any(out.iterdir()) and not (out / MARKER).exists())):
        raise ValueError(f"--out {out} is not empty and was not made by stage")


def stage(repo: Path, out: Path) -> None:
    if not repo.is_dir():
        raise ValueError(f"{repo} is not a directory")
    check_out(repo, out)
    pages = []
    for p in sorted(repo.rglob("*.md")):
        rel = p.relative_to(repo)
        if set(rel.parts) & SKIP or p.is_relative_to(out):
            continue
        pages.append(rel.as_posix())
    where = {rel: rel for rel in pages}
    if "index.md" in where:
        where["index.md"] = "repo-index.md"
    if "README.md" in where:
        where["README.md"] = "index.md"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARKER).write_text("")
    for src_rel, dst_rel in where.items():
        text = (repo / src_rel).read_text()
        src_dir, dst_dir = posixpath.dirname(src_rel), posixpath.dirname(dst_rel)

        def fix(m: re.Match, src_dir: str = src_dir, dst_dir: str = dst_dir) -> str:
            target = m.group(2)
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE) or target.startswith(("#", "/")):
                return m.group(0)
            path, sep, anchor = target.partition("#")
            resolved = posixpath.normpath(posixpath.join(src_dir, path))
            if resolved in where:
                new = posixpath.relpath(where[resolved], dst_dir or ".")
            else:
                asset = repo / resolved
                if asset.is_file() and asset.resolve().is_relative_to(repo):
                    (out / resolved).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(asset, out / resolved)
                new = posixpath.relpath(resolved, dst_dir or ".")
            return m.group(1) + new + sep + anchor + m.group(3)

        (out / dst_rel).parent.mkdir(parents=True, exist_ok=True)
        (out / dst_rel).write_text(LINK.sub(fix, text))


def main() -> None:
    p = argparse.ArgumentParser(prog="stage")
    p.add_argument("repo")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    try:
        stage(Path(a.repo).resolve(), Path(os.path.abspath(a.out)).resolve())
    except (ValueError, OSError) as e:
        print(f"stage: {e}", file=sys.stderr)
        sys.exit(1)
