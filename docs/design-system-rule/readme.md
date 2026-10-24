# Rule — ds-next terminal design system (Modernist direction)

The Modernist design system translated to a terminal: ink on ground, one red, heavy square rules, a numbered rule per turn, flush-left labels, nothing rounded. Same hybrid shape as Canopy (append-only transcript + pinned footing), different grammar. Independent of Rail and Canopy; never mixed on one screen.

## Principles
1. **The grid shows.** Col 1 glyphs, col 3 speech/tools, col 5 results; label column 12.
2. **Rules divide.** `━━ 03 ━━━…` before every prompt; turns are addressable.
3. **One red, and it means you.** Prompt, agent square, focused option, warning, failure. Done is ink.
4. **Nothing rounded.** Heavy square frames; ■ ▪ ▫ □ markers; a quadrant spinner.
5. **Flush left, always.** Titles at the left end of a rule; labels at the left of their column.
6. **The footing never moves.** Heavy box + bare status row, redrawn in place.
7. **Thinking is quiet.** Dim with a · lead; folds to `· Thought for 3s  ctrl-o`. No italics.
8. **Facts, not sentences.** `+14 −1`, `3 tools  15.2s  $0.0041`; two spaces between facts.

## Colour (dark / light · Modernist token)
bg #201e1d / #f3f2f2 (text / bg) · surface #2d2b2b / #eae9e9 (neutral-900 / surface) · text #f3f2f2 / #201e1d · muted #bab6b6 / #605d5d (neutral-400 / 700) · dim #7d7979 / #9b9797 (neutral-600 / 500) · rule #9b9797 / #605d5d (neutral-500 / 700) · accent #ff563c / #ec3013 (accent-500 / accent) · accent text #ff9783 / #ae1800 (accent-400 / 700). ANSI-16: accent → red, accent text → bold red.

## Glyphs
› prompt · ■ agent / focus · ▪ tool · ▫ running · □ option · └ result / fold · · thinking · ✓ ⚠ ✗ outcome · ━ ┃ ┏ ┓ ┗ ┛ heavy rule/frame · ‹ › choice. Spinner ▖▘▝▗ at 160 ms.

## Case
Frame titles, banner word-mark (DS-NEXT), form labels: uppercase. Flow text lowercase. No italics anywhere.

## Mascot
A canoe in ink with a red paddle and red water, 28×20 px (`assets/mascot.txt`). Two inks only, like the system.

## Files
- `tokens.json`, `tokens/colors.css` (`--rl-*`)
- `code/ui_style.py` — Rich + prompt_toolkit (`turn_rule`, `tool`, `result`, `thinking`, `thought`, `outcome`, `facts`, `dialog`, `input_frame`, `status_row`, `popup_rows`, `banner`, `VERBS`)
- `components/terminal/rule.{jsx,d.ts,prompt.md}`
- `pages/` — spec + screens (need `support.js` and `_ds/` beside them for the Modernist doc chrome)
- `gen/lib.js` — page generator
- `pages/_ds/` — the Modernist stylesheet the pages load, so they open from disk
- `chats/` — the Claude Design transcripts that produced Rail, Canopy and Rule
- `rule-cli/` — the reference CLI: the whole spec as source (`rule_cli/spec.py`), a tour of every section, the seven screens in dark and light, a live demo session, and `rule-cli html` for reading the tour on a phone. Its `README.md` lists where it departs from `code/ui_style.py` (frame widths, combined styles, rows past 80 columns).

## Status
Rule is a candidate direction, not yet accepted; Rail (`../design-system/`) is what ships. See `ACCEPTED.md`.
