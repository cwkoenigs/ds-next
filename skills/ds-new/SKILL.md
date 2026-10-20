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

Call `scaffold_list`. Use `AskUserQuestion` with one single-select question, "Which type?",
one option per **accepted** scaffold: label = its title, description = "outputs: …" (or "no
deployable outputs") then its id, version and tags.
If only one scaffold is accepted, still show the picker so the user sees what they are getting.

Then call `scaffold_get` with the chosen id. Keep its `version`, `tags` and `defaults`
(`test_cmd`, `lint_cmd`); you pass the version back when creating.

## 2. Three answers

Ask for whatever is still missing in **one** message, never one question at a time:

- **name**: lowercase-with-dashes, also the folder name. A name given in another case or with
  spaces: offer the lowercase-with-dashes form and use it only if they agree.
- **purpose**: one line, what it does and for whom.
- **owner**: default to `git config user.name`; only ask if that is empty.

That is the whole form. The type decides the tags, the test and lint commands and the outputs.
Do not ask about Snowflake schemas, extra tags, notes or declines: standards are declined later,
from status, when one actually gets in the way. Never invent a name or a purpose.

## 3. Show, then confirm

Call `canon_list` with the scaffold's tags. Show a four-line draft (type and version, name,
purpose, owner) and one line: "N standards apply · outputs: …". Then one `AskUserQuestion`:
"Create it?" with "Create", "Change something", "Cancel". On "Change something", ask what and
re-show once.

## 4. Create

Call `scaffold_project` with exactly: `scaffold`, `scaffold_version` (from step 1), `name`,
`purpose`, `owner`. Pass the user's values unchanged. The tool creates the
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
