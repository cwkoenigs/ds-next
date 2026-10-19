---
name: ds-new
description: >-
  Start a new project from an accepted canon scaffold, the team's standard way: pick the
  scaffold, answer a short form, see which standards apply, confirm, and the ds tools create
  it. Use when the user types /ds-new, or asks to start, create or scaffold a new project or
  repo. Never write project files by hand.
---

# /ds-new: a project from the canon

This is the same procedure as the orange `ds-next` terminal's `/new`, run inside Cortex Code.
Everything the user picks goes through the `ds` MCP tools (`scaffold_list`, `scaffold_get`,
`canon_list`, `scaffold_project`). If those tools are not available, stop and say:
`cortex mcp add ds ~/Developer/ds-next/.venv/bin/ds-next mcp`, then restart Cortex.

The user may have typed arguments: `/ds-new`, `/ds-new <name>`, or `/ds-new <name> <purpose...>`.
Use what they gave and do not ask for it again.

## 1. Pick the scaffold

Call `scaffold_list`. Use `AskUserQuestion` with one single-select question, "Which scaffold?",
one option per **accepted** scaffold: label = its title, description = its id, version and tags.
If only one scaffold is accepted, still show the picker so the user sees what they are getting.

Then call `scaffold_get` with the chosen id. Keep its `version`, `tags` and `defaults`
(`test_cmd`, `lint_cmd`); you pass the version back when creating.

## 2. The form

Ask for everything still missing in **one** round, never one question at a time.

- If name or purpose is missing, ask for both in one short message:
  "Name (lowercase-with-dashes) and purpose (one line: what it does and for whom)."
  A name the user gives in another case or with spaces: offer the lowercase-with-dashes form and
  use it only if they agree. Never invent a name or a purpose.
- Then one `AskUserQuestion` with these questions:
  1. **Snowflake** (single): "None", or Other for `DATABASE.SCHEMA` it reads or writes.
  2. **Owner** (single): the git user from `git config user.name` as the first option, or Other.
  3. **Declines** (single): "None", or Other as `id: reason; id: reason` for standards declined now.
  4. **Extra tags** (multi): the common tags not already in the scaffold's (`snowflake`,
     `cortex`, `mcp`, `data`), or Other. A Snowflake schema adds `snowflake` by itself.

`test_cmd` and `lint_cmd` come from the scaffold's defaults; mention them, do not ask.

## 3. Show what applies, then confirm

Call `canon_list` with the scaffold's tags plus any extras. Show the draft as a short table
(scaffold and version, name, purpose, snowflake, owner, tags, test, lint, declines) and one
line: "N standards apply (K gotchas)." If a decline names a standard that is not in that list,
say so. Then one `AskUserQuestion`: "Create it?" with "Create", "Change something", "Cancel".
On "Change something", ask what and re-show the table once.

## 4. Create

Call `scaffold_project` with: `scaffold`, `scaffold_version` (from step 1), `name`, `purpose`,
and only the optional fields the user actually set (`snowflake`, `owner`, `tags`, `notes`,
`declines`, `test_cmd`, `lint_cmd`). Pass the user's values unchanged. The tool creates the
repository in the current directory; it refuses a stale scaffold version, a bad name or a
non-empty directory, and the message says why. Report that message as it is; do not retry
with values you made up.

## 5. Report

Three lines: the path created and scaffold version; the reconcile summary the tool returned
(adopted, declined, pending); and the next commands:

```
cd <name> && uv run pytest -q
```

Do not run the tests yourself unless asked. Do not edit the created files.

## Rules

- `scaffold_project` is the only way a project comes into being. Never create directories or
  files for a new project with Bash, Write or Edit.
- Never replace an answer with one you made up. A purpose, name or schema you invent is not a
  suggestion.
- Be brief. This is a terminal.
