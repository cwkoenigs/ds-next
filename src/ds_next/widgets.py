"""Two inline widgets drawn with the ui_style roles: a picker and a one-screen form.

Both draw below the prompt (not full screen), erase themselves when done, and return a value,
or None when the user presses Esc or Ctrl-C. A frame means "needs you".
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import Condition, has_completions, is_done
from prompt_toolkit.layout import ConditionalContainer, HSplit, Layout, ScrollOffsets, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenuControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea

from . import ui_style as S
from .ui_style import G, LABEL_W

STYLE = Style.from_dict(S.pt_style())


def _grid(width: int) -> Dimension:
    """A container's width on the grid: `width` columns when the terminal has them (preferred as
    well as max, or a VSplit shares the slack evenly), what the terminal has when it is narrower."""
    return Dimension(max=width, preferred=width)


def _on_grid(container, width: int | None):
    """Hold a container to its `_grid` width however wide the terminal is: the root container is
    always written at the full width, so the cap only holds inside a VSplit with a filler after
    it (the filler paints nothing). None means the terminal's width."""
    return VSplit([container, Window()]) if width else container


# ── surviving a resize ───────────────────────────────────────────────────────
# prompt_toolkit redraws by moving the cursor relative to where it last was. When the terminal's
# columns change, xterm.js (VS Code's terminal) re-wraps every row that reaches the last column
# and shifts the cursor with it, so the next redraw lands under a ghost of the last one: the
# stacked frames. Cortex Code and Claude Code answer a resize by clearing the screen and the
# scrollback and printing the transcript again; so does every Application here. `repaint` is the
# host's "print everything again", at the new width.
repaint: Callable[[], None] | None = None


def _on_resize(app: Application) -> None:
    out = app.output
    app.renderer.reset()                         # forget the last screen: the next draw is whole
    out.erase_screen()
    out.write_raw("\x1b[3J")                     # and the scrollback, where the ghosts would be
    out.cursor_goto(0, 0)
    out.flush()
    if repaint is not None:
        repaint()
    app._request_absolute_cursor_position()      # the two steps prompt_toolkit's own handler takes
    app._redraw()


def resize_safe(app: Application) -> Application:
    """Give an Application the resize behaviour above. prompt_toolkit 3.0 registers `_on_resize`
    as its SIGWINCH handler when the app runs, so the instance attribute is what gets called."""
    app._on_resize = lambda: _on_resize(app)     # type: ignore[method-assign]
    return app


def _keys(*parts: tuple[str, str]) -> list[tuple[str, str]]:
    """Key line: dim text with the one submit key as a band."""
    return [("class:dim", "  ")] + [(f"class:{cls}", txt) for cls, txt in parts]


async def pick(title: str, options: list[tuple[str, str, str]]) -> str | None:
    """options: (value, label, description). ↑/↓ or a digit to move, Enter to choose."""
    state = {"i": 0}
    kb = KeyBindings()

    @kb.add("up")
    @kb.add("k")
    def _up(e):
        state["i"] = (state["i"] - 1) % len(options)

    @kb.add("down")
    @kb.add("j")
    @kb.add("tab")
    def _down(e):
        state["i"] = (state["i"] + 1) % len(options)

    @kb.add("enter")
    def _enter(e):
        e.app.exit(result=options[state["i"]][0])

    @kb.add("escape")
    @kb.add("c-c")
    def _cancel(e):
        e.app.exit(result=None)

    for n in range(1, min(len(options), 9) + 1):
        @kb.add(str(n))
        def _num(e, n=n):
            state["i"] = n - 1
            e.app.exit(result=options[n - 1][0])

    def text():
        out = []
        for i, (_, label, desc) in enumerate(options):
            on = i == state["i"]
            out += [("class:focus" if on else "class:field", f" {G.select if on else ' '} {i + 1}. {label}"),
                    ("class:muted", f"  {desc}\n")]
        out.append(("", "\n"))
        out += _keys(("dim", "↑↓ move · "), ("key", " Enter choose "), ("dim", " · Esc cancel"))
        return FormattedText(out)

    body = _on_grid(Frame(Window(FormattedTextControl(text), dont_extend_height=True), title=title,
                          style="class:frame.border", width=_grid(S.DESIGN_WIDTH)), S.DESIGN_WIDTH)
    app = resize_safe(Application(layout=Layout(body), key_bindings=kb, style=STYLE, full_screen=False,
                                  erase_when_done=True))
    return await app.run_async()


@dataclass
class Field:
    key: str
    label: str
    value: str = ""
    hint: str = ""
    required: bool = False
    choices: list[tuple[str, str]] | None = None
    example: str = ""
    normalize: Callable[[str], str] | None = None
    check: Callable[[str], str | None] | None = None


async def form(title: str, fields: list[Field], footer: Callable[[dict[str, str]], str],
               validate: Callable[[dict[str, str]], tuple[str, str] | None],
               width: int = S.DESIGN_WIDTH) -> dict[str, str] | None:
    """Every field on one screen, already filled with a suggestion, inside a square frame.
    Tab/↓ and Shift-Tab/↑ move, Enter submits from any field. Labels sit on the LABEL_W grid."""
    chosen = {f.key: max(0, next((i for i, (v, _) in enumerate(f.choices) if v == f.value), 0))
              for f in fields if f.choices}

    def choice_text(f: Field):
        def get():
            on = get_app().layout.has_focus(areas[f.key])
            i = chosen[f.key]
            return FormattedText([("class:strong" if on else "class:field", f"‹ {f.choices[i][1]} ›"),
                                  ("class:dim", f"  {i + 1}/{len(f.choices)}" if on else "")])
        return get

    areas = {}
    for f in fields:
        if f.choices:
            areas[f.key] = Window(FormattedTextControl(choice_text(f), focusable=True), height=1, dont_extend_height=True)
        else:
            areas[f.key] = TextArea(text=f.value, multiline=False, wrap_lines=False, style="class:field")
    order = [areas[f.key] for f in fields]
    error = {"msg": ""}

    def normalizer(f: Field):
        def on_change(buf):
            fixed = f.normalize(buf.text)
            if fixed != buf.text:
                buf.text = fixed
                buf.cursor_position = len(fixed)
        return on_change

    for f in fields:
        if f.normalize and not f.choices:
            areas[f.key].buffer.on_text_changed += normalizer(f)

    def values() -> dict[str, str]:
        return {f.key: (f.choices[chosen[f.key]][0] if f.choices else areas[f.key].text.strip()) for f in fields}

    def focused_choice() -> Field | None:
        return next((f for f in fields if f.choices and get_app().layout.has_focus(areas[f.key])), None)

    def label(f: Field):
        def get():
            on = get_app().layout.has_focus(areas[f.key])
            mark = "*" if f.required else " "
            return FormattedText([("class:focus" if on else "class:label",
                                   f"{G.select if on else ' '} {f.label:<{LABEL_W}}{mark} ")])
        return Window(FormattedTextControl(get), width=LABEL_W + 4, dont_extend_width=True)

    def hint():
        focused = next((f for f in fields if get_app().layout.has_focus(areas[f.key])), None)
        v = values()
        line = ""
        if focused:
            bits = []
            if focused.example and not v[focused.key]:
                bits.append(f"e.g. {focused.example}")
            if focused.hint:
                bits.append(focused.hint)
            line = " · ".join(bits)
        parts = [("class:dim", f"  {line}\n" if line else "\n")]
        parts.append(("class:accent", f"  {footer(v)}\n"))
        live = focused.check(v[focused.key]) if focused and focused.check and v[focused.key] else None
        if live:
            parts.append(("class:error", f"  {G.err} {live}\n"))
        elif error["msg"]:
            parts.append(("class:error", f"  {G.err} {error['msg']}\n"))
        else:
            parts.append(("", "\n"))
        keys = "←/→ change · " if focused_choice() else ""
        parts += _keys(("dim", f"{keys}Tab next · ↑ back · "), ("key", " Enter submit "), ("dim", " · Esc cancel"))
        return FormattedText(parts)

    kb = KeyBindings()

    def move(step: int):
        i = next((n for n, a in enumerate(order) if get_app().layout.has_focus(a)), 0)
        get_app().layout.focus(order[(i + step) % len(order)])

    @kb.add("tab")
    @kb.add("down")
    def _next(e):
        move(1)

    @kb.add("s-tab")
    @kb.add("up")
    def _prev(e):
        move(-1)

    def cycle(step: int):
        f = focused_choice()
        if f is not None:
            chosen[f.key] = (chosen[f.key] + step) % len(f.choices)

    @kb.add("right")
    def _right(e):
        if focused_choice() is not None:
            cycle(1)
        else:
            e.app.current_buffer.cursor_right()

    @kb.add(" ")
    def _space(e):
        if focused_choice() is not None:
            cycle(1)
        else:
            e.app.current_buffer.insert_text(" ")

    @kb.add("left")
    def _left(e):
        if focused_choice() is not None:
            cycle(-1)
        else:
            e.app.current_buffer.cursor_left()

    @kb.add("enter")
    def _submit(e):
        v = values()
        missing = next((f for f in fields if f.required and not v[f.key]), None)
        broken = next(((f.key, f.check(v[f.key])) for f in fields if f.check and v[f.key] and f.check(v[f.key])), None)
        problem = (missing.key, f"{missing.label} is required") if missing else broken or validate(v)
        if problem:
            error["msg"] = problem[1]
            e.app.layout.focus(areas[problem[0]])
            return
        e.app.exit(result=v)

    @kb.add("escape")
    @kb.add("c-c")
    def _cancel(e):
        e.app.exit(result=None)

    rows = [VSplit([label(f), areas[f.key]]) for f in fields]
    rows.append(Window(FormattedTextControl(hint), dont_extend_height=True))
    body = _on_grid(Frame(HSplit(rows), title=title, style="class:frame.border", width=_grid(width)), width)
    app = resize_safe(Application(layout=Layout(body, focused_element=order[0]), key_bindings=kb, style=STYLE,
                                  full_screen=False, erase_when_done=True))
    return await app.run_async()


# ── the prompt: a closed frame around the line you type ──────────────────────
def _cols(width: int | None) -> int:
    """The frame's width: the terminal's, unless one was asked for (tests, pipes)."""
    if width:
        return width
    try:
        return get_app().output.get_size().columns
    except Exception:  # noqa: BLE001 - outside an application there is no size
        return S.DESIGN_WIDTH


def prompt_frame(tag: str, text: str, width: int) -> list[tuple[str, str]]:
    """The three static rows of a prompt frame, as prompt_toolkit fragments: what `prompt_line`
    draws live, and what the caller reprints once the line is accepted. Cortex Code's box: the
    terminal's width, rounded corners, the session tag at the right of the top rule."""
    t = f" {tag} "
    inner = width - 2
    body = f"{G.prompt} {text}"[: inner - 1]
    return [("class:rule", "╭" + "─" * (width - 4 - len(t))), ("class:band", t), ("class:rule", "──╮\n"),
            ("class:rule", "│ "), ("class:prompt", body), ("", " " * (inner - 1 - len(body))), ("class:rule", "│\n"),
            ("class:rule", "╰" + "─" * inner + "╯")]


async def prompt_line(tag: str, *, completer=None, history=None, toolbar: Callable[[], list] | None = None,
                      width: int | None = None) -> str:
    """One line of input inside a closed frame the width of the terminal, the session tag on its
    top rule, the status band under it, the `/` menu dropping below, ↑↓ for history (or the menu
    when it is open), Tab to complete, Enter to accept. Raises KeyboardInterrupt on ctrl-c and
    EOFError on ctrl-d with an empty line. The frame erases itself; the caller reprints it with
    the accepted text (`prompt_frame`). `width` pins the frame (tests); None follows the terminal,
    so a resize redraws it to fit."""
    area = TextArea(multiline=False, wrap_lines=False, completer=completer, complete_while_typing=True,
                    history=history, style="class:field", prompt=[("class:prompt", G.prompt + " ")])
    buf = area.buffer
    t = f" {tag} "

    def top():
        return FormattedText([("class:rule", "╭" + "─" * (_cols(width) - 4 - len(t))), ("class:band", t),
                              ("class:rule", "──╮")])

    def bottom():
        return FormattedText([("class:rule", "╰" + "─" * (_cols(width) - 2) + "╯")])

    def menu_height():                                            # as tall as its items, 8 at most
        n = len(buf.complete_state.completions) if buf.complete_state else 0
        return Dimension.exact(min(8, max(1, n)))

    menu = ConditionalContainer(Window(CompletionsMenuControl(), height=menu_height, width=Dimension(min=8),
                                       dont_extend_width=True, scroll_offsets=ScrollOffsets(top=1, bottom=1)),
                                filter=has_completions & ~is_done)
    rows = [Window(FormattedTextControl(top), height=1),
            VSplit([Window(FormattedTextControl(FormattedText([("class:rule", "│ ")])), width=2, dont_extend_width=True),
                    area,
                    Window(FormattedTextControl(FormattedText([("class:rule", "│")])), width=1, dont_extend_width=True)]),
            Window(FormattedTextControl(bottom), height=1),
            VSplit([Window(width=2), menu])]                       # the menu drops below the box
    if toolbar is not None:
        rows.append(Window(FormattedTextControl(lambda: FormattedText(toolbar())), height=1, style="class:bottom-toolbar"))
    body = _on_grid(HSplit(rows, width=_grid(width) if width else None), width)
    kb = KeyBindings()
    menu_open = Condition(lambda: buf.complete_state is not None)

    @kb.add("enter")
    def _enter(e):
        cs = buf.complete_state
        if cs is not None and cs.current_completion is not None:
            buf.apply_completion(cs.current_completion)     # take the highlighted completion, then accept
        e.app.exit(result=buf.text)

    @kb.add("tab")
    def _tab(e):
        if buf.complete_state is None:
            buf.start_completion(select_first=True)
        else:
            buf.complete_next()

    @kb.add("s-tab", filter=menu_open)
    def _stab(e):
        buf.complete_previous()

    @kb.add("up")
    def _up(e):
        buf.auto_up()

    @kb.add("down")
    def _down(e):
        buf.auto_down()

    @kb.add("escape", filter=menu_open)
    def _close(e):
        buf.complete_state = None

    @kb.add("c-c")
    def _interrupt(e):
        e.app.exit(exception=KeyboardInterrupt())

    @kb.add("c-d")
    def _eof(e):
        if not buf.text:
            e.app.exit(exception=EOFError())

    app = resize_safe(Application(layout=Layout(body, focused_element=area), key_bindings=kb, style=STYLE,
                                  full_screen=False, erase_when_done=True))
    return await app.run_async()
