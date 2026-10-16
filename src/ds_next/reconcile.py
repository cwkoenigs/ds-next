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

DOCS = ("README.md", "AGENTS.md", "DECISIONS.md")
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


def check(repo: Path, canon: Canon | None = None, today: dt.date | None = None) -> Report:
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
    except tomllib.TOMLDecodeError as e:
        rep.errors.append(f"manifest is not valid TOML: {e}")
        return rep

    rep.repo = manifest.get("repo", {}).get("name", repo.name)
    rep.tags = list(manifest.get("repo", {}).get("tags", []))
    entries: dict = manifest.get("standards", {})
    for sid, e in entries.items():
        status = e.get("status")
        if sid not in canon.standards:
            rep.errors.append(f"manifest names {sid}, which the canon does not have")
            continue
        if status not in STATUSES:
            rep.errors.append(f"{sid}: status {status!r} is not one of {', '.join(STATUSES)}")
            continue
        if status == "declined":
            missing = [k for k in ("by", "reason", "revisit") if not e.get(k)]
            if missing:
                rep.errors.append(f"{sid}: a decline needs {', '.join(missing)}")
                continue
            rep.declined[sid] = e["reason"]
            if dt.date.fromisoformat(str(e["revisit"])) < today:
                rep.overdue.append(sid)

    for std in canon.applicable(rep.tags):
        e = entries.get(std.id, {})
        status = e.get("status")
        if status == "declined" and std.id in rep.declined:
            continue
        if status == "adopted" and int(e.get("version", 0)) >= std.version:
            rep.adopted.append(std.id)
        else:
            rep.pending.append(f"{std.id} v{std.version}")

    for doc in DOCS:
        f = repo / doc
        if f.is_file():
            rep.errors += [f"{doc}: [[{sid}]] does not resolve" for sid in canon.broken_pointers(f.read_text())]
    return rep
