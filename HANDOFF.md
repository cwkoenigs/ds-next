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

The idea is **not proven yet** (section 4).

## 2. Where things are

| Repo | What | Branch |
|---|---|---|
| `~/Developer/canon` | standards (`*.md`, `adr/`), gotchas (`gotchas/`, 11), blocks (`blocks/`, 11), scaffolds (`scaffolds/`, 2), `canon-lib` (`lib/`), `index.json` (built by `scripts/build_index.py`) | `lessons` |
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
- 112 tests pass.

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
   - 65 tests pass.

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
    expected it emptied;
  - `canon_lib.pointers` misses one nested-folder case.
- **"The builds pull the same code":** where canon had the code, all three "with" builds imported
  the identical functions. But they wrote just as much of their own code, and that code was no more
  alike (19 to 34% similar either way), because canon covers only a slice of each task.

**Conclusions:**
- **"Canon makes agents produce better code" failed on these tasks.** The judge didn't probe what
  canon guards against, and Haiku handled everything the judge did probe.
- **What survives:** agents reliably reuse the team's code when it exists.

### 4.4 In progress when this was written

The same honest test, for the **function library over MCP**: the `code` condition in
`bench/judge/run.sh`.
- It includes the gotchas and standards through `canon_list` and `canon_read`, and code through
  `code_search`, `code_get` and `code_add`. canon's files are unreadable.
- 9 builds were running. Results land in `bench/judge/runs/<task>-code-<n>/result.json`.
- The owner raised the option of testing the function library *without* the gotchas, to isolate
  "pulling code" from "reading lessons". That isn't run yet.

## 5. Where it stands

- **Proven:**
  - Agents absorb written lessons and reuse accepted code when it exists, across models (Cortex,
    Claude, Haiku) and access paths (CLI, MCP, files).
  - Scaffolds and blocks work mechanically.
- **Not proven:**
  - That canon makes code more correct, judged independently.
  - That builds converge as the library grows (plug and play).
- **The cost:** canon roughly doubles build cost on small tasks, from reading lessons and code.
- **Every test so far used toy tasks.** Small tests can't show anything about a real codebase, and
  choices made on small cases, like the Python-only code parser, may not hold up.

## 6. Open questions and decisions

1. **What exactly should be proven first?** Correctness, judged independently, has failed on easy
   tasks. Candidates:
   - harder tasks where an independent judge would catch real failures;
   - convergence as library coverage grows (run at 0%, half and full coverage, then measure each
     repo's own code size and similarity across builds);
   - a claim about consistency and maintenance across repos.
2. **How code is shared:** one canon package per language (`canon-lib`, the current proposal), or
   copying with provenance (`code_add`). A package per function was rejected.
3. **How the library grows:** proposed by promotion from real repos, with graph finding
   near-duplicate functions across repos, then owner review. Not built.
4. **Where graph and LSP fit:** navigating the repo being changed. They were never exercised,
   because every build started from an empty repo.
5. **Owner review** of every gotcha, block and scaffold, before anyone relies on them.
6. **The judge vs canon's safety rule:** the judge expects stage to empty any output folder, and
   canon forbids it. Is the rule right, or is the ticket?

**The owner's guidance so far:**
- Don't over-design.
- Design before testing.
- The design doesn't depend on Cortex.
- A proof of concept doesn't need serving infrastructure: a local package is fine.

## 7. How to run things

```sh
# canon
cd ~/Developer/canon && python3 scripts/build_index.py          # standards, blocks, scaffolds, code index
~/Developer/ds-next/.venv/bin/python scripts/test_blocks.py      # every block's tests, in a repo layout
cd lib && uv run pytest -q                                       # canon-lib

# ds-next
cd ~/Developer/ds-next && .venv/bin/python -m pytest -q
DS_CANON=~/Developer/canon .venv/bin/python bench/code_symbols_check.py   # every symbol stands alone

# the honest test (blind judge). Builder default: Haiku
bench/judge/write_judge.sh <task>                 # writes bench/judge/<task>/test_judge.py
bench/judge/run.sh <task> <without|with|code> <n> # result in bench/judge/runs/<task>-<cond>-<n>/result.json
```

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
