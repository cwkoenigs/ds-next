"""Summarise the maintenance test: per arm, regressions on the original judge, pass rate on the change
judge, how much of src/ and tests/ changed, cost and turns (medians with ranges).
Usage: python summarize_change.py [arm ...]"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

arms = sys.argv[1:] or ["without", "lessons", "lib", "both", "code"]
here = Path(__file__).resolve().parent


def med_range(xs: list[float], fmt: str = "{:.0f}") -> str:
    return f"{fmt.format(statistics.median(xs))} ({fmt.format(min(xs))} to {fmt.format(max(xs))})"


print(f"{'arm':8} {'n':>2} {'regressions':>12} {'change pass %':>22} {'src lines +-':>22} {'test lines +-':>22} {'$':>22} {'turns':>14}")
rows = []
for arm in arms:
    res = [json.loads(p.read_text()) for p in sorted(here.glob(f"runs/publish-change-{arm}-*/result.json"))]
    res = [r for r in res if r.get("change_total")]
    if not res:
        continue
    # a regression is a test the repo passed before the change and fails after it
    regress = 0
    for r in res:
        before = json.loads((here / f"runs/publish-{arm}-{r['run']}/result.json").read_text())
        regress += len(set(r["regression_failed"] or []) - set(before.get("failed") or []))
    pct = [100 * r["change_passed"] / r["change_total"] for r in res]
    src = [r["src_lines_changed"] for r in res]
    tst = [r["test_lines_changed"] for r in res]
    cost = [r["cost_usd"] or 0 for r in res]
    turns = [r["turns"] or 0 for r in res]
    failed = sorted({f for r in res for f in (r["regression_failed"] or []) + (r["change_failed"] or [])})
    print(f"{arm:8} {len(res):>2} {regress:>12} {med_range(pct, '{:.1f}'):>22} {med_range(src):>22} {med_range(tst):>22} "
          f"{med_range(cost, '{:.3f}'):>22} {med_range(turns):>14}")
    rows.append({"arm": arm, "n": len(res), "regressions": regress, "change_pass_median": statistics.median(pct),
                 "src_changed_median": statistics.median(src), "test_changed_median": statistics.median(tst),
                 "cost_median": statistics.median(cost), "turns_median": statistics.median(turns), "failed": failed})
print()
for r in rows:
    print(f"{r['arm']}: failed in some run: {r['failed']}")
(here / "runs/publish-change-summary.json").write_text(json.dumps(rows, indent=1))
