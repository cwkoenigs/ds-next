# Keeping rule/ and the Claude Design project in step

Source of truth for design decisions: the design project pages `Rule Terminal Design System` and `Rule Screens`, and the Modernist design system they derive from. Source of truth for behaviour: `code/ui_style.py` once ported.

| File | Role | Edited in |
| --- | --- | --- |
| `tokens.json` | roles (with their Modernist token names), glyphs, grid, motion, verbs, mascot | here; mirrored into `tokens/colors.css`, `code/ui_style.py`, `rule.jsx` |
| `tokens/colors.css` | `--rl-*` custom properties | here |
| `gen/lib.js` | page generator (80-col padding, heavy frames, mascot) | the design project |
| `pages/*.dc.html` | spec + screens | re-exported from the design project |
| `components/terminal/rule.*` | React primitives + contract + usage | the design project |
| `code/ui_style.py` | Rich + prompt_toolkit implementation | `src/ds_next/` after acceptance |

## Re-sync
1. If Modernist's ramps change, re-derive `color.dark/light` from the `color.modernist` map in `tokens.json`.
2. Regenerate pages; replace this folder wholesale; keep `SYNC.md`.
3. Diff `tokens.json` ↔ `PALETTE`, `G`, `VERBS`, `MASCOT` ↔ `rule.jsx` `INK`/`MAP`.

## Checks
- `python -c "import json; json.load(open('tokens.json'))"`
- Every hex in `tokens.json` exists in Modernist's `styles.css` ramps.
- `MASCOT` identical in `assets/mascot.txt`, `ui_style.py`, `rule.jsx`, `gen/lib.js`.
