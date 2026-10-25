# rule-cli

A sample CLI built on **Rule**, the ds-next terminal design system in the Modernist direction. The whole spec is in the source, and the CLI walks through every part of it.

The design pages are `../pages/Rule Terminal Design System.dc.html` and `../pages/Rule Screens.dc.html`, from the Claude Design export.

```sh
uv pip install -e .         # needs Python 3.10+, installs rich into the nearest .venv (the repo root's)
source ../../../.venv/bin/activate   # puts rule-cli on your PATH (Windows: ..\..\..\.venv\Scripts\activate)
rule-cli                    # the tour: every section, enter between chapters
rule-cli chapters           # list the 19 chapters
rule-cli tour -c 3          # one chapter (3 = colour roles)
rule-cli screen 5           # one of the seven screens, dark and light
rule-cli screen             # all seven
rule-cli spec --json        # the spec as data
rule-cli html -o tour.html  # the tour as one web page, readable on a phone
rule-cli demo               # a live session: type a request, /status, /new, /help, ctrl-d leaves
```

Options: `--theme dark|light` sets the theme for the prose and the demo. `--color truecolor|ansi16` forces the colour depth (otherwise it's read from `$COLORTERM`). `--one-theme` shows each mockup only once, instead of in dark and light. Mockups are painted on their theme's own ground, so a light screen still reads in a dark terminal.

## What's where

| File | Holds |
|---|---|
| `rule_cli/spec.py` | The spec as data: assumptions, the differences from Canopy, 8 principles, 8 colour roles with Modernist tokens, ANSI-16, glyphs, grid, case, motion, spinner verbs, mascot, code map, screens, known gaps |
| `rule_cli/ui_style.py` | The design's own `rule/code/ui_style.py` (palette, glyphs, grid, builders, frames, banner, mascot), with the fixes listed below |
| `rule_cli/screens.py` | The seven screens and the spec page's mockups (1b, 5a, 6, 7), built from those helpers |
| `rule_cli/tour.py` | The walkthrough, plus the live motion demo (quadrant spinner, thinking that folds, tools that land in place) |
| `rule_cli/cli.py` | The `rule-cli` commands and the interactive demo |

## Departures from the design files

- **`frame()` widths.** In `ui_style.py`, titled frames came out at 79 columns and frame rows at 79. The mockups show the same off-by-one (`BASH COMMAND`, `NEW PROJECT…`, the banner top). Every frame is now exactly 80.
- **Combined style names.** Rich looks a style name up whole, so `"muted bold"` and the mascot's `"text on_accent"` rendered unstyled. They are now registered in `theme()` (`COMBOS`).
- **Rows past 80 columns.** The banner tagline (33 columns in a 30-column pane) and two `/status` rows (83 columns) overflowed in the mockups. The tagline now sits on its own row under `DS-NEXT`. The `/status` values wrap at the value column (col 16).
- **Canopy in chapter 1.** Only Rule's side of the comparison is drawn. Canopy is described as a list of changes, since it's a different system.

`pytest` checks that every row fits in 80 columns and every frame is exactly 80, that the combined styles resolve, that the spec JSON is complete, and that the tour runs every chapter.
