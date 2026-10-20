"""The picker and the form, driven by real keystrokes through a pipe."""
import asyncio

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from ds_next.widgets import Field, form, pick


def drive(coro_fn, keys: str):
    async def go():
        with create_pipe_input() as inp, create_app_session(input=inp, output=DummyOutput()):
            task = asyncio.ensure_future(coro_fn())
            await asyncio.sleep(0.1)
            for ch in keys:                       # one key at a time, as a person types
                inp.send_text(ch)
                await asyncio.sleep(0.01)
            return await asyncio.wait_for(task, 3)
    return asyncio.run(go())


FIELDS = lambda: [Field("name", "name", "", required=True), Field("purpose", "purpose", "", required=True),
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
