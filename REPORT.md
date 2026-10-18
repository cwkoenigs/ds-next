# The team knowledge system: what it is, what we proved, what to build

2026-10-17. Final report on the proof of concept. The long, chronological record with every
mistake is [HANDOFF.md](HANDOFF.md); this is the result and the decision.

## 1. The idea

*"My team's software could almost become plug and play. AI only gets more accurate as the code
base grew. People would almost always pull the same code."*

Put the team's knowledge in one place (canon): standards, lessons learned, and accepted code. Any
agent, any model, reads it before it writes code, and pulls accepted code instead of rewriting it.
When a build teaches something, it goes back into canon.

## 2. The verdict

**Ship the package. Drop the lessons as they are.**

| Claim | Result |
|---|---|
| People pull the same code | **Shown.** 15 of 15 builds with code access pulled it; the same modules every time. |
| Less code written from scratch | **Shown.** 35% less on a 450-line task, 61% less once canon held the domain's code. |
| Fix it once, everywhere | **Shown.** One fix in the package repaired three repos with zero changes to them. |
| It pays off as the library grows | **Shown.** Code promoted from one real build was pulled by every sibling build. |
| Safe to change later | **Shown.** 15 change builds, zero regressions. |
| AI gets more accurate | **Not shown, and not testable here.** Haiku scored 96 to 100% without canon on all five tasks. There was nothing to improve. |
| Lessons (gotchas) help | **No.** 2× cost in every round, no judge points, and one lesson overrode the ticket silently. |

## 3. What was built

Four repos, all local, nothing pushed. canon's work is on branch `lessons`.

| Where | What |
|---|---|
| `~/Developer/canon` | 29 standards, 11 gotchas, 2 scaffolds, **13 blocks** of accepted code (69 functions, classes and constants, every one stands alone), **canon-lib** (`lib/`, the blocks as one installable package, 145 tests), `index.json`, `scripts/promote.py` |
| `~/Developer/ds-next` | the CLI and terminal UI over Cortex Code; **`ds-next mcp`**, which serves canon to any MCP agent (lessons, scaffolds, blocks, `code_search`, `code_get`, `code_add`); the benches (`bench/`); 113 tests |
| `~/Developer/skills-os`, `~/Developer/docs-ds` | procedures, and the docs renderer; unchanged |

The design went through five versions. The last is current.

| # | Version | Added | Tested |
|---|---|---|---|
| 1 | Standards | canon holds standards; ds-next scaffolds and reconciles repos against it | rebuild series |
| 2 | Lessons and blocks | gotchas; accepted code as whole modules copied into repos | rebuild series |
| 3 | Any agent | `ds-next mcp`: Claude, Cortex and others reach canon the same way | round 1 |
| 4 | Function library | accepted code searched and pulled one function at a time | rounds 1 to 3 |
| 5 | **Minimal: lessons + canon-lib** | one local package repos import; no serving layer | **rounds 1 to 3** |

## 4. How it was tested

Every number below comes from the same method, built after the first round was found circular.

- **A blind judge.** For each task a separate Opus run saw only the ticket, never canon, my checks
  or my solutions, and wrote hidden tests. Nobody edited them.
- **Judges validated before scoring.** A reference solution had to pass, and planted bugs had to
  fail: publish 9 of 12 caught, change 5 of 5, envcheck 9 of 9, envmerge 7 of 7.
- **Arms that isolate the mechanism.** Same ticket, same empty repo, Haiku 5.5, three builds each:
  nothing; lessons only; package only; both; function library over MCP. `~/Developer` unreadable to
  the builder.
- **Medians with ranges**, not means. Cost varied 4× run to run.

## 5. Results

### 5.1 Building: `publish` (manifest check + docs staging + pointer links; 57 judge cases)

| Arm | Judge | Lines written | Cost | Turns |
|---|---|---|---|---|
| nothing | 100% (96.5 to 100) | 426 | $0.207 | 29 |
| lessons | 96.5% | 446 | $0.494 | 74 |
| **package** | **100%** | **277** | **$0.101** | 37 |
| both | 96.5% | 317 | $0.304 | 65 |
| function library | 100% (96.5 to 100) | 280 | $0.200 | 64 |

The only failures in any arm were two tests on an ambiguous README rule. The lessons arms failed
them 3 of 3 because a gotcha encodes one project's decision, and the agent followed it over the
ticket without saying so.

### 5.2 Changing: the same 15 repos, a change ticket (44 judge cases for the change, 57 for regressions)

| Arm | Regressions | Change judge | Source lines changed | Cost | Turns |
|---|---|---|---|---|---|
| nothing | 0 | 100% | 54 | $0.021 | 19 |
| lessons | 0 | 97.7% | 67 | $0.040 | 55 |
| **package** | **0** | **100%** | 61 | $0.035 | 29 |
| both | 0 | 97.7% | 63 | $0.042 | 44 |
| function library | 0 | 100% (97.7 to 100) | 75 | $0.034 | 38 |

Nothing regressed anywhere. The canon arms cost more because they read more.

### 5.3 Growing: promote from one build, build the sibling (`envcheck` → `envmerge`, 110 judge cases)

| Arm | Judge | Lines written | Cost | Pulled |
|---|---|---|---|---|
| nothing | 110/110 ×3 | 248 | $0.041 | nothing |
| canon before promotion | 110/110 ×3 | 256 | $0.049 | the nearest wrong thing, once |
| **canon after, package** | **110/110 ×3** | **96** | **$0.037** | dotenv + schema, 3 of 3 |
| canon after, function library | 110/110 ×3 | 96 | $0.042 | dotenv + schema, 3 of 3 |

### 5.4 Fixing once

An independent judge found a defect in accepted code (`pointer_problems` dropped the version pin
from its message). It had reached every build that pulled the function. One fix in canon-lib took
the three package repos from 26/27 to 27/27 with zero changes to them. The copy-shape repo needed
one `code_add` to update.

### 5.5 The ceiling

Haiku without canon: 35/35, 27/27, 22/22, 57/57 and 110/110. A score cannot rise above 100%, so no
test here could show canon making code more accurate. What canon holds today is engineering
hygiene a current model already has.

## 6. Which method won

| Method | Correctness | Code written | Cost | Verdict |
|---|---|---|---|---|
| **canon-lib (package)** | best or tied, every round | least | lowest of the canon arms; below the control on publish | **ship** |
| Function library (`code_search` / `code_add`) | tied | same as package | 1.5 to 2× the package's turns, from argument errors and one function at a time | keep for discovery and for repos that cannot take the dependency |
| Lessons (gotchas as files) | worst, every round | no change | 2× | **stop, redesign** |
| Lessons + package | the package's gains minus the lessons' cost | | | no |

## 7. What to build now

### 7.1 canon-lib is the product

- **Source of truth stays the blocks** (`canon/blocks/<id>/`: code, tests, `BLOCK.md`). canon-lib
  is built from them. Today `promote.py` copies; make it a build step so the two cannot drift.
- **Rules, already proposed, now adopted:** append-only, a breaking change ships under a new name;
  heavy dependencies in extras; every symbol stands alone; a block's tests are the acceptance bar.
- **Install:** `uv add --editable <canon>/lib` today. A private index later, when there is a second
  machine; not before.
- **Discovery:** the package's `__init__` docstring lists every module and what it is for. That is
  what the winning builds read. Keep it one screen.

### 7.2 Promotion is the growth loop

1. A real repo has a module that stands alone (standard library only) and tests that pass a
   blind judge.
2. `python scripts/promote.py --repo ... --module ... --tests ... --id block-<name> --title "..."`
   makes the block and the canon-lib module, status `proposed`.
3. **Owner review flips it to `accepted`.** `code_search` and `code_add` serve accepted code only.
   The two dotenv blocks are accepted on the judge's word; review them first.
4. Rebuild the index. Repos see the new version as pending through `reconcile`.

### 7.3 Lessons: stop, then redesign

- The eleven gotchas cost 2× on every build and bought nothing. Six never applied to anything.
- Rewrite the five that applied as **decisions**: ten lines, a scope (`applies_to`, enforced), and
  the ticket they came from.
- **An agent that overrides a ticket because of a lesson must say so.** Add it to gotcha-agent-trust
  and to the system prompt.
- Serve by applicability only. Then re-test lessons alone, against a failing baseline.

### 7.4 Keep, fix, drop

- **Keep** `ds-next mcp`: the one door for every agent. Its tools now accept the argument names
  models actually send; keep them that way.
- **Fix** `reconcile` so it reports a stale block even when the manifest has another error.
- **Drop** anything Cortex-specific from the design, a package per function, and serving
  infrastructure. None of it changed a result.

## 8. What to test next

1. **A failing baseline.** Team-specific knowledge the model cannot infer (conventions, internal
   APIs, domain rules), with a judge given the team's standards. This is the only way to test
   "more accurate".
2. **A change that touches pulled code.** Does the package block, wrap or fork?
3. **Lessons alone, redesigned** (7.3), against that failing baseline.
4. **A real repo**: graph, LSP and reconcile against a living codebase were never exercised.

## 9. Open decisions for the owner

- Review the 13 blocks, 11 gotchas and 2 scaffolds. Nothing has owner review yet.
- Two rules the judges disagreed with: stage refuses to empty a folder it did not build; only the
  root README becomes the home page. Rule or ticket?
- Package or copy as the default. The evidence says package.

## 10. How to run it

```sh
# canon
cd ~/Developer/canon && python3 scripts/build_index.py
cd lib && uv run pytest -q                                   # 145 tests
python scripts/promote.py --repo <repo> --module src/<pkg>/<mod>.py --tests tests/test_<mod>.py --id block-<name> --title "..."

# ds-next
cd ~/Developer/ds-next && .venv/bin/python -m pytest -q      # 113 tests
ds-next mcp                                                  # the knowledge base, for any MCP client

# the honest test
bench/judge/write_judge.sh <task> [model]                    # blind judge
.venv/bin/python bench/judge/validate.py <workdir> <task>    # reference passes, planted bugs fail
bench/judge/run.sh <task> <without|lessons|lib|both|code> <n>
.venv/bin/python bench/judge/summarize.py <task>
bench/judge/change.sh <arm> <n>; .venv/bin/python bench/judge/summarize_change.py
```

Constraints that still hold: never push, commit locally; ask before installs that change the
machine; never print credentials; "Snowflake or local, nothing calls a third-party hosted model".
