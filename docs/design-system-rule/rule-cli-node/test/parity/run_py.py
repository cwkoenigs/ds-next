"""ds-next's own Python, through the steps."""
import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

os.environ["DS_AGENT"] = "claude"
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))  # ds-next/src, five folders up
from ds_next import agent, kb, reconcile, scaffold

ROOT, CANON, SKILLS, SCEN, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], sys.argv[5]
os.environ["DS_STATE"] = str(ROOT / "state")
canon, skills = kb.Canon(CANON), kb.Skills(SKILLS)
sc = json.loads(Path(SCEN).read_text())
(ROOT / "work").mkdir(parents=True)
(ROOT / "projects").mkdir()
norm = lambda t: t.replace(str(ROOT), "<ROOT>")
cache = {}
def tools_for(cwd):
    if cwd not in cache:
        cache[cwd] = {t.name: t for t in agent.tools(canon, skills, ROOT / cwd)}
    return cache[cwd]
steps = []
for st in sc["steps"]:
    args = json.loads(json.dumps(st["args"]).replace("<ROOT>", str(ROOT)))
    t = tools_for(st["cwd"]).get(st["tool"])
    try:
        r = asyncio.run(t.handler(args))
        steps.append({"tool": st["tool"], "text": norm(r["content"][0]["text"]), "error": bool(r.get("is_error"))})
    except Exception as e:  # noqa: BLE001
        steps.append({"tool": st["tool"], "text": f"EXCEPTION {type(e).__name__}: {norm(str(e))}", "error": True})
def tree(base):
    out = {}
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base).as_posix()
        if not p.is_file() or ("/.git/" in "/" + rel and not rel.endswith("hooks/pre-push")):
            continue  # git's own files, except the hook ds writes
        out[rel] = norm(p.read_text(errors="replace"))
    return out
rep = lambda r: {"repo": r.repo, "tags": r.tags, "adopted": r.adopted, "declined": r.declined, "pending": r.pending, "overdue": r.overdue,
                 "blocks": r.blocks, "type": r.type, "outputs": r.outputs, "errors": [norm(e) for e in r.errors]}
recon = {}
for case in sc["reconcile"]:
    d = ROOT / "recon" / case["name"]
    d.mkdir(parents=True)
    if case["manifest"] is not None:
        (d / ".ds").mkdir()
        (d / ".ds" / "manifest.toml").write_text(case["manifest"])
    for rel, text in case["docs"].items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text)
    recon[case["name"]] = rep(reconcile.check(d, canon))
pointers = [canon.pointer_problems(t) for t in sc["pointers"]]
adopt = {}
for case in sc["adopt"]:
    d = ROOT / "existing" / case["name"]
    d.mkdir(parents=True)
    for rel, text in case["files"].items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text)
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    a = scaffold.detect(d)
    det = {"name": a.name, "purpose": a.purpose, "owner": a.owner, "tags": a.tags, "test_cmd": a.test_cmd, "lint_cmd": a.lint_cmd}
    try:
        written = scaffold.adopt(d, a, canon, skills, adopt_all=case["adopt_all"])
        adopt[case["name"]] = {"detect": det, "written": written, "summary": reconcile.check(d, canon).summary(), "files": tree(d)}
    except Exception as e:  # noqa: BLE001
        adopt[case["name"]] = {"detect": det, "error": f"{type(e).__name__}: {norm(str(e))}"}
usage = []
if (ROOT / "state" / "usage.jsonl").exists():
    usage = [re.sub(r'"at": "[^"]+"', '"at": "<AT>"', norm(l)) for l in (ROOT / "state" / "usage.jsonl").read_text().splitlines()]
Path(OUT).write_text(json.dumps({"steps": steps, "files": tree(ROOT / "projects"), "captures": tree(ROOT / "work"), "reconcile": recon,
                                 "pointers": pointers, "adopt": adopt, "usage": usage}, indent=1, ensure_ascii=False))
print("python:", len(steps), "steps,", len(tree(ROOT / "projects")), "project files")
