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
