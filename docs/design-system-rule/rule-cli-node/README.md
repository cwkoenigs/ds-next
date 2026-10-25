# rule-cli (Node)

The reference CLI for **Rule**, the ds-next terminal design system in the Modernist direction, built in TypeScript with [Ink](https://github.com/vadimdemedes/ink). The whole spec is in the source, `rule` walks through every part of it, and `rule demo` runs a live session drawn in Rule. The components are the design system in code, so a CLI built in this style can import them instead of redrawing frames by hand.

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
- **Approvals:** anything that writes a file or runs a command opens the approval dialog. `1` yes, `2` don't ask again for that tool this session, `3` or `esc` declines and stops the turn so you can say what to do instead. The terminal's own read-only tool, `rule_spec` (the agent can read this design system), never asks.
- **Keys:** `esc` interrupts a turn, `ctrl-o` opens the last fold, and messages typed mid-turn are queued.
- **Commands:** `/status`, `/model <name>`, `/clear` (new conversation) and `/exit` are local; any other `/command` goes to the agent.
- **Stalls:** a turn silent for 10 minutes, outside an approval, is interrupted, as in ds-next. The next message carries on the same session.

What it doesn't have yet is ds-next's own tools (canon, scaffolds, code search, `scaffold_project`). Those are the next step: the `ds` server in `src/agent/backend.ts` is where they go, next to `rule_spec`.

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
| `src/agent/` | `rule agent`: the backend choice and session (`backend.ts`), SDK messages reduced to a few events (`events.ts`), how tool calls read (`present.ts`), Markdown as rows (`markdown.ts`), and the app (`AgentApp.tsx`) |
| `src/html.ts` | `rule html` |

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
npm test           # 38 tests: every row fits 80 columns and every frame is exactly 80, the box stays closed
                   # while wrapping, the spec is complete, the demo, tour and agent session driven by
                   # keystrokes (the agent scripted), the permission gate, and both SDKs load
npm run typecheck
```

Dependencies are pinned to exact versions at least two weeks old, except `@snowflake/cortex-agent-sdk`, pinned at 0.0.2, the same version ds-next uses in Python (its versions are all newer than that). Ink 6.8 runs on Node 20; Ink 7 needs Node 22.
