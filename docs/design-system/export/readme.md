# ds-next terminal design system

A design system for terminal interfaces: the look of `ds-next`, a Claude-Code-style REPL over
Cortex Code that scaffolds and checks data-science projects against a team canon. It is written
for two problems — **UI movement** (what appears, where, and what stays still) and **information
navigation** (finding the thing you need in a long session) — and it applies to any CLI the team
builds: same glyphs, same columns, same colours.

Sources: the `ds-next` codebase (`src/ds_next/ui.py`, `widgets.py`, `cli.py`), reference CLIs
Cortex Code, Claude Code and Hermes, and the Industry design system (steel accent, Barlow type) for
the documentation around the terminal. Design pages: `ds-next Screens.dc.html` (the chosen
direction, all screens), `ds-next Terminal Design System.dc.html` (roles, glyphs, grid, three
directions), `ds-next Baseline.dc.html` (the CLI before). Code: `handoff/ds_next/`.

## Principles

- **One rail.** Everything the agent does in a turn hangs off one vertical line in column 1. Local commands have no rail: they are instant and flat.
- **Three voices.** You (`›`, accent strong), the agent (`●`, accent), the machine (`→ │ ⎿`, muted). `✓ ⚠ ✗` are the only other colours.
- **Nothing moves that didn't change.** One live line at a time, reused in place. Labels, gutters, the toolbar never shift.
- **Everything is addressable.** Turns are numbered, results fold to one line with a count and a key, ids are things you can type back.
- **A frame means "needs you".** Boxes are rare and always mean input: a form, an approval. Output is never boxed. The banner is the one decorative exception, shown once.
- **Same grammar without the model.** CI output prints the same glyphs and columns, minus colour when not a TTY.

## Content fundamentals

Lowercase, terse, no trailing periods on single lines: `16 adopted · 0 pending`. Facts are joined
with ` · `. Second person, imperative hints: `/new starts a project · /help lists commands`. Errors
name what failed and then the fix, never a stack trace: `✗ canon not found at ~/Developer/canon` /
`set DS_CANON=<path> or run ds-next init`. Tool names are bold and exactly as the tool is called;
arguments are muted. No emoji; glyphs are the twelve in `guidelines/glyphs.html` and nothing else.
Keys are written as `Tab next · ↑ back` with the one submit key as a filled band.

## Visual foundations

- **Colour.** Twelve roles, two themes (`tokens/colors.css`). Dark is default; `[data-theme="light"]` flips. The accent is Industry steel stepped to 400 on dark / 700 on light so accent text stays 4.5:1. ok/warn/err are OKLCH at the accent's lightness. Colour names a voice or an outcome — never decoration. One filled band per screen (brand): the prompt tag or the submit key.
- **Type.** JetBrains Mono 12.5/19, regular and bold; every row exactly one line tall. Documentation around the terminal uses Barlow Condensed / Barlow.
- **Grid.** 80 columns, degrades to 60. Two indents: col 3 for what is said or run, col 5 for what came back. Label column 12 shared by forms, /status, reconcile. One blank line between turns, none inside; frames get one above and below.
- **Frames.** Square box-drawing (`┌ ─ ┐ │ └ ┘`), title in the top rule, keys in the bottom rule. Dim edge for input, warn edge for approvals. The banner is two panes with `┬ ┴` and a path footer. No rounded corners, no shadows, no fills except the band, the menu's focused row (hl) and the toolbar (surface).
- **Motion.** One live line (`◐◓◑◒` at 8 fps, seconds once a second). Append, never reflow. Widgets erase themselves whole and leave one static line. Results fold; ctrl-o opens the last fold.
- **Hover / press.** None — it's a terminal. Focus is `❯` in accent strong on the focused row; the menu's focused row is filled with hl.
- **Imagery.** None, except the mascot: a dog (brand) and cat (accent strong) with their arms around each other, 28×20 pixels in half-blocks, shown once in the banner.

## Iconography

No icon font. Twelve unicode glyphs, each with one meaning, one colour, one column
(`guidelines/glyphs.html`). All are in Menlo, SF Mono, JetBrains Mono, Cascadia and DejaVu, so a
VS Code terminal draws them without a Nerd Font. Retired: `◆`, `▼`, braille spinners, rounded
panels. No emoji, ever. There is no logo file — the word-mark is plain type (`guidelines/wordmark.html`).

## Index

- `styles.css` → `tokens/` fonts, colors, typography, grid.
- `guidelines/` — specimen cards: colours (dark, light, outcomes, rules), type (mono, doc), glyphs, grid, motion, mascot, word-mark.
- `components/terminal/` — Term, Line, You, Agent, Run, Result, Status, Footer, Outcome, Labelled, Hint, ErrorLine, Key, Frame, Mascot, Banner, Prompt, Toolbar, Menu (+ `terminal.card.html`).
- `ui_kits/terminal/` — a full session screen, dark/light.
- `assets/mascot.txt` — the mascot pixel grid (D dog · C cat · k eye · . empty).
- `handoff/ds_next/` — the Python that renders all of this with Rich + prompt_toolkit (`ui_style.py` holds the same tokens).
- `SKILL.md` — for Claude Code.

Intentional additions beyond the ds-next source: `Line` (a raw row) and `Key` (the filled key), because frames and key lines need them.
