"""Cut a canon block down to some of its symbols, for `rule agent`'s code_get and code_add.

The functions below are ds-next's (src/ds_next/code.py), copied unchanged: the cut works on Python's
own syntax tree, so it stays in Python. Keep them in step with ds-next.

Reads one JSON request on stdin, writes one JSON answer on stdout:
  {"code": text, "names": [...], "header": text, "tests": [[path, text], ...],
   "module_import": "pkg.module", "test_header": text}
  -> {"code": text, "kept": [...], "tests": [[path, text], ...],
      "third_party_code": bool, "third_party_tests": [bool, ...]}
"""
from __future__ import annotations

import ast
import json
import re
import sys


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


def main() -> None:
    req = json.load(sys.stdin)
    code = shake(req["code"], set(req["names"]), req["header"])
    kept = set(_top(ast.parse(code)))
    tests = []
    for path, text in req["tests"]:
        t = shake_tests(text, req["module_import"], kept, req["test_header"])
        if t:
            tests.append([path, t])
    json.dump({"code": code, "kept": sorted(kept), "tests": tests,
               "third_party_code": _third_party(code),
               "third_party_tests": [_third_party(t) for _, t in tests]}, sys.stdout)


if __name__ == "__main__":
    main()
