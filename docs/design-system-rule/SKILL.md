---
name: ds-next-rule-terminal-design
description: Use this skill to design or build terminal interfaces in the ds-next Rule style — the Modernist direction: ink on ground with one red, heavy square rules, a numbered rule per turn, pinned square input box, ■/▪ squares, └ results, numbered dialogs, canoe mascot. Independent of Rail and Canopy; never mix.
user-invocable: true
---

Read readme.md in this skill, then components/terminal/rule.prompt.md.
For HTML mocks compose window.Rule primitives (Term, TurnRule, You, Agent, Tool, Result, Thinking, Working, Dialog, Footing …): one row per line, 80 columns, a TurnRule before every You, Footing last.
For Python, copy code/ui_style.py and build with its helpers; never hard-code colours or glyphs; red only where the user is needed.
If invoked without other guidance, ask what terminal surface is being built and whether it is a mock or code, then act as an expert terminal designer.
