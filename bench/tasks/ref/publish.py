"""Reference `publish`: validates the judge (its tests must pass here, and fail on the mutants)."""
from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import shutil
import sys
import tomllib
from datetime import date, datetime
from pathlib import Path

SKIP = {".git", "node_modules", ".venv"}
MARKER = ".published-by-publish"
POINTER = re.compile(r"\[\[([a-z0-9-]+)(?:@(\d+))?\]\]")
CODE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]{0,3}\1[`~]*[ \t]*$|\Z)|(`+)[^`\n].*?\2",
                  re.DOTALL | re.MULTILINE)
# [text](dest "title") and ![alt](dest); dest may be <in angle brackets>
INLINE = re.compile(r"(!?\[[^\]]*\]\(\s*)(<[^>\n]*>|[^)\s]+)((?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\))")
# [label]: dest "title"
REFDEF = re.compile(r"^([ ]{0,3}\[[^\]]+\]:[ \t]*)(<[^>\n]*>|\S+)(.*)$", re.MULTILINE)
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def is_date(v) -> bool:
    return isinstance(v, date) and not isinstance(v, datetime)


def segments(text: str):
    """(is_code, piece) in order, so prose can be rewritten and code left alone."""
    pos = 0
    for m in CODE.finditer(text):
        if m.start() > pos:
            yield False, text[pos:m.start()]
        yield True, m.group(0)
        pos = m.end()
    if pos < len(text):
        yield False, text[pos:]


def check_manifest(path: Path, versions: dict[str, int]) -> tuple[list[str], list[str]]:
    """(report lines, adopted ids)."""
    out: list[str] = []
    try:
        m = tomllib.loads(path.read_text())
    except (OSError, ValueError) as e:
        return [f"ERROR manifest: cannot read {path}: {e}"], []
    seen, adopted = set(), []
    for section in ("adopted", "declined"):
        table = m.get(section, {})
        if not isinstance(table, dict):
            out.append(f"ERROR manifest: [{section}] must be a table of tables")
            continue
        for sid, entry in table.items():
            seen.add(sid)
            if not isinstance(entry, dict):
                out.append(f"ERROR {sid}: [{section}.{sid}] must be a table")
                continue
            if section == "adopted":
                adopted.append(sid)
            v = entry.get("version")
            if sid not in versions:
                out.append(f"ERROR {sid}: not in the catalogue")
                continue
            if not is_int(v):
                out.append(f"ERROR {sid}: version must be an integer")
            elif not 1 <= v <= versions[sid]:
                out.append(f"ERROR {sid}: version {v} is one the catalogue never had (current {versions[sid]})")
            elif v < versions[sid]:
                out.append(f"PENDING {sid}: {section} v{v}, the catalogue has v{versions[sid]}")
            if section == "adopted" and not is_date(entry.get("date")):
                out.append(f"ERROR {sid}: date must be a TOML date")
            if section == "declined":
                reason = entry.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    out.append(f"ERROR {sid}: reason must be non-empty text")
                if not is_date(entry.get("revisit")):
                    out.append(f"ERROR {sid}: revisit must be a TOML date")
    for sid in versions:
        if sid not in seen:
            out.append(f"PENDING {sid}: not adopted or declined")
    return out, sorted(adopted)


def load_index(path: Path) -> dict[str, int] | str:
    try:
        rows = json.loads(path.read_text())["standards"]
        versions = {r["id"]: r["version"] for r in rows}
        if not all(isinstance(k, str) and is_int(v) for k, v in versions.items()):
            raise ValueError("bad entry")
        return versions
    except (OSError, ValueError, KeyError, TypeError) as e:
        return f"ERROR index: cannot read {path}: {e}"


def plan(repo: Path, out: Path) -> dict[str, str]:
    pages = []
    for p in sorted(repo.rglob("*.md")):
        rel = p.relative_to(repo)
        if set(rel.parts) & SKIP or p.resolve().is_relative_to(out):
            continue
        pages.append(rel.as_posix())
    where = {rel: rel for rel in pages}
    if "index.md" in where:
        where["index.md"] = "repo-index.md"
    for rel in pages:  # the ticket says README.md becomes index.md, and qualifies only index.md as top-level
        if posixpath.basename(rel) == "README.md":
            where[rel] = posixpath.join(posixpath.dirname(rel), "index.md")
    return where


def rewrite(text: str, src_rel: str, dst_rel: str, where: dict[str, str], repo: Path, versions: dict[str, int],
            assets: set[str], counts: dict[str, int]) -> tuple[str, list[str]]:
    src_dir, dst_dir = posixpath.dirname(src_rel), posixpath.dirname(dst_rel)
    errors: list[str] = []

    def new_target(target: str) -> str:
        raw = target[1:-1] if target.startswith("<") and target.endswith(">") else target
        if not raw or SCHEME.match(raw) or raw.startswith(("#", "/")):
            return target
        path, sep, anchor = raw.partition("#")
        resolved = posixpath.normpath(posixpath.join(src_dir, path))
        if resolved in where:
            new = posixpath.relpath(where[resolved], dst_dir or ".")
        else:
            asset = repo / resolved
            if not resolved.startswith("..") and asset.is_file() and asset.resolve().is_relative_to(repo):
                assets.add(resolved)
            return target
        new += sep + anchor
        return f"<{new}>" if target.startswith("<") else new

    def fix_inline(m: re.Match) -> str:
        return m.group(1) + new_target(m.group(2)) + m.group(3)

    def fix_ref(m: re.Match) -> str:
        return m.group(1) + new_target(m.group(2)) + m.group(3)

    def fix_pointer(m: re.Match) -> str:
        sid, pin = m.group(1), m.group(2)
        if sid not in versions:
            errors.append(f"ERROR {src_rel}: {m.group(0)} is not in the catalogue")
            return m.group(0)
        if pin is not None and not 1 <= int(pin) <= versions[sid]:
            errors.append(f"ERROR {src_rel}: {m.group(0)} pins a version the catalogue never had")
            return m.group(0)
        counts[sid] = counts.get(sid, 0) + 1
        return f"[{sid} v{pin}](/standards/{sid}/v{pin}/)" if pin is not None else f"[{sid}](/standards/{sid}/)"

    pieces = []
    for is_code, seg in segments(text):
        if not is_code:
            seg = INLINE.sub(fix_inline, seg)
            seg = REFDEF.sub(fix_ref, seg)
            seg = POINTER.sub(fix_pointer, seg)
        pieces.append(seg)
    return "".join(pieces), errors


def publish(repo: Path, index: Path, out: Path) -> int:
    if not repo.is_dir():
        raise ValueError(f"{repo} is not a directory")
    for danger in (Path.home().resolve(), Path(out.anchor)):
        if out == danger:
            raise ValueError(f"--out {out} would delete {danger}")
    if out == repo or repo.is_relative_to(out):
        raise ValueError(f"--out {out} contains the repo")
    if out.exists() and (not out.is_dir() or (any(out.iterdir()) and not (out / MARKER).exists())):
        raise ValueError(f"--out {out} is not empty and was not made by publish")
    versions = load_index(index)
    if isinstance(versions, str):
        lines = [versions]
        print(versions)
        return 2
    lines, adopted = check_manifest(repo / ".ds" / "manifest.toml", versions)
    where = plan(repo, out)
    rendered: dict[str, str] = {}
    assets: set[str] = set()
    counts: dict[str, int] = {}
    for src_rel, dst_rel in where.items():
        text = (repo / src_rel).read_text(encoding="utf-8", errors="replace")
        rendered[dst_rel], errs = rewrite(text, src_rel, dst_rel, where, repo, versions, assets, counts)
        lines.extend(errs)
    lines = sorted(set(lines))
    for ln in lines:
        print(ln)
    if any(ln.startswith("ERROR") for ln in lines):
        return 2
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARKER).write_text("")
    for dst_rel, text in rendered.items():
        (out / dst_rel).parent.mkdir(parents=True, exist_ok=True)
        (out / dst_rel).write_text(text, encoding="utf-8")
    for rel in sorted(assets):
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / rel, out / rel)
    meta = {"repo": repo.name, "adopted": adopted, "pages": sorted(rendered),
            "pointers": {k: counts[k] for k in sorted(counts)}}
    (out / "publish.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 1 if lines else 0


def main() -> None:
    p = argparse.ArgumentParser(prog="publish")
    p.add_argument("repo")
    p.add_argument("--index", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    try:
        code = publish(Path(a.repo).resolve(), Path(a.index), Path(os.path.abspath(a.out)).resolve())
    except (ValueError, OSError) as e:
        print(f"publish: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
