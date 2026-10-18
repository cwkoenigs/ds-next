# Handoff: the team knowledge system (canon, ds-next)

State on 2026-10-17. Everything is local: nothing has been pushed. canon's work is on its `lessons`
branch (its `main` is untouched); ds-next has only `main`.

## 1. The idea

In the owner's words: *"my team's software could almost become plug and play. AI only gets more
accurate as the code base grew. People would almost always pull the same code. Imagine if we
started scaffolding methods, functions, calls."*

The working version of that:

- **canon** holds what the team knows. *Standards* say what must be true. *Gotchas* are mistakes
  already made once, with the rule that prevents them. *Accepted code* is reviewed, tested
  functions to reuse rather than rewrite. *Scaffolds* are accepted project shapes.
- **Agents working in a repo read the lessons that apply and pull the accepted code** instead of
  writing their own. When the team learns something, it goes back into canon through review.
- It is meant for any agent and any model (Claude, Cortex, others), through one MCP server.

**The design, by version** (when the owner asks "which version is this", this is the list):

| # | Version | What it added | Status |
|---|---|---|---|
| 1 | Standards | canon holds standards; ds-next scaffolds repos from canon and reconciles them against it (manifest, pre-push hook) | built |
| 2 | Lessons and blocks | gotchas, plus accepted code as whole modules copied into repos (`block_add`); tested by the rebuild series | built |
| 3 | Any agent | `ds-next mcp` serves canon to Claude, Cortex and others the same way; graph and LSP wired in | built, graph/LSP never exercised |
| 4 | Function library | accepted code searched and pulled one function at a time (`code_search`, `code_get`, `code_add`) | built, tested (4.4, 4.6) |
| 5 | Minimal proof of concept | canon is lessons plus `canon-lib`, one local package repos import; no serving layer | **current**, tested (4.3, 4.6) |

Versions 2 to 4 still exist in the code beside 5. What is proven and what is not is in section 5.

## 2. Where things are

| Repo | What | Branch |
|---|---|---|
| `~/Developer/canon` | standards (`*.md`, `adr/`), gotchas (`gotchas/`, 11), blocks (`blocks/`, 13), scaffolds (`scaffolds/`, 2), `canon-lib` (`lib/`), `index.json` (built by `scripts/build_index.py`) | `lessons` |
| `~/Developer/ds-next` | the CLI and terminal UI, the MCP server, the benches (`bench/`) | `main` |
| `~/Developer/skills-os`, `~/Developer/docs-ds` | procedures, and the Docusaurus renderer | unchanged here |

All gotchas, blocks and scaffolds are marked `proposed` or `accepted` by me. **None has had owner
review.**

## 3. What is built

**ds-next**, a small Claude-Code-style CLI over Cortex Code (`snowflake-cortex-agent-sdk` 0.0.2):
- **`/new`**: a scaffold picker and a one-screen form, reviewed by Cortex. The project is then
  created from the accepted scaffold by deterministic code.
- **Other commands:** `/canon`, `/blocks`, `/status`, `/docs`, `reconcile` (with a pre-push hook),
  `add <block>`.
- **`ds-next mcp`** serves the knowledge base to any MCP client, as tools:
  - **lessons:** `canon_list`, `canon_read`
  - **scaffolds:** `scaffold_get`
  - **blocks:** `block_list`, `block_get`, `block_add`
  - **code:** `code_search`, `code_get`, `code_add`
  - **repo:** `project_status`
- **Code intelligence wired in:** codebase-memory-mcp (a code graph, read-only), Serena (LSP),
  and `cortex search`.
- 113 tests pass.

**Accepted code exists in three shapes.** The first two came first; the third came out of design
discussion and is the current proposal.
1. **Blocks** (`canon/blocks/<id>/`): whole modules with tests. `block_add` copies one into a repo and
   records it in `.ds/manifest.toml`. Reconcile flags a newer version.
2. **Function-level library** (`index.json` "code", 54 symbols; ds-next `code.py`):
   - `code_search` finds functions by what they do.
   - `code_get` returns one function with only what it needs and its tests.
   - `code_add` copies just that into the repo with a provenance header, recorded in the manifest.
   - Every symbol stands alone: copied by itself, its tests pass and lint is clean
     (`bench/code_symbols_check.py`).
   - Pulls are logged to `~/.ds/usage.jsonl`.
3. **`canon-lib`** (`canon/lib/`): the same code as one local Python package. Repos run
   `uv add --editable <canon>/lib` and import from it (`from canon_lib.textsafe import json_literal`).
   - Proposed rules: append-only (a breaking change ships under a new name), and heavy
     dependencies in extras.
   - 145 tests pass.

## 4. Tests so far, and what they actually showed

They are listed in order, with my mistakes, because the mistakes are part of what was learned.

### 4.1 Rebuild series (rebuild the ds-next terminal from a spec, using canon)

- **Rebuilds 1 to 4, built by Cortex:** each rebuild picked up the previous one's lessons in its code
  most of the time (for example, gating `/new` on a review-verdict tool). Fixing one thing kept
  exposing the next problem.
- **Rebuilds 5 to 7, built by Claude:**
  - Rebuild 6 reached canon only through MCP, with canon's files blocked.
  - Rebuild 7 scored 25/25 on the final checks.
- **What this showed:** lessons written into canon get absorbed by the next build, by more than one
  model, and through more than one way of reaching canon.
- **What it did not show:** that canon makes code better. The checks were written by me to test
  canon's own lessons.
- **Mistakes:**
  - The product wrapped Cortex, so scoring needed a fake `cortex` (`bench/rebuild/fake_cortex.py`).
  - I spent hours fixing my own pseudo-terminal checks.
  - Cortex's request cap stopped runs.
  - The owner pointed out the test didn't need Cortex at all.

### 4.2 Small model-free tasks (`bench/tasks/`: stamp, mcheck, stage)

These are small command-line tools, built by Haiku 5.5, with checks I wrote.
- **Detailed specs:** canon helped by 1 check, because the specs spelled out the pitfalls, so the
  spec did canon's job.
- **Short "ticket" specs:** with canon 95%, without 76%, across 2 runs. **This is circular:** I wrote
  the checks from canon's lessons.
- **Function library vs whole blocks:** 94% vs 95%, and $0.040 vs $0.043 per build. On code this small
  there is nothing to save.

### 4.3 The honest test (`bench/judge/`)

**The judge:** for each ticket, a separate Claude run, which never saw canon, my checks or my
solutions and had no shell, wrote hidden acceptance tests: 57 tests, about 84 cases with
parameters. Nobody edited them.

**The builds:** Haiku from the same plain `uv init` repo, 3 runs each.

| | Judge tests passed | Imports `canon_lib` | Mean cost per build |
|---|---|---|---|
| Without canon | **252/252 (100%)** | 0/9 | $0.029 |
| With canon (lessons plus `canon-lib`, copied beside the repo) | 246/252 (98%) | **9/9** | $0.065 |

- **The runs were identical** across all three in every cell.
- **"With" lost points only where canon's own code or rules disagreed with the judge:**
  - stage refuses to empty an output folder it didn't create (canon's safety rule), and the judge
    expected it emptied. Every canon build said so in its final message ("stricter than the ticket
    asks, so say if you want it allowed"): a disclosed deviation, not a silent bug;
  - `canon_lib.pointers.pointer_problems` reported an unknown id without its pin (`[[ghost]]` for
    `[[ghost@1]]`), and the judge expected the pointer as written. A real defect in accepted code;
    fixed in block-markdown-pointers v2 (see 4.5). I first wrote this up as "a nested-folder case",
    which was wrong.
- **"The builds pull the same code":** where canon had the code, all three "with" builds imported
  the identical functions. But they wrote just as much of their own code, and that code was no more
  alike (19 to 34% similar either way), because canon covers only a slice of each task.

**Conclusions:**
- **"Canon makes agents produce better code" failed on these tasks.** The judge didn't probe what
  canon guards against, and Haiku handled everything the judge did probe.
- **The tasks were too simple.** Without canon, Haiku passed 100% of the judge's tests: a ceiling,
  so these tasks could not show whether canon helps. The next test needs tasks hard enough that the
  no-canon build fails a meaningful share of an independent judge's tests.
- **What survives:** agents reliably reuse the team's code when it exists.

### 4.4 The function library, by the same honest test

The `code` condition in `bench/judge/run.sh`: lessons through `canon_list` and `canon_read`, and
code through `code_search`, `code_get` and `code_add`, over MCP, with canon's files unreadable.
Haiku, 3 runs per task.

| | Judge tests passed | Pulled library code | Mean cost per build |
|---|---|---|---|
| Without canon | 252/252 (100%) | 0/9 | $0.029 |
| With canon, as a package | 246/252 (98%) | 9/9 | $0.065 |
| **With canon, function library** | **247/252 (98%)** | **9/9** | **$0.042** |

- **The same picture:** no gain on the judge's tests, and it lost the same points (stage's safety
  rule, the pointer pin), except the one build that pulled only `pointers` and wrote its own
  messages, which passed 27/27.
- **About a third cheaper than the package,** because the agent reads one function at a time.
- **Less convergence than the package:** the three builds of a task pulled *different* sets of
  functions (stamp: 7, 4 and 8 symbols). With the package, every build imported the identical set.
- **Not run yet:** the function library without the gotchas, which would isolate "pulling code"
  from "reading lessons".

### 4.5 Adversarial review of 4.3 and 4.4 (same day, after the fact)

Done by rerunning the three judges on the reference solutions with planted bugs, rereading every
build log, and re-examining both losses.

1. **The judges were half blind to canon.** 18 planted bugs, each a mistake canon's lessons name;
   the judges caught 11. The 7 missed: hooks under `core.hooksPath`, keyword package names,
   `{{placeholder}}` injection, swallowed git errors (stamp); datetime accepted as a date, an empty
   reason, tilde code fences (mcheck). So "no gain" was measured mostly on tests that did not probe
   what canon teaches. Where a judge did probe canon's ground (quoting metacharacters into TOML,
   YAML and Python; a non-empty target; a hook that actually runs), Haiku passed without canon.
2. **Both losses were misdiagnosed** (corrected above). One was a real defect in accepted code; the
   other was canon overriding the ticket, and saying so.
3. **The defect propagated exactly as the design predicts, both ways.** All 3 package builds, and
   the 2 library builds that pulled `pointer_problems`, inherited it; the library build that pulled
   only `pointers` wrote its own message and passed. One fix in canon-lib took the three package
   builds from 26/27 to 27/27 with zero changes in any repo. The copy-shape repo needed `code_add`
   again, which updated it to v2 and passed. `reconcile` should have flagged the stale copy but
   stops at the first manifest error, and the bench manifest had no tags.
4. **My reference was not independent of canon.** It had the identical pin defect: I wrote both from
   the same head. A reference validates a judge; it cannot stand in for one.
5. **The library arm pulled code in 9/9 builds.** The scorer counted only `canon_lib` imports, so
   it printed none. `score.py` now counts copied modules by their provenance header, and the lines
   the build wrote itself.
6. **Own code did not shrink.** Lines the build wrote itself (median; without / package / library):
   stamp 89 / 99 / 88; mcheck 174 / 130 / 131; stage 146 / 138 / 146. canon covers a slice of each
   task, and the rest is written fresh each time (9 to 34% similar across runs, in every arm).
7. **The library arm's tool errors were ours.** 10 of 17 errors in one build were argument names:
   `tags` sent to canon_read, `query`/`name` to code_get, `id`/`name` to code_add, and canon_list
   rejecting an empty call. Haiku also sent JSON lists where code_add wanted a comma-separated
   string (fixed: `parse_ids`). These inflate that arm's turns and cost.
8. **Cost was a mean over three with outliers** ($0.129 and $0.153 single runs). Medians
   (without / package / library): stamp 0.019 / 0.044 / 0.039; mcheck 0.027 / 0.044 / 0.042; stage
   0.031 / 0.052 / 0.048. Still 1.4 to 2.3× the control.
9. **The tasks were tailored to canon, and it still did not help.** The gotchas came from the
   ds-next build and the tasks were cut from the same build. 5 of 11 gotchas applied; the other 6
   (Cortex SDK, terminal UI, approvals, agent trust, verify-process, green-means-ran) were noise the
   lessons arm read past. What canon holds is engineering hygiene a strong model already knows;
   the only team-specific content is the manifest format, the `[[id]]` convention and two scaffolds.
10. **Three identical scores per arm** means the judge could not separate the arms. It is not
    evidence of stability.

What this leaves standing: reuse (agents pull accepted code when it exists) and fix-once propagation
(package shape). What it leaves open: whether canon changes correctness at all, which needs the
redesign in 4.6.

### 4.6 Round 2: a harder task, five arms, a validated judge

**Why:** 4.5 showed round 1 could not have found a gain: the control was at the ceiling, the judges
did not probe canon's lessons, and the arms mixed lessons with code.

**The task, `publish`** (`bench/tasks/publish/ticket.md`, 289 words): check a repo's standards
manifest against the index (as mcheck), stage its Markdown with rewritten links and copied assets
(as stage), turn `[[id]]` pointers into links, write `publish.json`, and write nothing if anything
is an ERROR. Three subsystems and an ordering rule in one ticket. Builds wrote 280 to 510 lines,
against 90 to 175 in round 1.

**The judge** (Opus, told to be adversarial and to write 30 to 45 tests): 34 tests, 57 cases.
Validated before any build was scored (`bench/judge/validate.py`, log in
`bench/judge/publish/validation.log`): a reference passes 57/57, and the judge catches 9 of 12
planted bugs (missed: datetime accepted as a date, link titles, reference-style links; it did not
test those forms). The reference first failed two tests because I had read "README.md becomes
index.md" as the root README only; the ticket qualifies only `index.md` as top-level, so the judge's
reading stands and the reference was changed to match the ticket.

**Arms** (Haiku 5.5, 3 builds each, the same `uv init --package` start, ~/Developer unreadable):
`without`; `lessons` (gotchas and standards as files, no code); `lib` (canon-lib only, no lessons);
`both`; `code` (the function library over MCP, lessons through canon_read).

| Arm | Judge pass, median (range) | Pulled canon code | Lines the build wrote, median | Cost, median (range) | Turns, median |
|---|---|---|---|---|---|
| without | 100% (96.5 to 100) | 0/3 | 426 | $0.207 (0.061 to 0.270) | 29 |
| lessons | 96.5% (96.5 to 96.5) | 0/3 | 446 | $0.494 (0.436 to 0.606) | 74 |
| lib | **100% (100 to 100)** | 3/3 | **277** | **$0.101 (0.060 to 0.241)** | 37 |
| both | 96.5% (96.5 to 96.5) | 3/3 | 317 | $0.304 (0.194 to 0.585) | 65 |
| code | 100% (96.5 to 100) | 3/3 | 280 | $0.200 (0.160 to 0.219) | 64 |

`bench/judge/summarize.py publish` prints this; `bench/judge/reads.py publish` prints what each
build read.

**What happened:**
- **Correctness: still at the ceiling.** The control passed 57/57 twice. The only tests any arm
  failed in any run were the two README tests. The ticket is ambiguous about nested READMEs; the
  judge read it literally (every README becomes its folder's index) and some builds read it as
  root-only: control 1 of 3, code 1 of 3, lessons 3 of 3, both 3 of 3.
- **Lessons made that failure certain.** `gotcha-docs-staging` says only the root README becomes
  the home page (a decision from the docs-ds build). Every build that read it followed it over the
  ticket, and none flagged the deviation; one reported "README.md → index.md: done". The lesson made
  the builds consistent, in the direction the judge rejected. Which reading is right is the team's
  call, not the judge's; but the agent should have said it was overriding the ticket.
- **Lessons cost the most and bought nothing here.** The lessons arm read 15 to 20 of the 29
  documents per build (including the Cortex SDK, terminal UI and approvals gotchas, none relevant),
  took 2.5× the turns and 2.4× the cost of the control, and wrote as much code.
- **The package alone was the best arm.** 100% in every run, 35% fewer lines written, median cost
  half the control (two runs at $0.06 and $0.10, one at $0.24). Round 1 on toy tasks showed the
  opposite (the package cost 2×); on a task big enough to have a slice worth pulling, the trade
  flips.
- **The function library matched the package on code and correctness but cost the same as the
  control**, in 64 turns: 8 to 11 `code_get` calls per build and 7 to 11 tool errors per build, most
  of them argument names (4.5, item 7; fixed after the run: the tools now take the names models
  send, and `canon_list` works without tags).
- **Convergence on what is pulled is real:** 9 of 9 builds with code access pulled confined, outdir
  and pointers (Jaccard 0.83; textsafe sometimes). Convergence of the code they wrote themselves is
  not: 7 to 12% similar across runs in every arm, canon or not.
- **Cost varies a lot run to run** (the control ranged $0.06 to $0.27), so with n=3 the cost
  ranking is a direction, not a measurement.

### 4.7 Round 3a: the maintenance test (is a canon-built repo easier to change?)

**Why:** "plug and play" should pay most on change, and a shared package might also hurt there
(behaviour that lives in the package cannot be changed in the repo).

**The change** (`bench/tasks/publish-change/ticket.md`): pages under `drafts/` publish with bad
pointers as `WARN` instead of `ERROR` (never blocking, never changing the exit code); a `--base-url`
prefix for pointer links, trailing slash dropped; `publish.json` gains `base_url` and `warnings`.
Applied by Haiku to each of the 15 round-2 repos, with the same knowledge access its arm had
(`bench/judge/change.sh`). Judged twice: the original 57 cases (regressions) and a new blind judge
for the change (Opus; 31 tests, 44 cases; its reference passes 44/44 and the old 57 with no
regressions; 5 of 5 planted bugs caught).

| Arm | Regressions | Change judge, median (range) | src lines changed, median | test lines changed, median | Cost, median | Turns, median |
|---|---|---|---|---|---|---|
| without | 0 | 100% (97.7 to 100) | 54 | 142 | $0.021 | 19 |
| lessons | 0 | 97.7% (97.7 to 97.7) | 67 | 118 | $0.040 | 55 |
| lib | **0** | **100% (100 to 100)** | 61 | 103 | $0.035 | 29 |
| both | 0 | 97.7% (97.7 to 97.7) | 63 | 116 | $0.042 | 44 |
| code | 0 | 100% (97.7 to 100) | 75 | 120 | $0.034 | 38 |

`bench/judge/summarize_change.py` prints this.

**What happened:**
- **No regressions anywhere:** no test a repo passed before the change failed after it, in any of
  the 15 repos.
- **Every build implemented the change correctly.** The only change-judge failure, in 7 of 15
  builds, is the README rule carried forward: a `drafts/README.md` stays `README.md` instead of
  becoming `index.md`, so one WARN test fails. It is the pre-existing reading, not a maintenance
  failure: the lessons arms fail it 3/3 (they follow the gotcha), the control 1/3, the library 1/3,
  the package 0/3.
- **A canon-built repo was neither easier nor harder to change.** Diff sizes are alike (54 to 75
  source lines). Cost was 1.6 to 2× the control, almost all of it reading: the lessons arm spent 55
  turns against 19.
- **The package's rigidity was not tested.** The change did not need to alter pulled behaviour
  (pointer parsing, out-dir safety), so the case where a package would have to be changed, or
  wrapped, is still open (6.3).

### 4.8 Round 3b: the growth test (does the library pay off as it grows?)

**The claim under test:** "AI only gets more accurate as the code base grew. People would almost
always pull the same code." Directly: promote code from one real build into canon, then build a
sibling task and see whether it is pulled, and what that does to the code written, the cost and
the judge's score.

**A domain canon did not cover:** dotenv files. Two tickets share the parsing, the TOML schema and
the type rules. `envcheck` (`bench/tasks/envcheck/ticket.md`) checks dotenv files against a schema;
`envmerge` (`bench/tasks/envmerge/ticket.md`) merges them for a deployment and writes the result
atomically. Both judges (Opus, adversarial) were validated: envcheck 96 cases, reference 96/96,
9 of 9 planted bugs caught; envmerge 110 cases, reference 110/110, 7 of 7 caught.

**Seed:** `envcheck`, three builds without canon, all 96/96. Seed 3 had a stand-alone `dotenv.py`
and `schema.py` with their own tests. `canon/scripts/promote.py` turned each into a block and a
canon-lib module (`block-dotenv`, `block-env-schema`; 13 blocks, 69 symbols, every one stands
alone). The blocks were marked accepted on the judge's word, because `code_search` serves only
accepted code; the owner has not reviewed them.

**Then `envmerge`, Haiku, 3 builds per arm:**

| Arm | Judge pass | Pulled | Lines the build wrote, median (range) | Cost, median (range) | Turns |
|---|---|---|---|---|---|
| without canon | 110/110 ×3 | nothing | 248 (231 to 270) | $0.041 (0.031 to 0.044) | 25 |
| canon before promotion (package) | 110/110 ×3 | textsafe 3/3, confined 1/3 | 256 (229 to 263) | $0.049 (0.048 to 0.071) | 37 |
| **canon after promotion (package)** | 110/110 ×3 | **dotenv + schema 3/3** | **96 (80 to 110)** | **$0.037 (0.035 to 0.038)** | 28 |
| **canon after promotion (function library)** | 110/110 ×3 | **dotenv + schema 3/3** | **96 (87 to 101)** | $0.042 (0.040 to 0.043) | 50 |

**What happened:**
- **Growth works mechanically, end to end:** code from one real build was promoted and every
  sibling build pulled it, through both shapes. The code written fell by 61% and cost did not rise.
- **Before promotion, canon in hand but nothing relevant in it cost more, not less:** the builds
  read what was there and used the nearest thing. One quoted dotenv values with
  `textsafe.json_literal` (JSON escapes are not dotenv escapes; it patched `$` by hand) and still
  passed the judge. A post-promotion build read the same function and rejected it as unsuitable.
- **Correctness is at the ceiling in every arm, again** (110/110 everywhere). Growth changed how
  much was written and what it was made of, not the judge's score. On tasks like these, with this
  model, "more accurate" cannot be measured; "less code, pulled from one place" can.
- **The function library pulled finer-grained:** `read_env`, `load_schema`, `check_value`,
  `SchemaError` by name (plus `check_one_line` for file names in the header), in about 50 turns;
  the package arm imported the modules in 28.

## 5. Where it stands (after rounds 2 and 3)

**Shown, with independent judges, on four tasks:**
- Agents pull the team's accepted code when it exists, and pull the same pieces (publish: 9/9 on
  confined, outdir, pointers; envmerge: 6/6 on dotenv, schema).
- Pulling it cuts what they write: by a third on publish, by 61% on envmerge once canon held the
  domain's code. Cost did not rise; as a package it fell.
- Growth works end to end: code promoted from one real build was pulled by every sibling build,
  through both shapes (4.8).
- A fix in the package reaches every repo with no change to the repo; a fix in a copy reaches a repo
  on the next `code_add` (4.5).
- A canon-built repo changes as safely as any other: zero regressions in 15 change builds (4.7).

**Not shown:**
- That canon makes builds more correct. On five tasks, with four validated judges, the control
  passed 96 to 100%. Haiku is at the ceiling on tasks of this kind, so "more accurate" cannot be
  measured here.
- That a repo built on canon is cheaper to change: it cost 1.6 to 2× more, all of it reading.
- Anything about a large or old codebase: every repo was hours old and a few hundred lines; graph,
  LSP and reconcile against a living repo were never exercised.

**Shown against the idea, as built today:**
- Lessons are expensive to carry (15 to 20 documents read per build; 2.4× cost on a build, 2× on
  a change) and have not bought a single judge point in any round. One lesson encodes a project
  decision (root README only) that the agent follows over an ambiguous ticket without saying so,
  and it followed through into the change.
- Canon in hand with nothing relevant in it costs more, not less: the builds read what is there and
  use the nearest thing, sometimes wrongly (4.8).
- Accepted code carries its defects to every consumer, and a model that trusts it does not test
  around it (4.5).

**Where this leaves the owner's idea.** "People would almost always pull the same code", "fix it
once" and "it pays off as the library grows" now have evidence: reuse, convergence on what is
pulled, 35 to 61% less code written, fix-once propagation, promotion from real builds. "AI only
gets more accurate" has none: correctness was at the ceiling without canon on every task tried.
On this evidence canon buys less code written from scratch, one place to fix it, and a shared
vocabulary across repos, not a higher score.

## 6. Open questions and the next tests

1. **Where could correctness show?** Either team-specific knowledge the model cannot infer
   (conventions, internal APIs, domain rules), judged by a judge who is given the team's standards;
   or domains where Haiku fails on its own (none of the file-and-CLI tasks did that). Canon has
   little team-specific content today: the manifest format, the `[[id]]` convention, two scaffolds.
2. **Lessons need a different shape.** The lessons arm is the weak part in every round. Few,
   specific, scoped as decisions; when a lesson contradicts the ticket the agent must say so (a rule
   for gotcha-agent-trust); retrieval by applicability, so a docs tool never reads the Cortex SDK
   gotcha. The `applies_to` field exists and nothing uses it in the file arms.
3. **A change that touches pulled code.** The maintenance test never had to change behaviour that
   lived in canon. Run a change ticket that does (a different pointer syntax, say), to see whether
   the package shape blocks, wraps or forks.
4. **Promotion as a process.** 4.8 promoted by hand with `promote.py`, accepted on the judge's word.
   Open: what the owner's review gate looks like, how a promoted block is versioned when its source
   repo changes, and how near-duplicates across repos are found (the graph's job).
5. **Package or copy:** both pulled the same code and scored the same; the package is cheaper on
   builds (28 vs 50 turns on envmerge) and propagates fixes; the copy needs no shared install.
   Rounds 2 and 3 favour the package.
6. **Owner review** of every gotcha, block and scaffold: 13 blocks now, two of them accepted on a
   judge's word only.
7. **The judge vs canon's rules:** out-dir clearing and the root-README rule. Is the rule right, or
   the ticket?

**The owner's guidance so far:**
- Don't over-design.
- Design before testing.
- The design doesn't depend on Cortex.
- A proof of concept doesn't need serving infrastructure: a local package is fine.
- Test honestly, with an independent judge; small tests are not a real codebase.

## 7. How to run things

```sh
# canon
cd ~/Developer/canon && python3 scripts/build_index.py          # standards, blocks, scaffolds, code index
~/Developer/ds-next/.venv/bin/python scripts/test_blocks.py      # every block's tests, in a repo layout
cd lib && uv run pytest -q                                       # canon-lib

# ds-next
cd ~/Developer/ds-next && .venv/bin/python -m pytest -q
DS_CANON=~/Developer/canon .venv/bin/python bench/code_symbols_check.py   # every symbol stands alone

# the honest test (blind judge). Builder default: Haiku; judge default: Opus
bench/judge/write_judge.sh <task> [model] ["30 to 45"]       # writes bench/judge/<task>/test_judge.py
.venv/bin/python bench/judge/validate.py <workdir> <task>    # reference must pass; mutants must fail
bench/judge/run.sh <task> <without|lessons|lib|both|code> <n> # bench/judge/runs/<task>-<arm>-<n>/result.json
.venv/bin/python bench/judge/summarize.py <task> [arm ...]   # per-arm table (median, range, similarity)
.venv/bin/python bench/judge/reads.py <task>                 # what each build read and pulled

# the maintenance test (round-2 repos must still be on disk; snapshots in runs/publish-<arm>-<n>/before)
bench/judge/change.sh <arm> <n>                              # runs/publish-change-<arm>-<n>/result.json
.venv/bin/python bench/judge/summarize_change.py

# the growth test: RUN_LABEL names the run, DS_CANON picks the canon (a frozen copy for "before")
DS_CANON=<frozen canon> RUN_LABEL=lib-pre bench/judge/run.sh envmerge lib 1
RUN_LABEL=lib-post bench/judge/run.sh envmerge lib 1
cd ~/Developer/canon && python scripts/promote.py --repo <repo> --module src/<pkg>/<mod>.py --tests tests/test_<mod>.py --id block-<name> --title "..."
```

A new task needs `bench/tasks/<task>/ticket.md`, a reference in `bench/tasks/ref/<task>.py` and
planted bugs in `bench/tasks/mutants.py`; the reference exists only to validate the judge.

**Builder isolation:** a headless `claude -p` run.
- `~/Developer` is blocked for Read, Grep, Glob, Edit and Write.
- Bash is limited to `uv` and `git`.
- There are no MCP servers except `ds` when the condition calls for it.

## 8. Constraints

- **Never push.** Commit locally only.
- **Installs:**
  - Ask before installs that change the machine.
  - Don't run third-party installers that reconfigure agents.
- **Credentials:** never print them.
- **Products:** the Anthropic Agent SDK terms forbid offering claude.ai login in a product.
- **canon rule:** "Snowflake or local; nothing calls a third-party hosted model."
- **Cortex:**
  - This account has a request cap, and `cortex exec` (print mode) is blocked on it; stream-json
    works.
  - Long Cortex runs need `caffeinate -ims`.
