# handoff — code + design pages

`design-system/` holds the current exports of the three design pages (open with `support.js` beside
them, or just drop the folder into `docs/design-system/`). They include the 2a–2d mark options and
the mascot in the 1a banner. `ds_next/` is the code that matches them.

## ds_next — drop-in files

Four complete files that replace `src/ds_next/{ui,widgets,cli}.py` and add `ui_style.py`.
They implement every screen in `ds-next Screens.dc.html` (1a–1h): framed two-pane banner with the
dog & cat, prompt rule with session tag, styled command menu, framed /new form, numbered rail turns,
approval frame with − / + diff, /status · /canon · /help columns, plain CI output, error lines.

    cp handoff/ds_next/*.py  <ds-next>/src/ds_next/

Behaviour is unchanged: same commands, same Approver rules, same form validation, same exit codes.
Additions: `/last` (full output of the last tool call), `#n` turn numbers, `DS_THEME=light`.

`pt_style()` now translates Rich syntax to prompt_toolkit (`on #hex` → `bg:#hex`, ANSI names →
`ansi*`) via `_pt()`, so the live copy and this one can be the same file.

Check after copying:

- `uv run ds-next` — banner, prompt rule, toolbar band; `/` opens the menu with descriptions and kind.
- `/new python cli try-me` — framed form, label column at 12, Enter band in the footer.
- a turn — `#1`, `●` text on the rail, `→` tools, `⎿` folded results, `◐` live line, `╰` footer.
- `/status`, `/canon`, `/help` — flat, no rail, shared label column.
- `uv run ds-next reconcile | cat` — glyphs, no escape codes.
- `COLORTERM= uv run ds-next` — ANSI-16 fallback; `DS_THEME=light` — light ramp.

Known gap (phase 2): the prompt has a top rule and `│ › ` but no bottom rule while typing —
prompt_toolkit's PromptSession can't close a frame around the live input line.
