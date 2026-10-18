"""Summarise the honest test for one task: per arm, the judge's pass rate (median and range over
runs), how often canon code was used, own code size, cost and turns, plus how alike the builds in
an arm are (pairwise similarity of the code they wrote themselves; Jaccard of what they pulled).
Usage: python summarize.py <task> [arm ...]"""
from __future__ import annotations

import difflib
import itertools
import json
import statistics
import sys
from pathlib import Path

task = sys.argv[1]
arms = sys.argv[2:] or ["without", "lessons", "lib", "both", "code"]
here = Path(__file__).resolve().parent
rows = []
for arm in arms:
    runs = sorted(here.glob(f"runs/{task}-{arm}-*/result.json"))
    res = [json.loads(p.read_text()) for p in runs]
    res = [r for r in res if r.get("total")]
    if not res:
        continue
    pct = [100 * r["passed"] / r["total"] for r in res]
    used = [bool(r.get("canon_lib") or r.get("code_add")) for r in res]
    cost = [r["cost_usd"] or 0 for r in res]
    own: list[str] = []
    pulled: list[set[str]] = []
    for p, r in zip(runs, res):
        repo = Path((p.parent / "repo.txt").read_text().strip())
        files = sorted((repo / "src").rglob("*.py")) if (repo / "src").exists() else []
        texts = [f.read_text(errors="replace") for f in files]
        own.append("\n".join(t for t in texts if not t.startswith("\"\"\"From the canon's block-")))
        pulled.append(set(r.get("canon_lib", [])) | set(r.get("code_add", [])))
    sim = [difflib.SequenceMatcher(None, a, b).ratio() for a, b in itertools.combinations(own, 2)]
    jac = [len(a & b) / len(a | b) if a | b else 1.0 for a, b in itertools.combinations(pulled, 2)]
    failed = sorted({f for r in res for f in r["failed"]})
    rows.append({"arm": arm, "n": len(res), "pass_median": statistics.median(pct), "pass_min": min(pct),
                 "pass_max": max(pct), "used_canon": f"{sum(used)}/{len(used)}",
                 "own_lines_median": statistics.median(r.get("own_lines", 0) for r in res),
                 "cost_median": statistics.median(cost), "cost_min": min(cost), "cost_max": max(cost),
                 "turns_median": statistics.median(r.get("turns") or 0 for r in res),
                 "own_code_similarity": statistics.mean(sim) if sim else None,
                 "pulled_jaccard": statistics.mean(jac) if jac else None, "failed_tests": failed})
hdr = f"{'arm':8} {'n':>2} {'pass% med (min-max)':>22} {'used':>5} {'own lines':>9} {'$ med (min-max)':>22} {'turns':>5} {'own sim':>8} {'pull jac':>8}"
print(hdr)
for r in rows:
    sim = f"{r['own_code_similarity']:.2f}" if r["own_code_similarity"] is not None else "-"
    jac = f"{r['pulled_jaccard']:.2f}" if r["pulled_jaccard"] is not None else "-"
    print(f"{r['arm']:8} {r['n']:>2} {r['pass_median']:6.1f} ({r['pass_min']:5.1f}-{r['pass_max']:5.1f})      {r['used_canon']:>5} "
          f"{r['own_lines_median']:9.0f} {r['cost_median']:7.3f} ({r['cost_min']:.3f}-{r['cost_max']:.3f})    {r['turns_median']:5.0f} {sim:>8} {jac:>8}")
print()
for r in rows:
    print(f"{r['arm']}: failed in some run: {r['failed_tests']}")
(here / f"runs/{task}-summary.json").write_text(json.dumps(rows, indent=1))
