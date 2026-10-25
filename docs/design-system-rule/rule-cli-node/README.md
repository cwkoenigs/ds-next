# rule-cli (Node)

The reference CLI for **Rule**, the ds-next terminal design system in the Modernist direction, built in TypeScript with [Ink](https://github.com/vadimdemedes/ink). The whole spec is in the source, `rule` walks through every part of it, and `rule demo` runs a live session drawn in Rule. The components are the design system in code, so a CLI built in this style can import them instead of redrawing frames by hand.

The agent terminal also comes in **Rail**, the look ds-next ships today: steel blue on graphite, the dog and the cat, Cortex Code's rounded box. One CLI, two looks: `--look rail` (or `DS_LOOK=rail`) changes how it's drawn, nothing else. See [Two looks](#two-looks-rule-and-rail).

It matches the Python `../rule-cli/`. The one difference is that the input box here stays closed on all four sides while you type, which prompt_toolkit couldn't do.

## Run it

Needs Node 20 or newer. The commands are the same on Mac and Windows.

```sh
npm install        # installs and builds
npm link           # puts `rule` on your PATH
rule               # the tour: every section, enter between chapters, q quits
```

```sh
rule chapters              # list the 19 chapters
rule tour -c 3             # one chapter (3 = colour roles)
rule screen 5              # one of the seven screens, dark and light
rule screen                # all seven
rule spec --json           # the spec as data
rule html -o tour.html     # the tour as one web page, readable on a phone
rule demo                  # a live session with a faked agent: type, / for commands, ? for keys
rule agent                 # a real session with Cortex Code or Claude Code (see below)
```

```sh
rule demo --look rail      # the agent terminal in Rail, with a scripted agent: no login needed
rule agent --look rail     # a real session in Rail; or set DS_LOOK=rail once in your shell profile
rule screen --look rail    # Rail's ten screens, dark and light
rule html --look rail      # Rail's screens as one web page (rail-screens.html), readable on a phone
```

Options: `--theme dark|light` sets the theme for the prose and the demo. `--color truecolor|ansi16|none` forces the colour depth (otherwise it's whatever the terminal supports; 256-colour terminals like macOS Terminal get the palette downsampled). `--one-theme` shows each mockup only once. `--no-pause` prints the tour straight through, which also happens when the output is piped. To remove the command later: `npm rm -g rule-cli`.

On Windows, use Windows Terminal. The old console window lacks the box-drawing characters and truecolor.

## In the demo

- **Typing:** the box stays closed and grows downward when a line wraps. `←→`, `ctrl-a`, `ctrl-e` and `ctrl-u` edit the line.
- **`/`:** opens the command popup. `↑↓` move the ■, `tab` completes, `enter` runs.
- **A request** (anything that isn't a command) plays a faked turn. Thinking streams, then folds; each tool runs under the quadrant spinner, then lands. `esc` interrupts, and anything you type during the turn is queued until it ends.
- **The approval dialog** replaces the box. Press `1`–`3`, or `↑↓` and `enter`; `esc` declines.
- **`/status`, `/new`, `/standards`, `/skills`, `/scaffold`, `/help`, `?`** each print their screen.

## A real agent: `rule agent`

`rule agent` runs a real session with Cortex Code or Claude Code, drawn in Rule. It picks the agent the way ds-next does: `--agent cortex|claude`, then `DS_AGENT`, then `agent = "..."` in `~/.ds/config.toml`, then whichever CLI is on your PATH, Cortex first.

```sh
rule agent                          # whichever agent ds-next would use
rule agent --agent cortex --connection my-conn
rule agent --agent claude --model claude-sonnet-5-5
```

- **Cortex Code** needs the `cortex` CLI on your PATH (or `CORTEX_CODE_CLI_PATH`) and Node 22.22 or newer. It uses your Snowflake connection, as ds-next does.
- **Claude Code** works with no CLI installed: the SDK carries its own. It uses your normal Claude Code login, and the session costs what a Claude Code session costs.
- **What you see:**
  - Thinking folds to `· Thought for 3s`.
  - Each tool shows as ▫ while it runs, then lands as ▪ with its result as a fact (`142 lines`, `+14 −1`).
  - Replies print as Rule Markdown: uppercase headings, code on the surface colour.
  - Each turn ends with `N tools  12.3s  $0.0123` (Cortex reports no cost).
- **Approvals:** anything that writes a file or runs a command opens the approval dialog. `1` yes, `2` don't ask again for that tool this session, `3` or `esc` declines and stops the turn so you can say what to do instead. Reading never asks: ds's read-only tools, `rule_spec`, and the code graph's and LSP's reads.
- **Keys:** `esc` interrupts a turn, `ctrl-o` opens the last fold, and messages typed mid-turn are queued.
- **Commands:** `/status`, `/model <name>`, `/clear` (new conversation) and `/exit` are local; any other `/command` goes to the agent.
- **Stalls:** a turn silent for 10 minutes, outside an approval, is interrupted, as in ds-next. The next message carries on the same session.

### ds-next's tools

The agent gets ds-next's tools, ported to TypeScript in `src/ds/`, with the same names, descriptions and arguments, and ds-next's own system prompt:

- **Reads, never asked:** `canon_list`, `canon_read`, `skills_list`, `skill_read`, `project_status`, `scaffold_list`, `scaffold_get`, `block_list`, `block_get`, `code_search`, `code_get`, `snowflake_search`.
- **Writes, each through the approval dialog:** `scaffold_project` (only from a scaffold the agent fetched this session), `adopt_repo`, `block_add`, `code_add`, `capture`.
- **The code graph and the LSP** (`codebase-memory-mcp`, `serena`) are attached when installed, as in ds-next. The graph is refreshed when the session starts.

They read the canon and skills-os where ds-next does: `DS_CANON` and `DS_SKILLS`, else `~/Developer`, `~/code` or `~/.ds`. Without a canon the session still starts, and each tool that needs it says what to set up.

`code_get` and `code_add` cut a canon module down to the symbols asked for, using Python's own syntax tree. That one step runs ds-next's functions, copied unchanged into `python/code_cut.py`, with Python 3.10 or newer: `DS_PYTHON` if set, else `uv`, `python3`, `python` (or `py -3` on Windows). Repos created here get the same pre-push hook as ds-next's, which runs `ds-next reconcile`.

**Parity with ds-next.** `test/parity/run.sh` runs ds-next's Python tools and this port through the same 229 steps on a real canon and skills-os, then compares everything. That covers every standard, skill, scaffold and block read, `code_get` on every indexed symbol, a project created from each accepted scaffold (every file compared), `block_add`, `code_add`, `capture`, adopting two existing repos, and reconcile on broken manifests.

```sh
DS_CANON=~/Developer/canon DS_SKILLS=~/Developer/skills-os sh test/parity/run.sh
```

Two differences are expected:
- `canon_read` of an unknown id: ds-next's message carries extra quotes, a side effect of Python's `KeyError`.
- A manifest that isn't valid TOML: the error is worded by a different parser.

**Where the port departs from ds-next, on purpose:**
- **`adopt_repo` is offered to the agent.** ds-next defines it and its prompt tells the agent to use it, but it's missing from the tools ds-next registers.
- **List arguments are read as lists.** A list passed for `tags` or `ids` reads as the comma-separated string; ds-next would read the list's Python text.
- **A tool that fails says why.** A canon that no longer matches its index returns an `ERROR:` result instead of an exception.

## Two looks: Rule and Rail

`--look` picks how `rule agent`, `rule demo`, `rule screen` and `rule html` are drawn. Default: `$DS_LOOK`, else `rule`. The tour and the spec are Rule's own, so they don't change.

| | Rule | Rail |
|---|---|---|
| What it is | This design system: ink, one red, heavy square frames, the canoe | ds-next's: steel blue on graphite, the dog and the cat, ok/warn/err in green, amber and red |
| A turn | `━━ 03 ━━` opens it; ■ the agent, ▫ a running tool that lands as ▪, `└` its result | The box you typed in stays in the scrollback; `#3`, then one rail: ● the agent, `│ → Tool`, `│   ⎿ result`, `╰ #3 · 2 tool calls · 12.3s · $0.01` |
| Thinking | Folds to `· Thought for 3s` (`ctrl-o` opens it) | Stays private, as ds-next and Claude Code keep it; the spinner says `Thinking` |
| The box | Heavy, square, as wide as the terminal; a bare status row under it | Cortex Code's: rounded, the session tag (`New session`, `#2`) on a band in the top rule, the `/` menu below, a toolbar under it: the folder, where the repo stands against the canon, model, effort, connected |
| Approval | A red dialog in place of the box: `1` `2` `3`, or `↑↓` and `enter` | A warn-edged frame on the rail, `Allow Bash?`, the whole input; type `y`, `a` or `n` and `enter`. Enter alone asks again |
| Spinner | `▘ Drafting  4s  esc interrupts`, quadrants at 160 ms | `◐ Running canon_read · 4s · ctrl-c interrupts`, at 125 ms |
| `ctrl-c` | Leaves | Interrupts a turn; at the prompt it clears the line, and a second press within two seconds leaves |

Everything else is shared: the agent and its tools, the queue, `esc`, the watchdog, and the commands (`/status`, `/model`, `/last`, `/clear`, `/help`, `/exit`).

**Rail comes from ds-next itself.** The palette, ANSI-16 fallbacks, glyphs, spinner, grid and mascot in `src/rail/tokens.ts` are `src/ds_next/ui_style.py`'s values, and a test reads that file and checks every one. The builders in `src/rail/builders.ts` are its functions with the same names (`run`, `result`, `footer`, `frame`, `banner`, `promptBox`, `toolbar`...). The owner's departures from the design handoff are kept: the rounded box with the session tag, the brighter banner, ctrl-c twice to leave.

**Where Rail here departs from ds-next:**
- **Long lines wrap inside the box,** and the box that stays in the scrollback keeps the whole line. ds-next's box scrolls sideways and its echo is cut at the box's width.
- **The box stays up during a turn,** so you can queue the next message. ds-next shows only the spinner. `esc` interrupts too, besides `ctrl-c`.
- **`ctrl-o` opens the last tool output,** as the result line says. ds-next prints that hint but only `/last` does it; `/last` works here as well.
- **The banner names the agent** (Cortex Code or Claude Code; ds-next runs only Cortex) and points to `/help` and `?`. ds-next's local `/new`, `/adopt`, `/canon`, `/skills`, `/docs` and `/captures` forms aren't ported. Asking for those things in words goes to the agent, which has the same tools.
- **Markdown** headings are bold, flush left; fenced code is muted. Rich centres headings and highlights code.

**Fixed along the way, in both looks:** the box could send an older line. Keys go to the handler from the last render, so when `enter` came before React had redrawn after the previous key (fast typing, a paste, a busy machine), it sent what the line held before. The approval and the dialog had the same fault: a quick `y` `enter` could read as an empty answer. Each now keeps what was typed where every key reads it at once.

## What's where

| File | Holds |
|---|---|
| `src/tokens.ts` | Colour roles (dark, light, ANSI-16), glyphs, grid, spinner, verbs, mascot: `../tokens.json` typed |
| `src/spec.ts` | The spec as data: assumptions, the differences from Canopy, principles, colour, glyphs, grid, case, motion, code map, screens, known gaps |
| `src/text.ts` | The row model: a line is a list of spans with colour roles, so tests can measure every cell |
| `src/builders.ts` | Every message type as rows: `turnRule`, `you`, `agent`, `tool`, `result`, `thinking`, `thought`, `outcome`, `facts`, `frame`, `dialog`, `inputBox`, `statusRow`, `popupRows`, `banner` |
| `src/components/` | The design system as Ink components: static ones in `rule.tsx`, live ones in `live.tsx` (`Working`, `InputBox`, `Footing`, `DialogPicker`, `useLineEditor`), the write-once transcript, and `LiveTurn` |
| `src/screens.ts` | The seven screens and the spec page's mockups |
| `src/tour/`, `src/demo/` | The walkthrough and the faked live session |
| `src/agent/` | `rule agent`: the backend choice and session (`backend.ts`), SDK messages reduced to a few events (`events.ts`), how tool calls read (`present.ts`), Markdown as rows (`markdown.ts`), the two looks (`looks.tsx`: everything that differs between Rule and Rail), what this machine has for the banner and toolbar (`desk.ts`), and the app (`AgentApp.tsx`) |
| `src/rail/` | Rail: `tokens.ts` (ds-next's `ui_style.py` values), `builders.ts` (its line builders, frames, banner, box, toolbar, menu, approval), `screens.ts` (the ten screens) |
| `src/demo/scripted.ts` | The scripted agent behind `rule demo --look rail` |
| `src/ds/` | ds-next's knowledge base and tools, ported: `kb.ts` (canon, skills), `scaffold.ts` (new projects, adopting, blocks), `reconcile.ts`, `code.ts`, `codetools.ts`, `tools.ts` (the 17 agent tools and the system prompt), `py.ts` (the bits of Python behaviour the files depend on) |
| `python/code_cut.py` | ds-next's code-cutting functions, unchanged, for `code_get` and `code_add` |
| `test/parity/` | The comparison with ds-next's Python |
| `src/html.ts`, `src/html-page.ts` | `rule html`: the tour page, and with `--look rail` the Rail screens page |

## Using the components

```tsx
import {render} from 'ink';
import {TurnRule, You, Tool, Outcome} from './components/rule.js';
import {Footing, useLineEditor} from './components/live.js';

<TurnRule n={3} />
<You>add a --since flag</You>
<Tool name="Bash" args="uv run pytest -q" result="13 passed in 1.42s" more={11} />
<Outcome kind="warn" subject="security" detail="1 finding  /explain security" />
```

Write the transcript once with `useTranscript()` and `<Transcript>`, built on Ink's `<Static>`. Redraw only the footing.

## Checks

```sh
npm test           # 74 tests: every row fits 80 columns and every frame is exactly 80, the box stays closed
                   # while wrapping, the spec is complete, the demo, tour and agent session driven by
                   # keystrokes (the agent scripted) in both looks, Rail's tokens against ds-next's
                   # ui_style.py, the permission gate, both SDKs build all 17 tools, and the ds port on
                   # a small canon (render, write, reconcile, blocks, code, tools)
npm run typecheck
```

Dependencies are pinned to exact versions at least two weeks old, except `@snowflake/cortex-agent-sdk`, pinned at 0.0.2 (released 2026-10-13) because it is the version ds-next runs in Python. Ink 6.8 runs on Node 20; Ink 7 needs Node 22.
