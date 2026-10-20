# Terminal components

Nineteen primitives, one per message type: Term, Line, You, Agent, Run, Result, Status, Footer,
Outcome, Labelled, Hint, ErrorLine, Key, Frame, Mascot, Banner, Prompt, Toolbar, Menu. Each
`*.prompt.md` here is the one-paragraph spec an agent reads before composing an HTML mock.

The React sources (`*.jsx`, `*.d.ts`), the compiled `_ds_bundle.js`, `terminal.card.html` and the
`ui_kits/terminal/index.html` session screen live in the Claude Design project
(https://claude.ai/design/p/81fef9af-a683-4f05-a370-344af3d1ea9e) and are read from there with the
DesignSync tool; they are not needed to build a terminal in Python, which goes through
`canon_lib.ui_style` instead.
