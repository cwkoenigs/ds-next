"""Broken twins of the reference solutions: each carries one mistake the canon records, and the
named checks must fail on it. Usage: python mutants.py <workdir>"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable

MUTANTS = {
    "stamp": [
        ("plain f-string quoting", [
            ('f\'[project]\\nname = {lit(a.name)}\\ndescription = {lit(a.purpose)}\\n\'',
             'f\'[project]\\nname = "{a.name}"\\ndescription = "{a.purpose}"\\n\''),
            ('f"{lit(a.purpose)}\\n"', 'f\'"""{a.purpose}"""\\n\''),
            ('PURPOSE: {lit(a.purpose)}', 'PURPOSE: {a.purpose}')],
         ["hostile purpose survives exactly in TOML, Python, YAML and Markdown"]),
        ("templates filled by repeated replace", [
            ('"README.md": f"# {a.name}\\n\\n{a.purpose}\\n",',
             '"README.md": "# {{name}}\\n\\n{{purpose}}\\n".replace("{{purpose}}", a.purpose).replace("{{name}}", a.name),')],
         ["{{placeholders}} in user text stay literal"]),
        ("hooks always in .git/hooks", [
            ('hooks = Path(git(target, "rev-parse", "--git-path", "hooks"))', 'hooks = Path(".git/hooks")')],
         ["hook goes where git runs hooks (core.hooksPath)"]),
        ("hook embeds the command in single quotes", [
            ('exec sh -c {shlex.quote(a.check)}', "exec sh -c '{a.check}'")],
         ["hook keeps a quoted check command intact"]),
        ("no keyword check", [("    if keyword.iskeyword(pkg) or keyword.issoftkeyword(pkg):", "    if False:")],
         ["refuses names that are not valid or not importable"]),
        ("no symlink or non-empty check", [
            ("    if target.is_symlink():", "    if False:"),
            ("    if target.exists() and (not target.is_dir() or any(target.iterdir())):", "    if False:")],
         ["refuses a non-empty target and changes nothing in it", "refuses a target that is a symlink to somewhere else"]),
        ("git errors ignored", [("    if r.returncode != 0:\n        raise", "    if False:\n        raise")],
         ["a git failure is a failure (non-zero exit, one-line reason, no traceback)"]),
    ],
    "mcheck": [
        ("datetime accepted as a date", [("not isinstance(v, datetime)", "True")], ["a datetime is not a date"]),
        ("bool accepted as an int", [("isinstance(v, int) and not isinstance(v, bool)", "isinstance(v, (int, float))")],
         ["a version must be an integer (not a string, float or boolean)"]),
        ("reason checked by truthiness", [("not isinstance(reason, str) or not reason.strip()", "not reason")],
         ["a decline needs a non-empty text reason and a revisit date"]),
        ("only backtick fences masked", [("(`{3,}|~{3,})", "(```)")],
         ["--docs: pointers in code (fences, tildes, nested, inline) are ignored"]),
        ("raises on a bad manifest", [("    except (OSError, ValueError) as e:\n        return [f\"ERROR manifest",
                                       "    except KeyError as e:\n        return [f\"ERROR manifest")],
         ["malformed or wrongly shaped input is an ERROR line, never a traceback"]),
        ("a newer version never reopens a decline", [
            ('            elif v < versions[sid]:', '            elif v < versions[sid] and section == "adopted":')],
         ["a newer version reopens a decline (PENDING)"]),
    ],
    "stage": [
        ("README overwrites the repo's index.md", [('        where["index.md"] = "repo-index.md"', "        pass")],
         ["every page lands at its path; README is home; the repo's index.md is kept"]),
        ("links not rewritten", [("LINK.sub(fix, text)", "text")], ["every relative link still reaches the right page"]),
        ("assets not copied", [("                if asset.is_file() and", "                if False and")],
         ["linked assets are copied"]),
        ("output folder never checked", [("    check_out(repo, out)\n", "")],
         ["refuses the repo itself as output", "refuses the home directory", "refuses a non-empty folder it did not create"]),
        ("skip list ignored", [("        if set(rel.parts) & SKIP or", "        if")], ["skips .git, node_modules and .venv"]),
    ],
    "publish": [
        ("unknown pointer loses its pin", [
            ('errors.append(f"ERROR {src_rel}: {m.group(0)} is not in the catalogue")',
             'errors.append(f"ERROR {src_rel}: [[{sid}]] is not in the catalogue")')], []),
        ("pointers inside code are pointers", [("        if not is_code:\n", "        if True:\n")], []),
        ("datetime accepted as a date", [("not isinstance(v, datetime)", "True")], []),
        ("bool accepted as an int", [("isinstance(v, int) and not isinstance(v, bool)", "isinstance(v, (int, float))")], []),
        ("publishes despite errors", [('    if any(ln.startswith("ERROR") for ln in lines):\n        return 2\n',
                                       '    has_error = any(ln.startswith("ERROR") for ln in lines)\n')], []),
        ("link titles break rewriting", [
            ('((?:\\s+(?:\\"[^\\"]*\\"|\'[^\']*\'|\\([^)]*\\)))?\\s*\\))")', '(\\))")')], []),
        ("reference-style links not rewritten", [("            seg = REFDEF.sub(fix_ref, seg)\n", "")], []),
        ("assets not copied", [("    for rel in sorted(assets):\n", "    for rel in []:\n")], []),
        ("stale pages linger", [("    if out.exists():\n        shutil.rmtree(out)\n    out.mkdir(parents=True)\n",
                                 "    out.mkdir(parents=True, exist_ok=True)\n")], []),
        ("PENDING exits 0", [("    return 1 if lines else 0\n", "    return 0\n")], []),
        ("publish.json pages unsorted", [('"pages": sorted(rendered)', '"pages": sorted(rendered, reverse=True)')], []),
        ("README links from subfolders not rewritten", [
            ('        if resolved in where:\n', '        if resolved in where and "/" not in src_rel:\n')], []),
    ],
    "publish-change": [
        ("drafts are still errors", [('    level = "WARN" if "drafts" in Path(src_rel).parts[:-1] else "ERROR"\n',
                                      '    level = "ERROR"\n')], []),
        ("trailing slash kept on base url", [('    base = base.rstrip("/")\n', '    base = base\n')], []),
        ("warnings not counted", [('"warnings": sum(ln.startswith("WARN") for ln in lines)', '"warnings": 0')], []),
        ("a warning changes the exit code", [('    return 1 if any(ln.startswith("PENDING") for ln in lines) else 0\n',
                                             '    return 1 if lines else 0\n')], []),
        ("base url ignored for pinned pointers", [('(f"[{sid} v{pin}]({base}/standards/{sid}/v{pin}/)"',
                                                   '(f"[{sid} v{pin}](/standards/{sid}/v{pin}/)"')], []),
    ],
    "envcheck": [
        ("trailing comment kept in unquoted values", [('    m = re.search(r"\\s#", rest)\n    if m:\n        rest = rest[:m.start()]\n', '')], []),
        ("double-quote escapes not processed", [('            if c == "\\\\" and i + 1 < len(rest) and rest[i + 1] in ESCAPES:', '            if False:')], []),
        ("bool is case-sensitive", [('value.lower() not in BOOLS', 'value not in BOOLS')], []),
        ("port 0 and 65536 accepted", [('1 <= int(value) <= 65535', '0 <= int(value) <= 65536')], []),
        ("earlier file wins", [('        merged.update(found)\n', '        merged = {**found, **merged}\n')], []),
        ("unknown variables ignored", [('            errors.append(f"ERROR {name}: not in the schema")\n', '            pass\n')], []),
        ("--print leaves values unquoted", [('            print(f"{name}={quote(final[name])}")', '            print(f"{name}={final[name]}")')], []),
        ("export prefix rejected", [('        if line.startswith(("export ", "export\\t")):\n            line = line[7:].lstrip()\n', '')], []),
        ("defaults not filled in", [('                final[name] = spec["default"]\n', '                pass\n')], []),
    ],
    "envmerge": [
        ("out written despite errors", [('    if errors:\n        sys.exit(1)\n    try:\n        write_out(', '    try:\n        write_out(')], []),
        ("unknown allowed without the flag", [('            if allow_unknown:\n', '            if True:\n')], []),
        ("header lacks the file names", [("    text = f\"# generated by envmerge from {', '.join(names)}\\n\" + \"\".join(",
                                         '    text = "# generated by envmerge\\n" + "".join(')], []),
        ("earlier file wins", [('        merged.update(found)\n', '        merged = {**found, **merged}\n')], []),
        ("values not quoted in out", [('        f"{name}={quote(final[name])}\\n" for name in sorted(final))', '        f"{name}={final[name]}\\n" for name in sorted(final))')], []),
        ("MERGED count excludes defaults", [('    print(f"MERGED {len(final)} from {len(a.files)} files")', '    print(f"MERGED {len(merged)} from {len(a.files)} files")')], []),
        ("bool is case-sensitive", [('value.lower() not in BOOLS', 'value not in BOOLS')], []),
    ],
}


def main() -> None:
    work = Path(sys.argv[1])
    bad = []
    for task, mutants in MUTANTS.items():
        if not (HERE / task / "check.py").exists():
            continue
        src = (HERE / "ref" / f"{task}.py").read_text()
        for i, (label, edits, expect) in enumerate(mutants):
            text = src
            for old, new in edits:
                if text.count(old) != 1:
                    raise SystemExit(f"{task} mutant {label!r}: edit not found once: {old[:60]!r}")
                text = text.replace(old, new)
            mod = work / f"{task}-m{i}.py"
            mod.write_text(text)
            repo = work / f"{task}-m{i}"
            subprocess.run([str(HERE / "ref" / "make_ref.sh"), task, str(mod), str(repo)], check=True,
                           capture_output=True)
            out = subprocess.run([PY, str(HERE / task / "check.py"), str(repo)], capture_output=True, text=True, check=False).stdout
            failed = set(re.findall(r"^FAIL  (.+?)  ", out, re.MULTILINE))
            missed = [e for e in expect if e not in failed]
            print(f"{'ok  ' if not missed else 'MISS'} {task}: {label} -> fails {sorted(failed)}")
            if missed:
                bad.append((task, label, missed))
    print("\nall mutants caught" if not bad else f"\n{len(bad)} mutants not caught: {bad}")


main()
