"""The canon's code library, one function at a time.

build_index.py records every top-level function, class and constant in the canon's blocks
(index.json "code"). Here a model can search them by what they do, read one with only what it
needs, and add just those symbols to a repo: the module is cut down to them (and the private
helpers and constants they use), and so are the block's tests. The manifest records which
symbols a repo took, so reconcile sees when the canon updates them.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import os
import re
import sys
import tomllib
from pathlib import Path

from .kb import Canon, json_str

STOP = {"a", "an", "the", "to", "of", "in", "on", "for", "and", "or", "is", "it", "that", "with", "i",
        "need", "want", "how", "do", "from", "into", "by", "be", "as", "at", "my", "some", "this", "safely"}


def _words(text: str) -> list[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP]


def search(canon: Canon, query: str, limit: int = 8) -> list[dict]:
    """Accepted code symbols ranked by how well their name, summary and context match the query."""
    terms = _words(query)
    if not terms:
        return []
    titles = {b.id: b.title for b in canon.blocks.values()}
    scored = []
    for s in canon.code.values():
        if s["status"] != "accepted":
            continue
        fields = ((3, _words(s["name"])), (2, _words(s["summary"])),
                  (1, _words(s["signature"]) + _words(titles.get(s["block"], "")) + list(s["tags"]) + s["lessons"]))
        score = 0
        for t in terms:
            score += max((w for w, words in fields if any(x == t or (len(t) > 3 and x.startswith(t[:5]))
                                                         for x in words)), default=0)
        if score:
            scored.append((score, -s["lines"], s))
    return [s for _, _, s in sorted(scored, key=lambda x: (-x[0], -x[1], x[2]["id"]))[:limit]]


def _top(tree: ast.Module) -> dict[str, ast.stmt]:
    out: dict[str, ast.stmt] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for tg in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                for n in (tg.elts if isinstance(tg, ast.Tuple) else [tg]):
                    if isinstance(n, ast.Name):
                        out[n.id] = node
    return out


def _closure(top: dict[str, ast.stmt], roots: set[str]) -> set[str]:
    keep, todo = set(), [r for r in roots if r in top]
    while todo:
        n = todo.pop()
        if n not in keep:
            keep.add(n)
            todo += [u for u in _uses(top[n]) if u in top and u not in keep]
    return keep


def _import_text(nd: ast.Import | ast.ImportFrom, names: list[ast.alias], lines: list[str]) -> str:
    """The import as the source wrote it when nothing was dropped; otherwise rebuilt, wrapped the
    way isort wraps a long line."""
    if len(names) == len(nd.names):
        return "".join(lines[nd.lineno - 1:nd.end_lineno]).rstrip("\n")
    if isinstance(nd, ast.Import):
        return ast.unparse(ast.Import(names=names))
    one = ast.unparse(ast.ImportFrom(module=nd.module, names=names, level=nd.level))
    if len(one) <= 100:
        return one
    parts = [ast.unparse(ast.ImportFrom(module="x", names=[a], level=0)).split(" import ", 1)[1] for a in names]
    return f"from {'.' * nd.level}{nd.module or ''} import (\n" + "".join(f"    {x},\n" for x in parts) + ")"


def _uses(node: ast.AST) -> set[str]:
    names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):   # pytest fixtures arrive by argument name
        names |= {a.arg for a in node.args.args + node.args.kwonlyargs}
    return names


def _segment(lines: list[str], node: ast.stmt) -> str:
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])]) - 1
    while start > 0 and lines[start - 1].lstrip().startswith("#"):
        start -= 1
    return "".join(lines[start:node.end_lineno])


def shake(source: str, roots: set[str], header: str = "") -> str:
    """The module cut down to `roots` and everything at top level they use, in source order, with
    only the imports those need."""
    tree = ast.parse(source)
    # ast counts only \n as a line break; str.splitlines also breaks on \x0b, \x1c, \u2028 and others,
    # which can sit inside string literals, and would cut a function short.
    lines = re.split(r"(?<=\n)", source)
    top = _top(tree)
    keep = _closure(top, roots)
    kept_nodes = [nd for nd in tree.body if any(top.get(k) is nd for k in keep)]
    used = set().union(*(_uses(nd) for nd in kept_nodes)) if kept_nodes else set()
    out = [header] if header else []
    sections: list[list[str]] = []          # the source's import groups, so the cut stays lint-clean
    last_end = None
    for nd in tree.body:
        if not isinstance(nd, (ast.Import, ast.ImportFrom)):
            continue
        if last_end is None or any(not ln.strip() for ln in lines[last_end:nd.lineno - 1]):
            sections.append([])
        last_end = nd.end_lineno
        if isinstance(nd, ast.ImportFrom) and nd.module == "__future__":
            sections[-1].append(ast.unparse(nd))
            continue
        names = [a for a in nd.names if (a.asname or a.name).split(".")[0] in used]
        if names:
            sections[-1].append(_import_text(nd, names, lines))
    out.append("\n\n".join("\n".join(s) for s in sections if s) + "\n")
    seen = set()
    for i, nd in enumerate(kept_nodes):
        if id(nd) not in seen:
            seen.add(id(nd))
            # isort wants one blank line after imports before a constant, two before a def or class
            gap = "\n\n" if i or isinstance(nd, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else "\n"
            out.append(gap + _segment(lines, nd).rstrip("\n") + "\n")
    return "".join(out)


def shake_tests(source: str, module_import: str, kept: set[str], header: str = "") -> str | None:
    """The block's tests that use only kept symbols (and at least one), with their helpers."""
    tree = ast.parse(source)
    imported = set()
    for nd in tree.body:
        if isinstance(nd, ast.ImportFrom) and nd.module == module_import:
            imported |= {a.asname or a.name for a in nd.names}
    top = _top(tree)
    roots = set()
    for nd in tree.body:
        if isinstance(nd, (ast.FunctionDef, ast.AsyncFunctionDef)) and nd.name.startswith("test"):
            reach = _closure(top, {nd.name})                  # the test and every helper it calls
            from_module = set().union(*(_uses(top[n]) for n in reach)) & imported
            if from_module and from_module <= kept:
                roots.add(nd.name)
    if not roots:
        return None
    return shake(source, roots, header)


def _third_party(text: str) -> bool:
    for nd in ast.parse(text).body:
        mods = [a.name for a in nd.names] if isinstance(nd, ast.Import) else \
            [nd.module] if isinstance(nd, ast.ImportFrom) and nd.module and nd.level == 0 else []
        for m in mods:
            root = m.split(".")[0]
            if root not in sys.stdlib_module_names and root not in ("__future__", "pytest", "pkg"):
                return True
    return False


def pieces(canon: Canon, ids: list[str], package: str) -> dict[str, dict]:
    """{block id: {"symbols", "code" (path, text), "tests" [(path, text)], "block"}} for the ids."""
    by_block: dict[str, set[str]] = {}
    for sid in ids:
        s = canon.code.get(sid)
        if s is None:
            raise ValueError(f"no code symbol {sid!r}; code_search finds them (ids look like block-x:name)")
        if s["status"] != "accepted":
            raise ValueError(f"{sid} is in block {s['block']}, which is {s['status']}, not accepted")
        by_block.setdefault(s["block"], set()).add(s["name"])
    out = {}
    for bid, names in by_block.items():
        b = canon.blocks[bid]
        files = canon.block_files(bid, package)              # refuses files that changed since the index
        code_path = f"src/{package}/{b.module}.py"
        header = (f'"""From the canon\'s {bid} v{b.version}: {", ".join(sorted(names))} and what they need.\n'
                  f'Added with code_add; change it in the canon, not here."""\n')
        code = shake(files[code_path], names, header)
        kept = set(_top(ast.parse(code)))
        tests = []
        for path, text in files.items():
            if path.startswith("tests/"):
                t = shake_tests(text, f"{package}.{b.module}", kept, f'"""Tests from the canon\'s {bid} v{b.version}."""\n')
                if t:
                    tests.append((path, t))
        out[bid] = {"symbols": sorted(names), "code": (code_path, code), "tests": tests, "block": b}
    return out


def get(canon: Canon, sid: str) -> str:
    s = canon.code.get(sid)
    if s is None:
        raise ValueError(f"no code symbol {sid!r}; code_search finds them")
    p = pieces(canon, [sid], "yourpkg")[s["block"]]
    tests = "\n".join(f"--- {path}\n{text}" for path, text in p["tests"]) or "(no tests use only this)"
    return (f"{sid}  ({s['kind']}, block {s['block']} v{s['version']})\n{s['signature']}\n{s['summary']}\n"
            f"needs: {', '.join(s['needs']) or '-'}  lessons: {', '.join(s['lessons']) or '-'}\n\n"
            f"--- {p['code'][0]}\n{p['code'][1]}\n{tests}")


def usage_log(event: str, ids: list[str], repo: Path | None = None) -> None:
    """Append what was pulled to ~/.ds/usage.jsonl ($DS_STATE overrides), so a team sees what code is
    reused. Never fails the call."""
    try:
        state = Path(os.environ.get("DS_STATE") or Path.home() / ".ds")
        state.mkdir(parents=True, exist_ok=True)
        with open(state / "usage.jsonl", "a") as f:
            f.write(json.dumps({"at": dt.datetime.now().isoformat(timespec="seconds"), "event": event,
                                "ids": ids, "repo": str(repo) if repo else None}) + "\n")
    except OSError:
        pass


def add(repo: Path, ids: list[str], canon: Canon | None = None, by: str | None = None,
        today: dt.date | None = None) -> list[dict]:
    """Add these code symbols to the repo: each block's module cut down to them (plus what they
    need), and the block tests that use only them. Merges with symbols added before; a repo that
    already has the whole block keeps it."""
    from .scaffold import _add_to_list_line, _git_user, _inside

    canon = canon or Canon()
    repo = Path(repo).resolve()
    manifest_path = repo / ".ds" / "manifest.toml"
    if not manifest_path.is_file():
        raise ValueError(f"{repo} has no .ds/manifest.toml; create it with ds-next new first")
    manifest_text = manifest_path.read_text()
    manifest = tomllib.loads(manifest_text)
    package = str(manifest.get("repo", {}).get("name", "")).replace("-", "_")
    if not package or not (repo / "src" / package).is_dir():
        raise ValueError(f"{repo} has no src/{package}/ package to add code to")
    have = manifest.get("blocks", {})
    for sid in ids:                                   # every id is checked before anything is written
        s = canon.code.get(sid)
        if s is None:
            raise ValueError(f"no code symbol {sid!r}; code_search finds them (ids look like block-x:name)")
        if s["status"] != "accepted":
            raise ValueError(f"{sid} is in block {s['block']}, which is {s['status']}, not accepted")
    if not ids:
        raise ValueError("no ids given")
    wanted: dict[str, list[str]] = {}
    for sid in ids:
        wanted.setdefault(sid.split(":", 1)[0], []).append(sid)
    done = []
    for bid, sids in wanted.items():
        prior = have.get(bid)
        if prior is not None and "symbols" not in prior and prior.get("version") == canon.blocks[bid].version:
            done.append({"block": bid, "symbols": "all", "note": "the repo already has the whole block", "files": []})
            continue
        names = set(prior.get("symbols", [])) if prior else set()
        all_ids = sorted({f"{bid}:{n}" for n in names} | set(sids))
        p = pieces(canon, all_ids, package)[bid]
        files = {p["code"][0]: p["code"][1], **dict(p["tests"])}
        targets = {rel: _inside(repo, rel) for rel in files}
        if prior is None:
            clash = [rel for rel, t in targets.items() if t.exists()]
            if clash:
                raise FileExistsError(f"not added: {', '.join(clash)} already exist and were not written from {bid}")
        for rel, text in files.items():
            targets[rel].parent.mkdir(parents=True, exist_ok=True)
            targets[rel].write_text(text)
        b = p["block"]
        added, manual = [], []
        for key, reqs, texts in (("dependencies", list(b.requires), [p["code"][1]]),
                                 ("dev", list(b.test_requires), [t for _, t in p["tests"]])):
            if not reqs or not any(_third_party(t) for t in texts):
                continue
            pyproject = repo / "pyproject.toml"
            result = _add_to_list_line(pyproject.read_text() if pyproject.is_file() else "", key, reqs)
            if result is None:
                manual += [f"{r} ({key})" for r in reqs]
                continue
            if result[1]:
                pyproject.write_text(result[0])
            added += result[1]
        when = today or dt.date.today()
        table = (f"[blocks.{bid}]\nversion = {b.version}\nby = {json_str(by or _git_user())}\n"
                 f'on = "{when}"\nmodule = {json_str(p["code"][0])}\n'
                 f"symbols = [{', '.join(json_str(s) for s in p['symbols'])}]\n")
        existing = re.compile(rf"^\[blocks\.{re.escape(bid)}\]\n(?:(?!\[).*\n?)*", re.MULTILINE)
        if existing.search(manifest_text):
            manifest_text = existing.sub(table + "\n", manifest_text, count=1)
        else:
            manifest_text = manifest_text.rstrip("\n") + "\n\n" + table
        done.append({"block": bid, "symbols": p["symbols"], "files": sorted(files), "requires": added,
                     "manual": manual, "note": "updated" if prior else "added"})
    manifest_path.write_text(manifest_text)
    usage_log("code_add", ids, repo)
    return done
