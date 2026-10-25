# Rule — status

Third direction, derived from the Modernist design system. Not yet accepted. Rail (`final/`) remains shipped; Canopy (`canopy/`) is the other candidate.

## Decisions taken in this draft
- Modernist mapped to the terminal: 2px rules → heavy box-drawing; radius 0 → square frames and square markers; mono + red → text/muted/dim/rule + accent/accent text only; flush-left → titles in rules, uppercase labels.
- No green/yellow: done is ink, ⚠ red, ✗ bold red.
- Numbered turn rule before every prompt (addressable turns, Modernist's visible structure).
- Same hybrid shape as Canopy: pinned footing, folded thinking, numbered dialogs, popup.
- Mascot: canoe with a red paddle (two inks, like the system). Facts use two-space separators.

## Known gaps
- With no green, a long `/status` with many ✓ reads flat — intentional, but worth a check on a real session.
- Heavy box-drawing (━ ┃ ┏) needs a font with the full box set; Menlo/JetBrains Mono/Cascadia have it, some bitmap fonts don't — fall back to light lines via `G` if `DS_RULES=light`.
- ANSI-16 maps accent and accent text both to red (bold distinguishes).
- prompt_toolkit must own the heavy box live; `input_frame()` is the static form.

## To accept
1. Pick Rule, Canopy or Rail (or keep them behind `DS_UI=rail|canopy|rule`).
2. Rename `code/ui_style.py` → `src/ds_next/ui_style_rule.py`; port `render()`, `widgets.form()`, `_prompt_approval()` to `turn_rule()/tool()/result()/dialog()/status_row()`.
3. Move this folder to `docs/design-system-rule/` and record the acceptance here.
