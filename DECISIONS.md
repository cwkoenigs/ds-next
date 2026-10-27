# Decisions

<!-- ds:local interview 2026-10-16 -->
Local decisions for this repo, numbered local-001 upward. Team-wide decisions belong in the
canon as standards; this file links them with `[[id]]` rather than restating them.

## local-001: No settings file runs or approves anything on its own

- **Status:** Accepted
- **Date:** 2026-10-26
- **Context:** rule-cli's review (its local-015 to local-017) found three things that apply here,
  the same SDK options being in `sdk.py`: a cloned repo's `.claude/settings.json` hooks ran in a
  Claude session; Cortex Code ran a repo's `.cortex` and `.claude` hooks; an allow rule in the
  person's own Claude settings ran a command without `can_use_tool`. A repo's own permission rules
  did not skip it, in either agent.
- **Options considered:** for Claude, honouring the rules, a managed-settings lock (dropped where an
  IT tier exists) or dropping user settings (losing `CLAUDE.md` and skills); for Cortex,
  `setting_sources=["user"]` (hooks still ran, instructions lost) or `disableAllHooks` through
  `--config` (hooks still ran), both tried live in rule-cli. Chosen: Claude gets
  `settings='{"disableAllHooks": true}'` and a `PreToolUse` callback (`sdk.ask_first`) that answers
  "ask" for every tool but Claude Code's reads; Cortex asks the person, with every hook's command,
  before a session starts where a repo's settings define hooks (`sdk.project_hooks`).
- **Consequences:** the person's own Claude hooks do not run in ds-next, and their allow rules do
  not save a question. Cortex in a repo with hooks costs one question per run.
- **Validation:** `tests/test_agent_settings.py`, with the real Claude Code offline (a home of its
  own, a fake key, a stand-in Messages API): no repo hook runs, and a command the person's settings
  allow still asks. Both failed before.
- **Review date:** each SDK upgrade.

## local-002: A block's manifest table lists the files it wrote

- **Status:** Accepted
- **Date:** 2026-10-26
- **Context:** `add_block` and `code.add` checked for files in the way only on a first add, so an
  update that brought a new file replaced whatever was there, against their own promise ("a file
  the block did not write before is never overwritten"). Nothing recorded which files a block
  wrote. They also wrote `pyproject.toml` and the manifest through a symbolic link.
- **Options considered:** compare contents (an older version's files are not in the canon); refuse
  every existing file on update (every update would fail); record the files: chosen.
- **Decision:** each `[blocks.<id>]` table gains `files = [...]`. An update replaces only those; for
  a table written before, the recorded module and the tests that import it, as a block's own tests
  do. Both refuse a linked `pyproject.toml` or manifest before writing anything. rule-cli's port
  does the same, and its parity check matches the two.
- **Consequences:** a manifest from before this keeps working; its next update writes the list.
- **Validation:** `tests/test_blocks.py`: an update refuses a file the block did not write, a legacy
  table trusts the tests that import the module, and no metadata goes through a link.
- **Review date:** when the manifest format next changes.

## local-003: The code tools come from ds-code, in place of the code graph and Serena

- **Status:** Accepted
- **Date:** 2026-10-27
- **Context:** ds-next attached codebase-memory-mcp (a code graph) and Serena (a language server)
  when installed. rule-cli replaced both with its own code tools, eight read-only tools answered
  by TypeScript's server and Pyright, and found the graph's packages download their binary around
  a registry mirror, and Serena a GPL-3.0 middleman to the same servers that reports its use. Those
  tools now live on their own as ds-code, an MCP server any agent starts. ds-next is the one terminal.
- **Options considered:**
  1. **Keep the graph and Serena**: two installs outside npm, one of them needing the graph rebuilt
     as a session starts.
  2. **Port the code tools to Python**: the language servers are npm packages, so it would still run
     Node, and two copies would need a parity test.
  3. **Attach ds-code as `code`**: chosen. One install from npm; every tool is a read, so none asks.
- **Decision:** `codetools.mcp_servers` offers `ds-code mcp <repo>` as `code` when `ds-code` is on the
  PATH (through `cmd /c` when what is found is npm's .cmd shim, as on Windows), and `read_only_ids` lists its eight
  tools. The graph, its index refresh while connecting, Serena and this repo's `.serena/` go. The
  prompt and the AGENTS.md a new repo gets name the `code` tools.
- **Consequences:** A machine without ds-code gets no code tools, as before without the graph and
  Serena. Starting a session no longer waits on indexing.
- **Validation:** `tests/test_codetools.py`. Started from this config, `ds-code mcp` served its eight
  read-only tools over stdio and answered `references` and `callers` on this repo from Pyright,
  tests included. The Windows form is not yet run on Windows.
- **Review date:** when ds-next has CI on Windows.

