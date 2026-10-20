# ds-next terminal design system

The source of the terminal's look, kept with the code it shapes. The canon standard is
[[terminal-design]]; the tokens ship as `src/ds_next/ui_style.py` (and as `block-ui-style` in the
canon, so every team CLI can import them from `canon_lib.ui_style`).

- `ds-next Terminal Design System.dc.html`: the system itself: principles, twelve colour roles,
  eleven glyphs, the 80-column grid, every message type, motion rules, three directions.
- `ds-next Screens.dc.html`: the full screen set for the chosen direction, Rail with Cortex chrome.
- `ds-next Baseline.dc.html`: the terminal as it ran before, for comparison.
- `HANDOFF-terminal.md`: the wiring plan that was applied to `ui.py`, `widgets.py` and `cli.py`.
- `ui_style.py`: the token module as delivered (the live copy is in `src/ds_next/`).
- `uploads/`: the reference screenshots (Cortex Code, Hermes, Claude Code).
- `_ds/industry-*`: the Industry web design system whose steel ramp the colour roles derive from.
- `export/`: the design-system package from the Claude Design project: `readme.md` (principles,
  content fundamentals, visual foundations), `tokens/` (CSS roles), `guidelines/` (specimen cards),
  `components/terminal/*.prompt.md` (the nineteen primitives), `assets/mascot.txt`. The React
  sources stay in the project (https://claude.ai/design/p/81fef9af-a683-4f05-a370-344af3d1ea9e).
- `../../skills/ds-terminal-design/`: the installable skill that points an agent at all of this.

Open the `.dc.html` files in a browser.

## Where the code departs from the delivered files (as of 2026-10-20, handoff 2)

The pages here are the current exports (marks 2a–2d, the mascot in the 1a banner). The code in
`src/ds_next/` is the handoff's code plus these, which the handoff predates or does not cover:

- **The prompt is a closed frame, drawn around a PromptSession.** Both a multi-line prompt
  message and a multi-row Application (`widgets.prompt_line`) redraw one row lower per keystroke in
  VS Code's terminal once the completion menu changes the height. A PromptSession reserves the
  menu's rows up front and stays put, so the frame is built from what it supports: the top rule
  with the session tag printed once (`session_rule`), the right edge as the right prompt, the
  bottom rule as the first line of the toolbar, and the bottom rule reprinted when the line is
  accepted. `prompt_line` stays in the widgets for terminals that handle it.
- **`agent_lines`.** `Text.rstrip()` mutates in place and returns None; the handoff prints "None"
  for every agent line. Fixed in the live copy.
- **Banner chrome** is brighter: title and word-mark in `strong`, labels in `accent`, a `muted` edge,
  at the owner's request to read closer to Cortex.
- **Outcome lines** carry `counts()`, the numbers without the repo name, since the name is the
  subject of the line.
- **The form** keeps the live rules from before the handoff: an example while a field is empty, the
  name normalised as you type, a red line while it breaks [[repo-naming]].
- **Leaving.** `/exit` and ctrl-c twice both leave, besides ctrl-d.
- `ui_style.py` beside the pages is the live copy; the handoff's is in `handoff/ds_next/`.
