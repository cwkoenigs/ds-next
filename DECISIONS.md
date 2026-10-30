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

## local-004: Codex through its app-server, every tool served by ds-next

- **Status:** Accepted
- **Date:** 2026-10-27
- **Context:** The owner's work computer has Cortex Code and Codex, not Claude Code. rule-cli drove
  Codex (its local-009); with rule-cli cut down to the code tools (ds-code), ds-next is the terminal
  and needs Codex as a third agent, with the same tools and the same approvals.
- **Options considered:**
  1. **`codex exec`**: it cannot ask before a command runs or a file changes, and takes no tools from
     the client.
  2. **`codex app-server`, tools from MCP servers in Codex's config**: Codex would approve the ds
     writes by its own rules, not ds-next's, and its protocol has no approval request for an MCP tool.
  3. **`codex app-server`, every tool a dynamic tool served by ds-next**: chosen, as rule-cli did.
- **Decision:** `DS_AGENT=codex` (or `agent = "codex"`, or `codex` alone on PATH) runs `codex
  app-server` (CODEX_CLI_PATH, else `codex` on PATH). `codex.py`'s client has the SDK clients' shape
  and turns Codex's notifications into the SDK's message types, so the agent loop and the UI are
  unchanged. ds-next's own tools are called through their in-process server's handlers; ds-code's
  through an MCP client session. Threads run `approvalPolicy: untrusted` in the `workspace-write`
  sandbox; `ds` and `code` in the user's Codex config are switched off, since they are served already.
  A denial declines (the model is told and asks); one that says to interrupt cancels the turn. Codex
  starts in a session of its own and is ended by the end of its input, then its process group.
  `ds-next setup --agent codex` registers `ds` with Codex and links the skills.
- **Consequences:** Codex is whatever the machine has installed, not pinned, and its app-server is
  marked experimental. Its turns show tokens, not dollars.
- **Validation:** `tests/test_codex.py`: a stand-in app-server plays a turn (a ds tool unasked, a
  command asked, yes, no and interrupt); the code tools reach Codex through their server; and the
  real app-server (0.162.1 here), its model calls going to a local stand-in, called a ds tool without
  asking and ran a command on a yes and not on a no. `ds-next ask` with `DS_AGENT=codex` drew a
  whole turn. Codex has not yet been run against a real model, nor on Windows.
- **Review date:** each Codex upgrade.

## local-005: The look comes from ds-cli-design

- **Status:** Superseded by local-006 (2026-10-28)
- **Date:** 2026-10-27
- **Context:** ds-next kept its own `ui_style.py`; ds-cli-design, the terminal design system as a
  library (atlas uses it), held a copy from the design export, and rule-cli a third in TypeScript.
  The owner wants one design system. Its values were already equal; ds-next's banner and prompt box
  were the newer look.
- **Options considered:**
  1. **Keep ds-next's copy**: every change to the look made twice, and atlas drawn from an older one.
  2. **ds-cli-design as the one copy, ds-next imports it**: chosen. ds-cli-design 1.1.0 took ds-next's
     banner and prompt box; drawn from it, ds-next's banner, box, theme and prompt_toolkit styles are
     identical, span for span.
- **Decision:** ds-next depends on `ds-cli-design @ git+https://github.com/cwkoenigs/ds-cli-design@v1.1.0`
  and imports `ds_cli_design.ui_style`; `src/ds_next/ui_style.py` is gone. A change to the look is made
  in ds-cli-design, released as a tag, and taken here by moving the pin.
- **Consequences:** ds-cli-design was made public for this (2026-10-27), so ds-next, its CI and atlas
  install it with no login. Its first commit carries an older copy of four ds-next files from the
  design export (`examples/ds-next/`), public with it; the owner accepted that.
- **Validation:** the whole suite on the library's style; banner, prompt box, theme and
  prompt_toolkit styles compared span for span with the deleted copy.
- **Review date:** the next design export.

## local-006: The look comes from canon-lib

- **Status:** Accepted
- **Date:** 2026-10-28
- **Context:** local-005 made ds-cli-design the one copy of the look without weighing the canon's
  own path for it, released on 2026-10-20 and never replaced by a decision: the accepted standard
  [[terminal-design]], `block-ui-style` and `block-tui-widgets`, built into `canon_lib.ui_style` and
  `canon_lib.widgets`, which the `python-cli` scaffold imports. canon-lib is how accepted code reaches
  repos ([[adr-001]]), and the owner's split is that canon-lib carries the code projects import while
  the MCP carries the knowledge. Canon v5 of `ui_style` was ds-next's own copy, so ds-cli-design 1.1.0
  differed from it only in `banner(name=...)`; `src/ds_next/widgets.py` was canon's v7 with its two
  import lines changed.
- **Options considered:**
  1. **Keep ds-cli-design as the one copy**: a second package of accepted code beside canon-lib,
     against the owner's "one package of the canon (canon-lib) at most".
  2. **canon-lib, the `tui` extra, pinned to a tag**: chosen. canon took `banner(name=...)` (block-ui-style
     v6) and atlas's `browse` (block-tui-picker, proposed) and released canon-lib 0.2.0 as the tag
     `canon-lib-v0.2.0` (cwkoenigs/canon#1).
- **Decision:** ds-next depends on `canon-lib[tui] @ git+https://github.com/cwkoenigs/canon@canon-lib-v0.2.0#subdirectory=lib`
  and imports `canon_lib.ui_style` and `canon_lib.widgets`; its copy of `widgets.py` and the copy of
  canon's `ui_style` tests are gone. A change to the look is made in the canon's blocks, released as a
  canon-lib tag, and taken here by moving the pin. ds-cli-design keeps the design exports and checks
  `tokens.json` against the canon's code.
- **Consequences:** ds-next and atlas draw from the same code as every repo made from `python-cli`.
  New repos also stop pointing at one person's checkout: `scaffold.canon_lib_source` gives them
  canon-lib from git at its tag, from the canon's own origin (the team's copy at work), and falls back
  to the path only where the tag is missing. The agent is told to import canon-lib first; `code_add`
  and `block_add` are for a repo that cannot take the dependency (adr-001's second door).
- **Validation:** the whole suite on canon-lib 0.2.0, installed from the tag; `canon_lib_source` against
  a checkout with and without an origin and the tag.
- **Review date:** the next canon-lib release.

## local-007: One file per machine says which world it is in

- **Status:** Accepted
- **Date:** 2026-10-28
- **Context:** What differs between the owner's machines and a work machine (the git host, the group
  the team's repos live under, how to authenticate) was spread out: canon's `install.sh` worked it
  out and kept it only in the clones' remotes, and `/so-capture` read a file of its own
  (`~/.config/so-capture/config.toml`) that could only describe GitLab and existed on no machine.
  The owner asked for one config to fill out per world. `set_default_agent` also rewrote
  `~/.ds/config.toml` keeping top-level values only, so any table in it was lost on the next setup.
- **Options considered:** a YAML file of its own (a second format beside the TOML ds-next and Codex
  already use); `~/.config/so-capture` extended (one skill's file for what the whole system needs);
  `~/.ds/config.toml`, the file ds-next already keeps per machine: chosen.
- **Decision:** `~/.ds/config.toml` holds `agent`, `[world]` (`host`, `group`, `token_env`) and
  `[capture]` (`repo`, `branch`, `dir`). canon's `install.sh` writes `[world]` and `[capture]` when it
  has settled the team host and the file has no `[world]` yet; `/so-capture` reads them, falling back
  to the canon checkout's remote. `set_default_agent` changes only the `agent` line.
- **Consequences:** `ds-next setup` no longer loses a table; a config that is not TOML is kept as
  `config.toml.bak`. Nothing in ds-next reads `[world]` yet.
- **Validation:** `tests/test_setup.py`: the tables survive two setups and the agent line is never
  duplicated (both new tests fail on the old writer); a broken file is kept aside.
- **Review date:** when a second tool needs `[world]`.

## local-018: `ds-next setup` owns every connection, and can undo it

- **Status:** Accepted
- **Date:** 2026-10-29
- **Context:** The guide promised that an agent on a set-up machine has the `ds` tools, the `code`
  tools "with ds-code on PATH", and the `/so-*` skills. Only the first was true outside the ds-next
  terminal: `setup` registered `ds` alone (the terminal attached `code` to its own sessions), and the
  `/so-*` links in `~/.claude/skills` on the owner's Mac were made by hand on 2026-10-13. Nothing
  undid any of it; a machine could be installed and updated but not cleanly removed, and a sandbox
  trial on 2026-10-29 left skill paths under `/private/tmp` in Cortex's list for good.
- **Options considered:**
  1. **Leave `code` to each repo's `.mcp.json` and the skills to skills-os's `install.sh`**: three
     mechanisms for one promise, none of them reversible, and the repo file only reaches a repo that
     carries it.
  2. **A separate `ds-next teardown` command**: a second place that has to know what setup wrote.
  3. **`setup` registers everything the guide promises, and `setup --remove` reverses exactly that**:
     chosen. One table (`CLIS`) says how each agent CLI is driven; `servers()` and `skill_dirs()` say
     what to connect; connect and disconnect walk the same lists.
- **Decision:** `setup` registers `ds` and, when `ds-code` is on PATH, `code` (`ds-code mcp`, through
  `cmd /c` for npm's Windows shim); links `/ds-new`, `/ds-terminal-design` and every `so-*/SKILL.md`
  of the skills-os checkout kb already locates; allows the read-only tools of both servers in Claude
  Code and Cortex Code. `setup --remove` unregisters the two servers, unlinks only links that resolve
  into our checkouts (Cortex: `skill remove` by path), drops the rules of both servers whether or not
  ds-code is installed now, and leaves `~/.ds/config.toml` to canon's `uninstall.sh`. Codex's
  app-server already switched both servers off in the terminal, expecting this.
- **Consequences:** The guide's claim is true in every agent, and canon's `uninstall.sh` has one
  command to call. A link that is not ours is reported and left alone, both ways.
- **Validation:** `tests/test_setup.py`: `code` registered and allowed when ds-code is on PATH;
  skills-os skills linked, a foreign link kept; `--check` runs only `get`/`list`; remove empties the
  registry, the links and the rules and leaves the rest; a second remove still succeeds; Cortex adds
  and removes by path. 168 tests pass.
- **Review date:** when a fourth agent CLI is added, to see whether `CLIS` still describes it.
- **Revised 2026-10-29, after an external review (Codex, #16):** remove only unregisters a `ds` or
  `code` that runs our command and names one that does not; a `code` registration outlives ds-code's
  removal and still comes off by its command name; allow rules are written only for servers that
  registered; remove unlinks every link into ds-next's skills or skills-os, dangling ones included, and
  leaves all others; `permissions` of an odd shape (null, a list, a string) are tolerated; skill paths
  are absolute even from a relative `DS_SKILLS`. Not taken: locking settings.json against a concurrent
  agent write (a one-shot CLI with a `.bak`), and telling a failed `mcp get` from "not registered"
  (the CLIs' exit codes do not distinguish them).
- **Simplified 2026-10-29, after a cleanup review (#17):** the two servers are one static table
  (`servers()`: name, command basename, read-only tools) and each computes its own argv; a registration
  is "ours" when its command is `ds-next` or `ds-code` wherever installed, so remove also takes a
  registration left by an older install, and `removable()`/`all_rules()`/the three `setup_<agent>`
  wrappers are gone. `kb.bases()` names the places repositories are looked for, and remove recognises a
  link into skills-os under any of them.
