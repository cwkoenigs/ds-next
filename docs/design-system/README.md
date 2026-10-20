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

## Where the code departs from the documents (as of 2026-10-20)

The `.dc.html` exports are frozen at delivery. These are the differences a reader will notice:

- **The mascot.** The design system document retires `▼` and leaves the banner's left pane to the
  word-mark. The handoff (`handoff/`) then added the dog and cat, and that is what ships:
  `MASCOT` and `mascot_lines()` in `ui_style.py`, with the roles `eye`, `on_brand`, `on_strong`,
  `on_eye`.
- **The prompt.** The screens show a two-line framed prompt. prompt_toolkit redraws a multi-line
  prompt message one row lower on every keystroke, so the rule with the session tag is printed
  once as a static line (`session_rule()`) and the prompt itself is one line, `│ › `. The bottom
  edge is the toolbar band, as the handoff's "known gap" already said.
- **Colours in prompt_toolkit.** Rich's `on x` and `bright_black` are not prompt_toolkit syntax;
  `_pt()` translates the palette for the prompt, menu and widgets.
- **The footer** counts tool calls (`#1 · 3 tool calls · 15.2s`), as the screens show, by counting
  tool-use blocks; the SDK's own turn count is not shown.
- **Outcome lines** carry the counts without the repo name (`✓ feed-model  26 adopted · 0 declined ·
  0 pending`); the name is the subject, so it is not repeated.
- **The form** has a `type` field cycled with ←/→ (the screens show it), plus live rules the screens
  predate: an example while a field is empty, the name normalised as you type, a red line while it
  breaks [[repo-naming]].
- **Leaving.** `/exit` and ctrl-c twice both leave, besides ctrl-d.
- `ui_style.py` here is the live copy, not the delivered one; the delivered one is in `handoff/`.
