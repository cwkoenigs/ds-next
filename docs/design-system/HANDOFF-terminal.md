# Wiring the design system into ds-next

Reference: `ds-next Screens.dc.html` (1a–1h) · tokens: `ui_style.py` → copy to `src/ds_next/ui_style.py`.

Three files change. Diffs are against the current `ui.py`, `widgets.py`, `cli.py`. Nothing in
`agent.py`, `kb.py`, `reconcile.py`, `scaffold.py` moves.

One honest limit: prompt_toolkit's `PromptSession` can't draw a closed frame *around* a line
you're still typing. The prompt gets the top rule with the session tag and `│ › `; the bottom
rule is the toolbar band. A fully framed prompt needs the form's `Application` approach — phase 2.

---

## 1 · ui.py

### Imports and constants

```diff
-from rich.console import Console, Group
+from rich.console import Console
 from rich.markdown import Markdown
-from rich.panel import Panel
 from rich.table import Table
 from rich.text import Text
+from prompt_toolkit.styles import Style
 
 from . import __version__, docs, reconcile, scaffold
+from . import ui_style as S
+from .ui_style import G, LABEL_W
 ...
-ACCENT = "#d97757"        # the Claude Code orange
-DIM = "grey50"
```

### Rendering

```diff
-def _bullet(body, style: str = "white") -> Table:
-    t = Table.grid(padding=(0, 1))
-    ...
-    return t
+# _bullet is gone: agent text → S.agent_lines, tool calls → S.run, outcomes → S.outcome
```

```diff
 def render(console: Console, msg: Any, state: dict) -> None:
     if isinstance(msg, AssistantMessage):
         for b in msg.content:
             if isinstance(b, TextBlock) and b.text.strip():
-                console.print(_bullet(Markdown(b.text.strip())))
+                S.agent_lines(console, Markdown(b.text.strip()))
                 state["asked"] = asks(b.text)
             elif isinstance(b, ThinkingBlock):
                 state["step"] = "Thinking"
             elif isinstance(b, ToolUseBlock):
                 state["step"] = f"Running {_short(b.name)}"
                 state.setdefault("tools", {})[b.id] = b.name
-                head = Text(_short(b.name), style="bold")
-                arg = _arg_summary(b.input)
-                if arg:
-                    head.append(f"({arg})")
-                console.print(_bullet(head, style="green"))
+                console.print(S.run(_short(b.name), _arg_summary(b.input)))
     elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
         for b in msg.content:
             if isinstance(b, ToolResultBlock):
                 state["step"] = "Thinking"
                 text = _result_text(b)
                 lines = text.splitlines() or ["(no output)"]
-                more = f" … +{len(lines) - 1} lines" if len(lines) > 1 else ""
-                style = "red" if b.is_error or text.startswith("ERROR:") else DIM
-                console.print(Text(f"  ⎿  {lines[0][:100]}{more}", style=style))
+                state["last_result"] = text          # /last and ctrl-o read this
+                console.print(S.result(lines[0][:72], more=len(lines) - 1,
+                                       error=b.is_error or text.startswith("ERROR:")))
     elif isinstance(msg, SystemMessage) and msg.subtype == "init":
         state["model"] = msg.data.get("model")
     elif isinstance(msg, ResultMessage):
         secs = msg.duration_ms / 1000
-        parts = [f"{msg.num_turns} turn{'s' if msg.num_turns != 1 else ''}", f"{secs:.1f}s"]
+        n = state.get("turn_no", 1)
+        parts = [f"#{n}", f"{msg.num_turns} tool call{'s' if msg.num_turns != 1 else ''}", f"{secs:.1f}s"]
         if msg.total_cost_usd:
             parts.append(f"${msg.total_cost_usd:.4f}")
         if msg.is_error or msg.subtype != "success":
-            console.print(Text(f"  ⎿  {msg.subtype}: {'; '.join(msg.errors or [])}", style="red"))
-        console.print(Text("  " + " · ".join(parts), style=DIM))
+            console.print(S.result(f"{msg.subtype}: {'; '.join(msg.errors or [])}", error=True))
+        console.print(S.footer(*parts))
```

### Approver — the diff in the approval frame

`Approver` keeps its logic; it hands `changed` rows to the prompt instead of a prose string.

```diff
-                detail = "Changed from your form:\n" + "\n".join(
-                    f"  {k}: {self.draft.get(k, '')!r} → {args.get(k, '')!r}"
-                    for k in changed_keys(self.draft, args)) + "\n\n" + detail
+                changed = [(k, str(self.draft.get(k, "")), str(args.get(k, "")))
+                           for k in changed_keys(self.draft, args)]
+                detail = json.dumps({k: v for k, v in args.items() if k not in dict.fromkeys(c[0] for c in changed)})
+                self._changed = changed
```

and `_prompt_approval` reads `self.approver._changed` (or pass it through `ask`'s signature — cleaner:
`ask(title, detail, changed)`; update the `Callable` type accordingly).

### Repl.__init__

```diff
-        self.console = Console(highlight=False)
+        self.console = S.console()
+        self.turn_no = 0
 ...
         self.session = PromptSession(
             history=FileHistory(str(home / "history")),
             completer=SlashCompleter(...),
             complete_while_typing=True,
             bottom_toolbar=self._toolbar,
+            style=Style.from_dict(S.pt_style()),
+            reserve_space_for_menu=8,
         )
```

### Banner, toolbar, prompt

```diff
     def banner(self) -> None:
         shell = "found" if docs_shell_path() else "not found"
-        body = Group(...)
-        self.console.print(Panel(body, border_style=ACCENT, expand=False, padding=(0, 2)))
-        self.console.print()
+        facts = [("cwd", _tilde(self.cwd, 40)),
+                 ("canon", f"{len(self.canon.standards)} standards · {len(self.canon.scaffolds)} scaffolds"),
+                 ("skills", f"{len(self.skills.all)} from skills-os"),
+                 ("docs", f"docs-ds {shell}"),
+                 ("model", f"{self.agent.model or 'auto'} · effort {self.agent.effort or 'default'}")]
+        for line in S.banner(f"v{__version__}", facts,
+                             ["/new starts a project · /help lists commands", "ctrl-d leaves"],
+                             _tilde(self.canon.root, 60), "start, check and grow",
+                             w=S.width(self.console)):
+            self.console.print(line)
+        self.console.print()

     def _toolbar(self):
-        where = self._where
-        model = ...
-        return HTML(...)
+        model = self.state.get("model") or self.agent.model or "auto"
+        left = f"{self.cwd.name} · {self._where} · {model} · {self.agent.effort or 'default'} · " \
+               f"{'connected' if self.agent.connected else 'idle'}"
+        return S.toolbar(left, f"#{self.turn_no}", get_app().output.get_size().columns)
```

Prompt message (in `run()`): the top rule carries the session tag; `│ › ` is the input row.

```diff
-                    line = await self.session.prompt_async(HTML(f'<style fg="{ACCENT}">›</style> '))
+                    cols = S.width(self.console)
+                    tag = " New session " if self.turn_no == 0 else f" #{self.turn_no + 1} "
+                    top = "┌" + "─" * (cols - 3 - len(tag)) 
+                    line = await self.session.prompt_async([
+                        ("class:rule", top), ("class:band", tag), ("class:rule", "─┐\n"),
+                        ("class:rule", "│ "), ("class:prompt", G.prompt + " ")])
```

(`from prompt_toolkit.application import get_app` for the toolbar width.)

### Approval prompt

```diff
-    async def _prompt_approval(self, title: str, detail: str) -> str:
+    async def _prompt_approval(self, title: str, detail: str, changed=()) -> str:
         if self._status:
             self._status.stop()
         try:
-            self.console.print(Panel(Text(detail or "(no input)"), title=..., border_style="yellow", expand=False))
-            return await PromptSession().prompt_async(HTML("  Allow? <b>y</b>es · ..."))
+            rows: list[Text | None] = []
+            for k, before, after in changed:
+                rows.append(S.labelled(k, Text(f"− {before}", style="err"), indent=0))
+                rows.append(S.labelled("", Text(f"+ {after}", style="ok"), indent=0))
+            for ln in (detail or "(no input)").splitlines()[:6]:
+                rows.append(Text(ln, style="muted"))
+            head = Text.assemble((f"Allow {title}?", "warn bold"),
+                                 (" · changed from your form", "dim") if changed else "")
+            keys = Text.assemble((" y ", "key"), (" yes · ", "dim"), ("a", "bold"), (" always this session · ", "dim"),
+                                 ("n", "bold"), (" no", "dim"))
+            self.console.print(Text(G.rail, style="rule"))
+            for line in S.frame(head, rows, kind="approval", keys=keys, w=S.width(self.console),
+                                prefix=Text(G.rail + " ", style="rule")):
+                self.console.print(line)
+            return await PromptSession(style=Style.from_dict(S.pt_style())).prompt_async(
+                [("class:rule", G.rail + "   "), ("class:prompt", G.prompt + " ")])
```

### Local commands

```diff
     def cmd_help(self, _: str) -> None:
-        t = Table(box=None, show_header=False, padding=(0, 2))
-        for c, d in COMMANDS.items():
-            t.add_row(Text(c, style=ACCENT), d)
-        ...
-        self.console.print(t)
+        for c, d in COMMANDS.items():
+            self.console.print(Text.assemble("  ", (f"{c:<22}", "bold"), (d, "muted")))
+        self.console.print(Text.assemble("  ", ("/<skill>              ", "bold"), ("run a skills-os skill", "muted")))
+        self.console.print(S.hint("ctrl-o open last fold · ctrl-c interrupt · ctrl-d leave"))

     def cmd_canon(self, arg: str) -> None:
         if arg in self.canon.standards:
             s = self.canon.standards[arg]
-            self.console.print(Panel(Markdown(self.canon.read(arg)), title=..., border_style=DIM))
+            self.console.print(S.outcome("ok", s.id, f"v{s.version} · {s.status}"))
+            S.agent_lines(self.console, Markdown(self.canon.read(arg)))   # reading is quoting: same rail
             return
         ...
-        t = Table(box=None, padding=(0, 2), header_style=DIM)
-        for col in ("id", "v", "applies to", "status", "title"): t.add_column(col)
-        for s in stds:
-            t.add_row(Text(s.id, style=ACCENT), str(s.version), ",".join(s.applies_to), s.status, s.title)
-        self.console.print(t)
+        repo = reconcile.find_repo(self.cwd)
+        rep = reconcile.check(repo, self.canon) if repo else None
+        self.console.print(Text(f"  {'standard':<18}{'v':<4}{'applies to':<20}this project", style="dim"))
+        for s in stds:
+            mark = _adoption_mark(s, rep)      # ("ok","✓") | ("warn","⚠ v1 → v2") | ("dim","○ pending") | ("dim","")
+            self.console.print(Text.assemble("  ", (f"{s.id:<18}", "bold"), (f"{s.version:<4}", "muted"),
+                                             f"{', '.join(s.applies_to):<20}", mark))

     def cmd_status(self, _: str) -> None:
         repo = reconcile.find_repo(self.cwd)
         if repo is None:
-            self.console.print(Text("Not a ds repo. /new creates one.", style=DIM))
+            self.console.print(S.hint("not a ds repo · /new creates one"))
             return
         r = reconcile.check(repo, self.canon)
-        style = "green" if r.ok and not r.pending else ("yellow" if r.ok else "red")
-        self.console.print(_bullet(Text(r.summary(), style="bold"), style=style))
-        for p in r.pending: ...
+        kind = "ok" if r.ok and not r.pending else ("warn" if r.ok else "err")
+        self.console.print(S.outcome(kind, repo.name, r.summary()))
+        for p in r.pending:
+            self.console.print(S.labelled("pending", Text.assemble((p, "bold"), (" · new", "muted"))))
+        for sid, why in r.declined.items():
+            self.console.print(S.labelled("declined", Text.assemble((sid, "bold"), (f" · {why}", "muted"))))
+        for e in r.errors:
+            for line in S.error(e):
+                self.console.print(line)
```

`cmd_new`: the "Scaffold …" bullet and the draft summary become one line and the label column:

```diff
-        self.console.print(_bullet(Text.assemble(("Scaffold ", ""), (sc.id, "bold"), ...), style="green"))
-        shown = Text(); ... self.console.print(_bullet(shown))
+        self.console.print(S.outcome("ok", sc.id, f"v{sc.version} · {a.name} · {a.purpose}"))
```

(The form already showed name/purpose/owner; repeating them was the "double summary" in the baseline.)

### The turn

```diff
-        def label() -> str:
-            secs = int(time.monotonic() - started)
-            return f"[{ACCENT}]✻[/] {self.state['step']}… [{DIM}]{secs}s · ctrl-c to interrupt[/]"
-        self._status = self.console.status(label(), spinner="dots", spinner_style=ACCENT)
+        self.turn_no += 1
+        self.state["turn_no"] = self.turn_no
+        self.console.print(Text(f"#{self.turn_no}", style="dim"))
+        def label() -> str:
+            return S.status_label(self.state["step"], int(time.monotonic() - started))
+        self._status = self.console.status(label(), spinner=S.SPINNER, spinner_style="accent")
 ...
         except TurnStalled as e:
-            self.console.print(Text(f"  ⎿  {e}", style="yellow"))
+            self.console.print(S.result(str(e), error=True))
         except CortexCodeSDKError as e:
-            self.console.print(Text(f"Cortex Code: {e}", style="red"))
+            for line in S.error(f"Cortex Code refused: {e}", "the draft is kept · retry, or /clear"):
+                self.console.print(line)
 ...
         if interrupted:
-            self.console.print(Text("  ⎿  Interrupted by user", style="red"))
+            self.console.print(S.result(f"interrupted after {int(time.monotonic() - started)}s · session kept", error=True))
+            self.console.print(S.footer(f"#{self.turn_no}"))
```

### Messages in `handle` / `run`

```diff
-            self.console.print(Text("  Type a message, or / for commands. /new starts a project.", style=DIM))
+            self.console.print(S.hint("type a message, or / for commands · /new starts a project"))
...
-            self.console.print(Text(f"Unknown command {cmd}. /help lists them.", style="red"))
+            near = difflib.get_close_matches(cmd, [*COMMANDS, *(f"/{n}" for n in self.skills.all)], 1)
+            for line in S.error(f"{cmd} is not a command", "/help lists them" + (f" · did you mean {near[0]}?" if near else "")):
+                self.console.print(line)
...
-                    self.console.print(Text("  ctrl-c again to leave, or /exit", style=DIM))
+                    self.console.print(S.hint("ctrl-c again to leave · or /exit"))
```

Add `/last` to `COMMANDS` and:

```python
def cmd_last(self, _: str) -> None:
    text = self.state.get("last_result")
    if not text:
        self.console.print(S.hint("no tool output yet")); return
    for ln in text.splitlines():
        self.console.print(Text(" " * 4 + ln, style="muted"))
```

---

## 2 · widgets.py

```diff
-ACCENT = "#d97757"
-STYLE = Style.from_dict({...})
+from prompt_toolkit.widgets import Frame, TextArea
+from . import ui_style as S
+from .ui_style import G, LABEL_W
+STYLE = Style.from_dict(S.pt_style())
```

Form: labels on the 12-column grid, the frame from prompt_toolkit's own `Frame` (square corners),
the submit key as the one band in the footer.

```diff
     def label(f: Field):
         def get():
             on = get_app().layout.has_focus(areas[f.key])
             mark = "*" if f.required else " "
-            return FormattedText([("class:focus" if on else "class:label", f" {'❯' if on else ' '} {f.label:<12}{mark} ")])
-        return Window(FormattedTextControl(get), width=17, dont_extend_width=True)
+            return FormattedText([("class:focus" if on else "class:label",
+                                   f"{G.select if on else ' '} {f.label:<{LABEL_W}}{mark} ")])
+        return Window(FormattedTextControl(get), width=LABEL_W + 4, dont_extend_width=True)
```

```diff
-        parts.append(("class:dim", f"   {keys}Tab/↓ next · ↑ back · Enter submit · Esc cancel"))
+        parts.append(("class:dim", f"   {keys}Tab next · ↑ back · "))
+        parts.append(("class:key", " Enter submit "))
+        parts.append(("class:dim", " · Esc cancel"))
```

```diff
-    rows = [Window(FormattedTextControl(FormattedText([("class:title", f" {title}\n")])), height=2)]
-    rows += [VSplit([label(f), areas[f.key]]) for f in fields]
+    rows = [VSplit([label(f), areas[f.key]]) for f in fields]
     rows.append(Window(FormattedTextControl(hint), dont_extend_height=True))
+    body = Frame(HSplit(rows), title=title, style="class:frame.border")
     first = order[0]
-    app = Application(layout=Layout(HSplit(rows), focused_element=first), ...)
+    app = Application(layout=Layout(body, focused_element=first), key_bindings=kb, style=STYLE,
+                      full_screen=False, erase_when_done=True)
```

The `pick` widget keeps its shape; swap `❯` for `G.select` and the key line to the same
`class:dim` / `class:key` pattern. Title in `cmd_new` becomes just `"New project from the canon"` —
the keys line already says what to do.

---

## 3 · cli.py — same grammar, no colour

```diff
-out = Console(highlight=False, markup=False, soft_wrap=True)
+from . import ui_style as S
+out = S.console(color=sys.stdout.isatty(), soft_wrap=True)
```

```diff
 def reconcile(...):
     ...
-        out.print(rep.summary())
-        if rep.outputs: out.print(f"  outputs  {', '.join(rep.outputs)}  (...)")
-        for p in rep.pending: out.print(f"  pending  {p}")
-        for sid, why in rep.declined.items(): out.print(f"  declined {sid}: {why}")
+        kind = "ok" if rep.ok and not rep.pending else ("warn" if rep.ok else "err")
+        out.print(S.outcome(kind, repo.name, rep.summary()))
+        if rep.outputs:
+            out.print(S.labelled("outputs", ", ".join(rep.outputs)))
+        for p in rep.pending:
+            out.print(S.labelled("pending", p))
+        for sid, why in rep.declined.items():
+            out.print(S.labelled("declined", f"{sid} · {why}"))
+        if rep.pending:
+            out.print(S.hint("run ds-next reconcile --accept to adopt, or /reconcile in the terminal"))
     for e in rep.errors:
-        out.print(f"  error    {e}", style="red")
+        for line in S.error(e):
+            out.print(line)
```

```diff
 def canon_list(...):
     for s in ...:
-        out.print(f"{s.id:22} v{s.version}  {s.title}")
+        out.print(Text.assemble(("  "), (f"{s.id:<18}", "bold"), (f"{s.version:<4}", "muted"),
+                                f"{', '.join(s.applies_to):<20}", (s.title, "muted")))
```

Every `style="red"` in `cli.py` → `S.error(...)`; every `style="yellow"` → `S.outcome("warn", …)`.
When stdout isn't a TTY `S.console(color=False)` drops colour and keeps the glyphs (1g).

---

## Order of work

1. Copy `ui_style.py` in; run the terminal — nothing changes yet.
2. `render()` + the turn (rail, status, footer). Biggest visible win, no behaviour change.
3. Banner, prompt rule, toolbar, completion-menu style.
4. Approval frame with the diff; `/last` + `last_result`.
5. Form: labels, `Frame`, key band.
6. Local commands and `cli.py`.

Checks: `DS_THEME=light ds-next` reads on a light terminal; `COLORTERM= ds-next` falls back to
ANSI-16; `ds-next reconcile | cat` prints glyphs with no escape codes; every frame is exactly 80
columns at `COLUMNS=80` and shrinks cleanly to 60.
