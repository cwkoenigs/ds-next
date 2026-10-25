# Rule terminal components — usage

Load `../../tokens/colors.css` and `rule.jsx` (after React). Everything is on `window.Rule`.

Compose top-down inside `<Term theme>`: `<TurnRule n>` then `<You>` for every prompt, messages, one blank `<Line> </Line>`, then `<Footing>` last — always.

- One `Line` is one terminal row; never wrap.
- `Agent` children are wrapped lines; the first carries ■ in accent. Markdown headings are `<Heading>` (uppercase bold); inline code is `<Code>`.
- `Tool` + `Result` are adjacent. Results are facts (`+14 −1`, `142 lines`), not sentences.
- `Thinking` with `secs` is the fold; without, children stream with a · lead. No italics.
- `Working` sits above the footing; it is replaced in place by the message it produced.
- Outcomes: `ok` is ink, `warn` red, `err` bold red — red means "needs you".
- `Dialog` replaces `InputBox` (pass as `Footing dialog=`); titles are uppercased; `StatusRow left=` carries the keys.
- Only `Frame` draws lines besides `TurnRule`; both are heavy. Nothing is rounded.
- Facts in a row are separated by two spaces (`Facts items=[…]`), never by ·, except in the status row.

```jsx
<Term theme="light">
  <TurnRule n={2}/><You>add a --since flag</You><Line> </Line>
  <Thinking secs={3}/>
  <Agent>I'll add <b>--since</b> as an ISO date.</Agent><Line> </Line>
  <Tool name="Bash" args="uv run pytest -q"/><Result more={11}>13 passed in 1.42s</Result><Line> </Line>
  <Footing cwd="~/Developer/order-metrics"/>
</Term>
```
