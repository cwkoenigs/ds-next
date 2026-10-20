---
name: ds-next-terminal-design
description: Use this skill to design or build terminal interfaces (CLIs, REPLs, agent terminals) in the ds-next style — colour roles, glyph vocabulary, the 80-column grid, frames, the rail, and the dog-and-cat mascot. Works for HTML mocks and for Python (Rich + prompt_toolkit) code.
user-invocable: true
---

Read readme.md within this skill, then guidelines/ and components/terminal/*.prompt.md.
For HTML mocks compose the terminal components (Term, Agent, Run, Result, Frame, Banner, Prompt …) and keep every row one line tall at 80 columns.
For Python, copy handoff/ds_next/ui_style.py and build lines with its helpers (agent_lines, run, result, outcome, frame, banner); never hard-code colours or glyphs.
If invoked without other guidance, ask what terminal surface is being built (banner, form, turn, status, CI output) and whether it is a mock or code, then act as an expert terminal designer.
