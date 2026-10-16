"""Two inline widgets in the Claude Code style: a picker and a one-screen form.

Both draw below the prompt (not full screen), erase themselves when done, and return a value,
or None when the user presses Esc or Ctrl-C.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea

ACCENT = "#d97757"
STYLE = Style.from_dict({
    "accent": f"{ACCENT} bold", "dim": "#808080", "error": "#e06c75", "label": "#a0a0a0",
    "focus": f"{ACCENT} bold", "field": "", "title": "bold",
})


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
        out = [("class:title", f" {title}\n\n")]
        for i, (_, label, desc) in enumerate(options):
            on = i == state["i"]
            out += [("class:accent" if on else "", f" {'❯' if on else ' '} {i + 1}. {label}"),
                    ("class:dim", f"  {desc}\n")]
        out.append(("class:dim", "\n ↑↓ move · Enter choose · Esc cancel"))
        return FormattedText(out)

    app = Application(layout=Layout(Window(FormattedTextControl(text), dont_extend_height=True)),
                      key_bindings=kb, style=STYLE, full_screen=False, erase_when_done=True)
    return await app.run_async()


@dataclass
class Field:
    key: str
    label: str
    value: str = ""
    hint: str = ""
    required: bool = False


async def form(title: str, fields: list[Field], footer: Callable[[dict[str, str]], str],
               validate: Callable[[dict[str, str]], tuple[str, str] | None]) -> dict[str, str] | None:
    """Every field on one screen, already filled with a suggestion. Tab/↓ and Shift-Tab/↑ move,
    Enter submits from any field. `validate` returns (field key, message) to refuse a submit;
    `footer` is recomputed on every keystroke."""
    areas = {f.key: TextArea(text=f.value, multiline=False, wrap_lines=False, style="class:field")
             for f in fields}
    order = [areas[f.key] for f in fields]
    error = {"msg": ""}

    def values() -> dict[str, str]:
        return {k: a.text.strip() for k, a in areas.items()}

    def label(f: Field):
        def get():
            on = get_app().layout.has_focus(areas[f.key])
            mark = "*" if f.required else " "
            return FormattedText([("class:focus" if on else "class:label",
                                   f" {'❯' if on else ' '} {f.label:<12}{mark} ")])
        return Window(FormattedTextControl(get), width=17, dont_extend_width=True)

    def hint():
        focused = next((f for f in fields if get_app().layout.has_focus(areas[f.key])), None)
        parts = [("class:dim", f"   {focused.hint}\n" if focused and focused.hint else "\n")]
        parts.append(("class:accent", f"   {footer(values())}\n"))
        if error["msg"]:
            parts.append(("class:error", f"   {error['msg']}\n"))
        parts.append(("class:dim", "   Tab/↓ next · ↑ back · Enter submit · Esc cancel"))
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

    @kb.add("enter")
    def _submit(e):
        v = values()
        missing = next((f for f in fields if f.required and not v[f.key]), None)
        problem = (missing.key, f"{missing.label} is required") if missing else validate(v)
        if problem:
            error["msg"] = problem[1]
            e.app.layout.focus(areas[problem[0]])
            return
        e.app.exit(result=v)

    @kb.add("escape")
    @kb.add("c-c")
    def _cancel(e):
        e.app.exit(result=None)

    rows = [Window(FormattedTextControl(FormattedText([("class:title", f" {title}\n")])), height=2)]
    rows += [VSplit([label(f), areas[f.key]]) for f in fields]
    rows.append(Window(FormattedTextControl(hint), dont_extend_height=True))
    first = next((areas[f.key] for f in fields if f.required and not f.value), order[0])
    app = Application(layout=Layout(HSplit(rows), focused_element=first), key_bindings=kb, style=STYLE,
                      full_screen=False, erase_when_done=True)
    return await app.run_async()
