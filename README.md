# ds-next

<!-- ds:local interview 2026-10-16 -->
`ds`, rebuilt small. A terminal that looks and behaves like Claude Code, drives Claude Code or
Cortex Code through their agent SDKs (Cortex's `snowflake-cortex-agent-sdk` is a fork of Claude's
`claude-agent-sdk`) or Codex through its app-server (`codex.py`), with `sdk.py` picking one per
machine, and scaffolds projects from the team's knowledge base. About 1,350 lines of Python in seven modules.

Owner: ckoenigs

## The system it completes

Four repositories, one loop. Knowledge is written once, read everywhere, and new knowledge
flows back to where it is written.

```
            ┌──────────── canon ────────────┐   what is true: versioned standards, index.json
            │                               │
     reads  │                               │  merge request (so-capture)
            ▼                               │
  ┌─────────────────────┐   capture   ┌─────┴──────────────┐
  │ ds-next             │ ──────────▶ │ .ds/captures/*.md  │  drafts in canon format
  │  terminal + Cortex  │             └────────────────────┘
  │  scaffold, reconcile│ ◀──── skills-os: how we work (SKILL.md procedures, /so-* commands)
  └─────────┬───────────┘
   writes   │  README, AGENTS.md ([[pointers]], never text), DECISIONS.md, .ds/manifest.toml, hook
            ▼
       a new repo ──── pre-push: reconcile ── pending standards are a nudge, never a block
            │
            └──── /docs ──▶ docs-ds renders the repo with every [[pointer]] linked to its standard
```

| Part | Role here | Found at |
|---|---|---|
| canon | the only place a standard's text exists; ds-next reads `index.json` and the files | `$DS_CANON`, else `~/Developer/canon` |
| skills-os | procedures the agent follows (`skill_read`), offered as `/so-*` slash commands, and named in every new repo's AGENTS.md | `$DS_SKILLS`, else `~/Developer/skills-os` |
| docs-ds | the Docusaurus shell `/docs` builds with; never modified | `$DS_DOCS_SHELL`, else `~/Developer/docs-ds` |
| Claude Code, Cortex Code or Codex | the model and its tools, driven through its SDK (Codex: its app-server) with the knowledge base as in-process tools | `claude`, `cortex` or `codex` on `PATH`; `ds-next setup --agent claude` (or `cortex`, or `codex`) decides which the terminal uses, `DS_AGENT` overrides for one run |

## Run

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -e ".[test]"
.venv/bin/ds-next              # the terminal
.venv/bin/pytest -q            # 21 deterministic tests
DS_LIVE=1 .venv/bin/pytest -q -m live    # one end-to-end run through Cortex Code
```

## The terminal

```
› /new                                  (or /new python, or /new python cli order-metrics)

 New project from the canon. Which scaffold?
 ❯ 1. python › cli          Python command-line tool · v1
   2. python › package      Python library package · v1

⏺ Scaffold python-cli v1 · Python command-line tool
 Python command-line tool · fill in, check, Enter
 ❯ name        * order-metrics
   purpose     * Pull daily order metrics from Snowflake for the finance team
   snowflake     ANALYTICS.ORDERS
   owner         cwkoenigs                 ← suggestions already filled in
   test          uv run pytest -q
   16 standards apply · tags python, package, cli, snowflake      ← live as you type
   Tab/↓ next · ↑ back · Enter submit · Esc cancel

⏺ Looking at the draft against the canon.
⏺ scaffold_get(python-cli)                 ← the accepted scaffold, fetched from the canon
⏺ scaffold_project(order-metrics)
  ⎿  created …/order-metrics from python-cli v1
  3 turns · 15.2s
```

`/new` is local and instant: a picker of the canon's accepted scaffolds (Tab-completes as
`/new python cli`), then one form with every field on screen and suggestions filled in. On
Enter the model reviews the draft against the canon. If something is wrong or too vague it
says so once; Enter keeps your answers, or type a correction. Then it fetches the accepted
scaffold with `scaffold_get` and creates the repo. `scaffold_project` refuses a version the
model did not fetch, so the code always comes from the canon as it is today. Submitting the
form approves exactly what you submitted; if the model changes a value, you approve the change.

| Input | Does | Model? |
|---|---|---|
| `/new [path…] [name]` | picker and form, then review, fetch and create | yes, once |
| `/canon [id\|tags]` | list standards, or read one | no |
| `/skills [name]` | list skills-os procedures, or read one | no |
| `/so-<skill> [context]` | the agent reads that skill and follows it | yes |
| `/status` | reconcile the current repo | no |
| `/docs` | build with docs-ds and serve on a local port | no |
| `/captures` | drafts waiting to become canon merge requests | no |
| `/effort [level]` | thinking effort, `low` by default for speed; resumes the same session | no |
| `/model`, `/clear`, `/help`, `/exit` | session control | no |
| anything else | a turn with the agent (Claude Code, Cortex Code or Codex) | yes |

While the model works, the status line shows the step and the seconds elapsed. Ctrl-C
interrupts a turn and keeps the session. Enter on an empty line answers the model's last
question with "keep my answers"; with no question pending it prints a hint. Ctrl-D leaves.

The agent's tools, served in-process: `canon_list`, `canon_read`, `skills_list`, `skill_read`,
`project_status`, `scaffold_list` and `scaffold_get` are approved automatically because they
only read. `scaffold_project` and `capture` write, as do Cortex's own Bash and file edits, so
they ask unless the form already approved them. An approval shows the whole request, asks one
question at a time even when Cortex makes parallel calls, and takes only an explicit `y`, `a` or
`n`: Enter alone asks again. No settings file skips the question: an allow rule in your Claude
settings still asks, and before a Cortex session starts in a repo whose own settings define hooks,
ds-next shows each hook's command and asks.

## Code intelligence

When installed, ds-next also gives the agent these. Each is optional, and none is installed by ds-next.

| Server | Tool | Auto-approved | Asks |
|---|---|---|---|
| `code` | [ds-code](https://github.com/cwkoenigs/ds-code) (`ds-code mcp`): TypeScript's and Pyright's language servers | all eight: `find_symbol`, `references`, `callers`, `callees`, `file_symbols`, `definition`, `repo_overview`, `change_impact` | nothing (every tool reads) |
| `ds.snowflake_search` | `cortex search` | docs, catalog objects, table details | nothing |

Install ds-code once: clone it, then `npm install` and `npm link` in it (its README has the steps).
ds-next finds `ds-code` on the PATH and starts it for the repo it runs in; nothing needs indexing or
refreshing. It replaced codebase-memory-mcp and Serena (local-003).

## Without the model

The same code, for scripts, hooks and CI:

```bash
ds-next new NAME --answers answers.toml [--dir PARENT]   # tests/fixtures/answers.toml is an example
ds-next reconcile [PATH] [--quiet]                       # exit 1 only on a broken pointer or bad manifest
ds-next adopt [PATH] [--purpose ..] [--tags a,b] [--adopt-all]   # an existing repo joins: manifest, AGENTS.md, hook
ds-next canon list [--tags python,cli] | canon read ID
ds-next skills
ds-next docs [--out DIR]
ds-next ask "PROMPT" [--yes]                             # one turn, printed like the terminal
```

## What a scaffolded repo gets

The code is an accepted scaffold from the canon's `scaffolds/` directory, recorded in the
manifest by id and version. Today the canon has `python-cli` (the ds-cli shape: typer, a
console script) and `python-package`, both Python 3.12 with uv, a src layout, a passing test,
ruff and a GitLab CI file. A new scaffold is a canon merge request, not a ds-next release. Its docs are README.md, an AGENTS.md under
40 lines with standards as `[[id]]` pointers, DECISIONS.md, `.ds/manifest.toml` with every
applicable standard adopted or declined with a reason and a 90-day revisit, `.ds/interview.md`,
and a pre-push hook. A CLI is also tagged `package`, so it inherits package standards.

## Findings from building against Cortex Code 1.2.14

- The SDK is `snowflake-cortex-agent-sdk` 0.0.2, Public Preview since 2026-10-13. Its
  `cortex_agent_sdk.cortexcode` module has the same API as the older `cortex-code-agent-sdk`
  (last release 1.0.7, 2026-07-31), which it supersedes.
- Neither SDK supports `mcp` 2: both build in-process tool servers with the 1.x decorator API that
  `mcp` 2 removed. The new SDK declares `mcp<2` itself. The old one declares `mcp>=1.0` unbounded,
  so a fresh install of it picks up `mcp` 2 and `create_sdk_mcp_server` raises `AttributeError`.
- `allowed_tools` is exclusive in Cortex: every tool not listed is blocked before `can_use_tool` is
  asked, Bash included. ds-next sets no allowlist and approves read-only tools in its callback.
- Both agents run a repo's own hooks from its settings, with nothing asked (checked live): Claude
  Code from `.claude/settings.json`, Cortex Code from `.cortex/` and `.claude/settings.json`. Claude's
  are switched off (`disableAllHooks` through `settings`); Cortex has no switch, so ds-next asks
  first (local-001).
- Codex runs through `codex app-server`, the JSON-RPC its editor extensions use: unlike `codex exec`, it
  asks before a command runs or a file changes, and it calls tools the client serves. Every tool
  reaches it as a dynamic tool from ds-next, the code tools included, so each call goes through
  ds-next's approval as with the other agents. A no declines, as a denial does with Claude Code; the
  turn goes on and the model asks what to do instead. The app-server is marked experimental:
  `tests/test_codex.py` drives the real binary when one is installed, so rerun it after upgrading
  Codex (local-004).
- An allow rule in the person's own Claude settings skips `can_use_tool` (checked offline against
  the real CLI). A `PreToolUse` callback that answers "ask" sends the call back to it; settings-file
  hooks being off does not stop it (local-001).
- Cortex drops the error flag of in-process tool results, whether it is sent as `is_error` or
  `isError` (checked live). ds-next therefore starts every error result with `ERROR:`, which the
  model reads and the terminal colours red.
- `can_use_tool` receives a kind (`"MCP"`, `"Bash"`) and `{"action", "resource"}`. For MCP tools,
  the first line of `resource` is the tool's full name and the rest is its input.

## Not here yet

A nudge when a repo's scaffold has a newer version in the canon, `reconcile --interactive` (adopt or decline a pending standard from the terminal; today the agent
can do it by editing the manifest, with approval), publishing captures as canon merge requests
(the so-capture skill's job), streaming partial text, and a published package so the CI
reconcile job can install it.
