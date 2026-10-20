"""The picker and the form, driven by real keystrokes through a pipe."""
import asyncio

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from ds_next.widgets import Field, form, pick, prompt_frame, prompt_line


class _Interrupted(Exception):
    """ctrl-c inside the task, carried out as a plain exception: asyncio re-raises a
    KeyboardInterrupt straight out of the loop and leaves the task's exception unretrieved."""


def drive(coro_fn, keys: str):
    async def go():
        with create_pipe_input() as inp, create_app_session(input=inp, output=DummyOutput()):
            async def run():
                try:
                    return await coro_fn()
                except KeyboardInterrupt as e:
                    raise _Interrupted from e

            task = asyncio.ensure_future(run())
            await asyncio.sleep(0.1)
            for ch in keys:                       # one key at a time, as a person types
                inp.send_text(ch)
                await asyncio.sleep(0.01)
            return await asyncio.wait_for(task, 3)
    try:
        return asyncio.run(go())
    except _Interrupted as e:
        raise KeyboardInterrupt from e


def FIELDS():
    return [Field("name", "name", "", required=True), Field("purpose", "purpose", "", required=True),
            Field("owner", "owner", "ck")]


def make_form(seen):
    return lambda: form("t", FIELDS(), lambda v: "n standards", lambda v: seen.append(v) or None)


def test_form_tab_through_and_enter_submits():
    seen = []
    out = drive(make_form(seen), "my-cli\tdoes things\r")
    assert out == {"name": "my-cli", "purpose": "does things", "owner": "ck"}


def test_form_refuses_missing_required_and_jumps_there():
    out = drive(make_form([]), "my-cli\r" "pulls orders\r")   # first Enter: purpose missing, focus moves there
    assert out == {"name": "my-cli", "purpose": "pulls orders", "owner": "ck"}


def test_form_validate_can_refuse():
    calls = []

    def validate(v):
        calls.append(v)
        return ("name", "taken") if len(calls) == 1 else None

    out = drive(lambda: form("t", FIELDS(), lambda v: "", validate), "a-b\tc\r" "\x7f\x7fxy\r")
    assert out["name"] == "axy" and len(calls) == 2      # refused, focus back on name, edited, accepted


def test_form_escape_cancels():
    assert drive(make_form([]), "abc\x1b") is None


def test_pick_arrows_and_enter():
    opts = [("a", "A", ""), ("b", "B", ""), ("c", "C", "")]
    assert drive(lambda: pick("t", opts), "\x1b[B\x1b[B\r") == "c"
    assert drive(lambda: pick("t", opts), "2") == "b"


def test_form_choice_field_cycles_with_arrows_and_space():
    fields = lambda: [Field("type", "type", "cli", choices=[("cli", "CLI"), ("ml", "ML pipeline"), ("app", "App")]),
                      Field("name", "name", "", required=True)]
    seen = []
    footer = lambda v: seen.append(v["type"]) or v["type"]
    # focus starts on the first field, the type: → twice and space once wraps back to cli; Tab to name
    out = drive(lambda: form("t", fields(), footer, lambda v: None), "\x1b[C\x1b[C \tx\r")
    assert out == {"type": "cli", "name": "x"}
    # → once picks ml; a space typed in the name field is still a space
    out = drive(lambda: form("t", fields(), footer, lambda v: None), "\x1b[C\ta b\r")
    assert out == {"type": "ml", "name": "a b"}


def test_form_normalizes_and_checks_as_you_type():
    from ds_next.scaffold import name_problem, normalize_name
    fields = lambda: [Field("name", "name", "", required=True, example="feed-model",
                            normalize=normalize_name, check=name_problem)]
    out = drive(lambda: form("t", fields(), lambda v: "", lambda v: None), "Feed Model_v2\r")
    assert out == {"name": "feed-model-v2"}
    # a trailing hyphen breaks the rule: Enter is refused, backspace fixes it, Enter goes through
    out = drive(lambda: form("t", fields(), lambda v: "", lambda v: None), "feed-\r\x7f\r")
    assert out == {"name": "feed"}


def test_normalize_name_examples():
    from ds_next.scaffold import name_problem, normalize_name
    assert normalize_name("  Barn  Board") == "barn-board"
    assert normalize_name("feed__model") == "feed-model"
    assert normalize_name("-x--y!") == "x-y"
    assert name_problem("feed-model") is None
    assert name_problem("class") and "keyword" in name_problem("class")
    assert name_problem("a") and "2 to 41" in name_problem("a")


def test_prompt_line_accepts_completes_and_recalls_history():
    import pytest
    from prompt_toolkit.history import InMemoryHistory

    from ds_next.ui import SlashCompleter
    comp = SlashCompleter({"/help": "this list", "/new": "start"}, {}, {})
    hist = InMemoryHistory()
    hist.append_string("/status")
    assert drive(lambda: prompt_line("New session", completer=comp, history=hist, width=60), "hello\r") == "hello"
    assert drive(lambda: prompt_line("#2", completer=comp, history=hist, width=60), "/he\t\r") == "/help"
    assert drive(lambda: prompt_line("#3", completer=comp, history=hist, width=60), "\x1b[A\r") == "/status"
    with pytest.raises(KeyboardInterrupt):
        drive(lambda: prompt_line("#4", completer=comp, history=hist, width=60), "abc\x03")
    with pytest.raises(EOFError):
        drive(lambda: prompt_line("#5", completer=comp, history=hist, width=60), "\x04")


def test_prompt_frame_is_exact():
    frags = prompt_frame("New session", "/new feed-model", 60)
    lines = "".join(txt for _, txt in frags).split("\n")
    assert [len(ln) for ln in lines] == [60, 60, 60], lines
    assert lines[0].startswith("╭─") and lines[0].endswith(" New session ──╮"), lines[0]
    assert lines[1].startswith("│ › /new feed-model") and lines[1].endswith("│")
    assert lines[2] == "╰" + "─" * 58 + "╯"
    from ds_next import ui_style as S
    assert lines == [t.plain for t in S.prompt_box("New session", "/new feed-model", 60)], "live and static agree"


def test_resize_clears_screen_and_scrollback_then_repaints():
    """VS Code's terminal re-wraps rows on a column change and shifts the cursor; the only
    redraw that cannot stack is one from a clean screen with the transcript printed again."""
    from prompt_toolkit.application import Application
    from prompt_toolkit.layout import Layout, Window

    from ds_next import widgets

    writes: list[str] = []

    class Out(DummyOutput):
        def erase_screen(self): writes.append("2J")
        def write_raw(self, data): writes.append(data)
        def cursor_goto(self, row=0, column=0): writes.append(f"goto {row},{column}")

    painted: list[int] = []
    widgets.repaint = lambda: painted.append(len(writes))
    try:
        with create_pipe_input() as inp, create_app_session(input=inp, output=Out()):
            app = widgets.resize_safe(Application(layout=Layout(Window()), output=Out()))
            app._on_resize()
    finally:
        widgets.repaint = None
    assert writes[:3] == ["2J", "\x1b[3J", "goto 0,0"], writes
    assert painted == [3], "the transcript is printed after the clear and before the redraw"
