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

Open the `.dc.html` files in a browser.

## Where the code departs from the delivered files (as of 2026-10-20, handoff 2)

The pages here are the current exports (marks 2a–2d, the mascot in the 1a banner). The code in
`src/ds_next/` is the handoff's code plus these, which the handoff predates or does not cover:

- **The prompt.** The handoff's two-line prompt message redraws one row lower on every keystroke in
  VS Code's terminal (the session tag stacks). The rule with the tag is printed once as a static
  line (`session_rule()`) and the prompt is one line, `│ › `. The handoff's own "known gap" stands:
  no closing rule while you type.
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
