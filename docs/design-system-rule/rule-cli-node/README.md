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
rule demo                  # a live session: type, / for commands, ? for keys, ctrl-d leaves
```

Options: `--theme dark|light` sets the theme for the prose and the demo. `--color truecolor|ansi16|none` forces the colour depth (otherwise it's whatever the terminal supports; 256-colour terminals like macOS Terminal get the palette downsampled). `--one-theme` shows each mockup only once. `--no-pause` prints the tour straight through, which also happens when the output is piped. To remove the command later: `npm rm -g rule-cli`.

On Windows, use Windows Terminal. The old console window lacks the box-drawing characters and truecolor.

## In the demo

- **Typing:** the box stays closed and grows downward when a line wraps. `←→`, `ctrl-a`, `ctrl-e` and `ctrl-u` edit the line.
- **`/`:** opens the command popup. `↑↓` move the ■, `tab` completes, `enter` runs.
- **A request** (anything that isn't a command) plays a faked turn. Thinking streams, then folds; each tool runs under the quadrant spinner, then lands. `esc` interrupts, and anything you type during the turn is queued until it ends.
- **The approval dialog** replaces the box. Press `1`–`3`, or `↑↓` and `enter`; `esc` declines.
- **`/status`, `/new`, `/standards`, `/skills`, `/scaffold`, `/help`, `?`** each print their screen.

## What's where

| File | Holds |
|---|---|
| `src/tokens.ts` | Colour roles (dark, light, ANSI-16), glyphs, grid, spinner, verbs, mascot: `../tokens.json` typed |
| `src/spec.ts` | The spec as data: assumptions, the differences from Canopy, principles, colour, glyphs, grid, case, motion, code map, screens, known gaps |
| `src/text.ts` | The row model: a line is a list of spans with colour roles, so tests can measure every cell |
| `src/builders.ts` | Every message type as rows: `turnRule`, `you`, `agent`, `tool`, `result`, `thinking`, `thought`, `outcome`, `facts`, `frame`, `dialog`, `inputBox`, `statusRow`, `popupRows`, `banner` |
| `src/components/` | The design system as Ink components: static ones in `rule.tsx`, live ones in `live.tsx` (`Working`, `InputBox`, `Footing`, `DialogPicker`, `useLineEditor`), the write-once transcript, and `LiveTurn` |
| `src/screens.ts` | The seven screens and the spec page's mockups |
| `src/tour/`, `src/demo/` | The walkthrough and the live session |
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
npm test           # 24 tests: every row fits 80 columns and every frame is exactly 80, the box stays closed
                   # while wrapping, the spec is complete, and the demo and tour driven by keystrokes
npm run typecheck
```

Dependencies are pinned to exact versions at least two weeks old. Ink 6.8 runs on Node 20; Ink 7 needs Node 22.
