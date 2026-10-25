import difflib
import json
import sys
from pathlib import Path

W = sys.argv[1]
py, ts = json.loads(Path(f"{W}/out_py.json").read_text()), json.loads(Path(f"{W}/out_ts.json").read_text())
sc = json.loads(Path(f"{W}/scenarios.json").read_text())
bad = 0
def show(label, a, b):
    global bad
    bad += 1
    a, b = (a if isinstance(a, str) else json.dumps(a, indent=1, ensure_ascii=False)), (b if isinstance(b, str) else json.dumps(b, indent=1, ensure_ascii=False))
    d = list(difflib.unified_diff(a.splitlines(), b.splitlines(), "python", "ts", lineterm="", n=1))
    print(f"--- {label}"); print("\n".join(d[:14]) + ("\n..." if len(d) > 14 else ""))
for i, (p, t) in enumerate(zip(py["steps"], ts["steps"])):
    if p != t:
        show(f"step {i} {p['tool']} {json.dumps(sc['steps'][i]['args'])[:80]} (error py={p['error']} ts={t['error']})", p["text"], t["text"])
for sec in ("files", "captures"):
    for k in sorted(set(py[sec]) | set(ts[sec])):
        if py[sec].get(k) != ts[sec].get(k):
            show(f"{sec}: {k}", py[sec].get(k, "<missing>"), ts[sec].get(k, "<missing>"))
for sec in ("reconcile", "adopt"):
    for k in py[sec]:
        if py[sec][k] != ts[sec].get(k):
            show(f"{sec}: {k}", py[sec][k], ts[sec].get(k))
if py["pointers"] != ts["pointers"]: show("pointers", py["pointers"], ts["pointers"])
if py["usage"] != ts["usage"]: show("usage.jsonl", "\n".join(py["usage"]), "\n".join(ts["usage"]))
print(f"\n{bad} differences (2 are expected: see README); {len(py['steps'])} steps, {len(py['files'])} project files, {len(py['reconcile'])} reconcile cases, {len(py['adopt'])} adoptions compared")
