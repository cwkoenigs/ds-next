"""`reconcile`: offline, deterministic, read-only. Compares a repo's manifest with the canon.

Pending standards are information. Only a malformed manifest or a broken pointer is an error,
so the pre-push hook never blocks on a standard nobody has decided on yet.
"""
from __future__ import annotations

import datetime as dt
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .kb import Canon

STATUSES = ("adopted", "declined", "pending")


@dataclass
class Report:
    repo: str
    tags: list[str] = field(default_factory=list)
    adopted: list[str] = field(default_factory=list)
    declined: dict[str, str] = field(default_factory=dict)
    pending: list[str] = field(default_factory=list)      # "id vN" strings
    overdue: list[str] = field(default_factory=list)      # declines past their revisit date
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        return (f"{self.repo}: {len(self.adopted)} adopted, {len(self.declined)} declined, "
                f"{len(self.pending)} pending, {len(self.errors)} errors")


def find_repo(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        if (p / ".ds" / "manifest.toml").is_file():
            return p
    return None


SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "site", "build", "dist", "__pycache__"}


def _docs(repo: Path) -> list[Path]:
    """Every Markdown file a person would read: the root docs plus anything under docs/ or
    elsewhere, skipping hidden, generated and vendored directories."""
    out = []
    for f in sorted(repo.rglob("*.md")):
        rel = f.relative_to(repo).parts
        if any(p in SKIP_DIRS or p.startswith(".") for p in rel[:-1]) or f.is_symlink():
            continue
        out.append(f)
    return out


def _version(e: dict) -> int | None:
    v = e.get("version")
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 1 else None


def check(repo: Path, canon: Canon | None = None, today: dt.date | None = None) -> Report:
    """Never raises on a bad manifest: every problem becomes an error line, so the hook and
    the terminal always get an answer."""
    canon = canon or Canon()
    today = today or dt.date.today()
    repo = Path(repo).resolve()
    rep = Report(repo.name)
    path = repo / ".ds" / "manifest.toml"
    try:
        manifest = tomllib.loads(path.read_text())
    except FileNotFoundError:
        rep.errors.append("no .ds/manifest.toml (create the repo with ds-next new)")
        return rep
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        rep.errors.append(f"manifest is not valid TOML: {e}")
        return rep

    head = manifest.get("repo")
    if not isinstance(head, dict):
        rep.errors.append("manifest has no [repo] table")
        return rep
    if isinstance(head.get("name"), str) and head["name"]:
        rep.repo = head["name"]
    else:
        rep.errors.append("[repo] name must be a non-empty string")
    tags = head.get("tags")
    if not (isinstance(tags, list) and tags and all(isinstance(t, str) and t for t in tags)):
        rep.errors.append("[repo] tags must be a non-empty list of strings")
        return rep
    rep.tags = list(tags)
    entries = manifest.get("standards", {})
    if not isinstance(entries, dict) or not all(isinstance(e, dict) for e in entries.values()):
        rep.errors.append("[standards] must hold one table per standard, like [standards.testing]")
        return rep

    for sid, e in entries.items():
        status = e.get("status")
        if sid not in canon.standards:
            rep.errors.append(f"manifest names {sid}, which the canon does not have")
            continue
        if status not in STATUSES:
            rep.errors.append(f"{sid}: status {status!r} is not one of {', '.join(STATUSES)}")
            continue
        if status in ("adopted", "declined") and _version(e) is None:
            rep.errors.append(f"{sid}: version must be a whole number from 1 up, not {e.get('version')!r}")
            continue
        if status in ("adopted", "declined") and not (isinstance(e.get("by"), str) and e["by"].strip()):
            rep.errors.append(f"{sid}: by must name who decided, not {e.get('by')!r}")
            continue
        if status in ("adopted", "declined") and _version(e) > canon.standards[sid].version:
            rep.errors.append(f"{sid}: {status} at v{_version(e)}, but the canon only has "
                              f"v{canon.standards[sid].version}")
            continue
        if status == "declined":
            missing = [k for k, ok in (("reason", isinstance(e.get("reason"), str) and e["reason"].strip()),
                                       ("revisit", e.get("revisit") not in (None, ""))) if not ok]
            if missing:
                rep.errors.append(f"{sid}: a decline needs {', '.join(missing)}")
                continue
            revisit = e["revisit"]
            if isinstance(revisit, str):
                try:
                    revisit = dt.date.fromisoformat(revisit)
                except ValueError:
                    revisit = None
            if not isinstance(revisit, dt.date) or isinstance(revisit, dt.datetime):
                rep.errors.append(f"{sid}: revisit must be a date like 2027-01-31, not {e['revisit']!r}")
                continue
            rep.declined[sid] = str(e["reason"])
            if revisit < today:
                rep.overdue.append(sid)

    for std in canon.applicable(rep.tags):
        e = entries.get(std.id, {})
        status = e.get("status")
        if status == "declined" and std.id in rep.declined:
            if (_version(e) or 0) >= std.version:
                continue
            # a decline answers the version it was made against; a newer one is a new question
            del rep.declined[std.id]
            rep.overdue = [s for s in rep.overdue if s != std.id]
            rep.pending.append(f"{std.id} v{std.version} (declined at v{_version(e)})")
            continue
        if status == "adopted" and (_version(e) or 0) >= std.version:
            rep.adopted.append(std.id)
        elif not any(err.startswith(f"{std.id}:") for err in rep.errors):
            rep.pending.append(f"{std.id} v{std.version}")

    for f in _docs(repo):
        try:
            text = f.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        rel = f.relative_to(repo).as_posix()
        rep.errors += [f"{rel}: {problem}" for problem in canon.pointer_problems(text)]
    return rep
