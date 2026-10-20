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
