# What is `ds`?

Written 2026-10-23, after `/mcp` in Claude Code reported "Reconnected to ds."

`ds` is the MCP server built into ds-next, the knowledge-base terminal rebuilt in
mid-October 2026. It is a local tool, not something from Anthropic.

## Where it comes from

The user-level Claude Code MCP config (`~/.claude.json`, key `mcpServers.ds`) runs:

```
/Users/clarkkoenigs/Developer/ds-next/.venv/bin/ds-next mcp
```

That is the same binary `~/.local/bin/ds-next` points at, the one whose pre-push
reconcile hook was fixed in ds-next PR #1 on 2026-10-20.

## What it does

ds-next ties together four repos: canon (versioned standards, `~/Developer/canon`),
skills-os (the `/so-*` procedures, `~/Developer/skills-os`), docs-ds (the Docusaurus
shell, `~/Developer/docs-ds`) and whichever repo is being worked in. The `mcp`
subcommand exposes that knowledge base to Claude Code as tools:

| Tool(s) | Purpose |
|---|---|
| `canon_list`, `canon_read` | read standards from canon |
| `skills_list`, `skill_read` | read the skills-os procedures behind the `/so-*` commands |
| `scaffold_list`, `scaffold_get`, `scaffold_project` | create a new repo from a canon scaffold |
| `capture` | draft new knowledge into `.ds/captures/` for a merge request back to canon |
| `block_add`, `block_get`, `block_list` | store and list reusable blocks |
| `code_add`, `code_get`, `code_search` | store and search code snippets |
| `project_status` | report a repo's `.ds/manifest.toml` state |
| `snowflake_search` | search Snowflake objects |

## The "needs authentication" warning

The `⚠ 1 MCP server needs authentication` banner was a stale status from before the
server reconnected. `ds` is a local stdio process with no login, so there is nothing
to authenticate. Running `/mcp` reconnected it and cleared the warning.
