"""`reconcile`: offline, deterministic, read-only. Compares a repo's manifest with the canon.

Pending standards are information. Only a malformed manifest, a broken pointer or a [uses] entry
that names nothing the canon's registry knows is an error, so the pre-push hook never blocks on a
standard nobody has decided on yet.
"""
from __future__ import annotations

import datetime as dt
import re
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
    blocks: list[str] = field(default_factory=list)       # "id vN" of accepted code in use
    type: str = ""                                        # project type from the scaffold
    outputs: list[str] = field(default_factory=list)      # declared outputs; publishing is not tracked yet
    notes: list[str] = field(default_factory=list)        # information about [uses] that is nobody's error yet
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        return f"{self.repo}: {self.counts()}"

    def counts(self) -> str:
        """The numbers without the name: 26 adopted · 1 declined · 0 pending (errors only when there are any)."""
        s = f"{len(self.adopted)} adopted · {len(self.declined)} declined · {len(self.pending)} pending"
        return s + (f" · {len(self.errors)} errors" if self.errors else "")


def find_repo(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        if (p / ".ds" / "manifest.toml").is_file():
            return p
    return None


def repo_name(repo: Path) -> str:
    """The manifest's [repo] name, or the directory's name when the manifest cannot say."""
    try:
        name = tomllib.loads((repo / ".ds" / "manifest.toml").read_text()).get("repo", {}).get("name")
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError, AttributeError):
        name = None
    return name if isinstance(name, str) and name else repo.name


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


def _check_blocks(manifest: dict, canon, rep) -> None:
    """Accepted code in use, and which copies are behind the canon. Runs even when the rest of the
    manifest is broken, so a stale block is never hidden behind another error."""
    blocks = manifest.get("blocks", {})
    if not isinstance(blocks, dict) or not all(isinstance(e, dict) for e in blocks.values()):
        rep.errors.append("[blocks] must hold one table per block, like [blocks.block-text-safety]")
        blocks = {}
    for bid, e in blocks.items():
        b = canon.blocks.get(bid)
        v = _version(e)
        if b is None:
            rep.errors.append(f"manifest uses block {bid}, which the canon does not have")
        elif v is None or v > b.version:
            rep.errors.append(f"block {bid}: version must be a whole number from 1 to v{b.version}, not {e.get('version')!r}")
        else:
            rep.blocks.append(f"{bid} v{v}")
            if v < b.version:
                rep.pending.append(f"{bid} v{b.version} (block; this repo has v{v})")


def _literal(entry: str) -> str:
    """What canon's build_repos.py scans for: the entry less `[optional parts]` and a trailing `*`."""
    s = re.sub(r"\s*\[[^\]]*\]", "", entry)
    return re.sub(r"\s+", " ", s).strip().removesuffix("*").rstrip()


def _resolves(use: str, declared: list[str]) -> bool:
    return use in declared or any(_literal(use) == _literal(d) for d in declared)


def _check_uses(manifest: dict, canon, rep) -> None:
    """[provides] and [uses] (canon adr-002) are tables of string lists. Each [uses] key must name a
    registered repo, and each entry something that repo declares: an error when the repo declares
    anything (a rename or a typo), a note while it declares nothing. Before the canon's pipeline has
    written the index's repos section, only the shapes are checked."""
    for table in ("provides", "uses"):
        t = manifest.get(table, {})
        if not isinstance(t, dict) or not all(isinstance(v, list) and v and all(isinstance(x, str) and x for x in v)
                                              for v in t.values()):
            rep.errors.append(f'[{table}] must hold lists of strings, like commands = ["ds-next mcp"]')
            return
    uses = manifest.get("uses", {})
    section = canon.repos
    if not uses or not section:
        return
    registered = {r["name"]: r for r in section.get("repos", []) if "name" in r}
    for target, entries in uses.items():
        provider = registered.get(target)
        if provider is None:
            rep.errors.append(f"[uses] names {target}, which the canon's registry does not have")
            continue
        declared = [e for es in provider.get("provides", {}).values() for e in es]
        missing = [u for u in entries if not _resolves(u, declared)]
        if not missing:
            continue
        if declared:
            rep.errors.append(f"[uses] {target}: {', '.join(missing)} is not among what {target} provides "
                              f"({', '.join(declared)})")
        else:
            rep.notes.append(f"uses {target}: {', '.join(missing)} ({target} declares nothing yet)")


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
        _check_blocks(manifest, canon, rep)
        return rep
    rep.tags = list(tags)
    if isinstance(head.get("type"), str):
        rep.type = head["type"]
    outs = head.get("outputs", [])
    if isinstance(outs, list) and all(isinstance(o, str) and o for o in outs):
        rep.outputs = list(outs)
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

    _check_blocks(manifest, canon, rep)
    _check_uses(manifest, canon, rep)

    for f in _docs(repo):
        try:
            text = f.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        rel = f.relative_to(repo).as_posix()
        rep.errors += [f"{rel}: {problem}" for problem in canon.pointer_problems(text)]
    return rep
