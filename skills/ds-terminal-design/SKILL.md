---
name: ds-terminal-design
description: >-
  Design or build a terminal interface (a CLI, a REPL, an agent terminal) in the team's style:
  the twelve colour roles, the glyph vocabulary, the 80-column grid, frames that mean "needs you",
  one rail per turn, and the dog-and-cat mascot. Use when the user asks for a CLI, a terminal
  screen, a status or error line, a banner, a form or picker in a terminal, or an HTML mock of one.
  Works for Python (Rich + prompt_toolkit, through canon_lib.ui_style) and for HTML mocks.
---

# Terminal design, the team's way

The design system is the canon standard `terminal-design`; its full package is in the ds-next
checkout at `docs/design-system/export/` (`readme.md` first, then `guidelines/` and
`components/terminal/*.prompt.md`). The pixel reference is `docs/design-system/ds-next Screens.dc.html`.

## Python

Never hard-code a colour or a glyph. Import the tokens and build every line with their helpers:

```python
from canon_lib.ui_style import console, outcome, labelled, hint, error, run, result, footer, frame, banner
out = console(color=sys.stdout.isatty())      # colour on a terminal, plain glyphs in a log
out.print(outcome("ok", "feed-model", "26 adopted · 0 pending"))
```

- `outcome`, `labelled`, `hint`, `error` for a flat command (no rail).
- `agent_lines`, `run`, `result`, `footer`, `status_label` for an agent's turn (one rail).
- `frame` for anything that needs the user; the picker, form and framed prompt are in
  `canon_lib.widgets` (`pick`, `form`, `prompt_line`).
- A new CLI from the `python-cli` project type already does this; in an existing repo,
  `block_add block-ui-style` (and `block-tui-widgets` for widgets).

## Content

Lowercase, terse, no trailing periods on single lines; facts joined with ` · `; imperative hints
(`/new starts a project`); errors name what failed and then the fix, never a stack trace; tool
names bold and exact, arguments muted; no emoji; only the twelve glyphs.

## HTML mocks

Compose the terminal components (`Term`, `You`, `Agent`, `Run`, `Result`, `Frame`, `Banner`,
`Prompt`, `Toolbar`, `Menu`...) from `export/components/terminal/*.prompt.md`, every row one line
tall at 80 columns, with `export/tokens/colors.css` for the roles.

If invoked without other guidance, ask what terminal surface is being built (banner, form, turn,
status, CI output) and whether it is a mock or code, then act as an expert terminal designer.
