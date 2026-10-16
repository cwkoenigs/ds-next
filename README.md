# ds-next

<!-- ds:local interview 2026-10-16 -->
`ds`, rebuilt small. A terminal that looks and behaves like Claude Code, drives Cortex Code
through Snowflake's Python SDK (`snowflake-cortex-agent-sdk`, its `cortexcode` module), and scaffolds projects from the team's
knowledge base. About 1,350 lines of Python in seven modules.

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
| Cortex Code | the model and its tools, driven through the SDK with the knowledge base as in-process MCP tools | `cortex` on `PATH` |

## Run

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -e ".[test]"
.venv/bin/ds-next              # the terminal
.venv/bin/pytest -q            # 21 deterministic tests
DS_LIVE=1 .venv/bin/pytest -q -m live    # one end-to-end run through Cortex Code
```

## The terminal

```
╭──────────────────────────────────────────────────────────────╮
│  ✻ Welcome to ds-next v0.1.0                                 │
│    /new to start a project · /help for commands · ctrl-c …   │
│    canon:  18 standards at ~/Developer/canon                 │
│    skills: 11 from skills-os · docs-ds found                 │
╰──────────────────────────────────────────────────────────────╯
› /new orders-cli
⏺ Starting the interview for orders-cli. 1 Purpose …  2 Kind — cli or package? [cli]
› pull daily order metrics from Snowflake; cli; ANALYTICS.ORDERS; lands a day late
⏺ canon_list(python,package,cli,snowflake)
  ⎿  adr-000 v1 [*] Repo knowledge system … +15 lines
⏺ Here's the summary before I create: … Good to create?
› yes
⏺ scaffold_project(orders-cli)
╭─ scaffold_project ─────────────╮
│ { "name": "orders-cli", … }    │
╰────────────────────────────────╯
  Allow? yes · always this session · no › y
  ⎿  created …/orders-cli … +13 lines
  2 turns · 10.0s
```

| Input | Does | Model? |
|---|---|---|
| `/new [name]` | the interview, then `scaffold_project` after you approve it | yes |
| `/canon [id\|tags]` | list standards, or read one | no |
| `/skills [name]` | list skills-os procedures, or read one | no |
| `/so-<skill> [context]` | the agent reads that skill and follows it | yes |
| `/status` | reconcile the current repo | no |
| `/docs` | build with docs-ds and serve on a local port | no |
| `/captures` | drafts waiting to become canon merge requests | no |
| `/model`, `/clear`, `/help`, `/exit` | session control | no |
| anything else | a turn with Cortex Code | yes |

Ctrl-C interrupts a turn and keeps the session. Ctrl-D leaves.

The agent's tools, served in-process: `canon_list`, `canon_read`, `skills_list`, `skill_read`,
and `project_status` are approved automatically because they only read. `scaffold_project` and
`capture` write, so they ask, as do Cortex's own Bash and file edits.

## Without the model

The same code, for scripts, hooks and CI:

```bash
ds-next new NAME --answers answers.toml [--dir PARENT]   # tests/fixtures/answers.toml is an example
ds-next reconcile [PATH] [--quiet]                       # exit 1 only on a broken pointer or bad manifest
ds-next canon list [--tags python,cli] | canon read ID
ds-next skills
ds-next docs [--out DIR]
ds-next ask "PROMPT" [--yes]                             # one turn, printed like the terminal
```

## What a scaffolded repo gets

Python 3.12 with uv, src layout, a typer CLI for `kind = "cli"` (the ds-cli shape) or a plain
package, a passing test, ruff, and a GitLab CI file. Its docs are README.md, an AGENTS.md under
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
- `can_use_tool` receives a kind (`"MCP"`, `"Bash"`) and `{"action", "resource"}`. For MCP tools,
  the first line of `resource` is the tool's full name and the rest is its input.

## Not here yet

`reconcile --interactive` (adopt or decline a pending standard from the terminal; today the agent
can do it by editing the manifest, with approval), publishing captures as canon merge requests
(the so-capture skill's job), streaming partial text, and a published package so the CI
reconcile job can install it.
