"""Does the blind judge catch planted bugs? Build the reference and each mutant (bench/tasks/mutants.py)
as a uv project, score each with the judge's tests, and report what the judge misses. A judge that the
reference does not pass, or that misses most mutants, cannot score builds.
Usage: python validate.py <workdir> <task> [task ...]"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = HERE.parent / "tasks"
WORK = Path(sys.argv[1]).resolve()
WORK.mkdir(parents=True, exist_ok=True)
ONLY = sys.argv[2:]
ns: dict = {"__file__": str(TASKS / "mutants.py")}
exec(compile((TASKS / "mutants.py").read_text().replace("\nmain()\n", "\n"), "mutants", "exec"), ns)  # noqa: S102
MUTANTS = ns["MUTANTS"]


def score(task: str, repo: Path) -> dict:
    r = subprocess.run([sys.executable, str(HERE / "score.py"), task, str(repo)], capture_output=True, text=True,
                       check=False)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return {"passed": -1, "total": -1, "failed": [r.stderr[-300:]]}


def build(task: str, module: Path, repo: Path) -> None:
    subprocess.run([str(TASKS / "ref" / "make_ref.sh"), task, str(module), str(repo)], check=True, capture_output=True)


summary = {}
for task, mutants in MUTANTS.items():
    if ONLY and task not in ONLY:
        continue
    source = (TASKS / "ref" / f"{task}.py").read_text()
    ref = WORK / f"{task}-ref"
    build(task, TASKS / "ref" / f"{task}.py", ref)
    base = score(task, ref)
    print(f"{task} reference: {base['passed']}/{base['total']} failed={base['failed']}", flush=True)
    caught = 0
    for i, (label, edits, _expect) in enumerate(mutants):
        text = source
        for old, new in edits:
            assert text.count(old) == 1, (task, label, old[:50])
            text = text.replace(old, new)
        module = WORK / f"{task}-m{i}.py"
        module.write_text(text)
        repo = WORK / f"{task}-m{i}"
        build(task, module, repo)
        s = score(task, repo)
        new_fail = sorted(set(s["failed"]) - set(base["failed"]))
        caught += bool(new_fail)
        print(f"  {'caught' if new_fail else 'MISSED'} {label!r}: {s['passed']}/{s['total']} new failures={new_fail}",
              flush=True)
    summary[task] = {"reference": f"{base['passed']}/{base['total']}", "reference_failed": base["failed"],
                     "caught": caught, "of": len(mutants)}
print(json.dumps(summary, indent=1))
(HERE / "validation.json").write_text(json.dumps(summary, indent=1))
