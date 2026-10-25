"""A guided walk through every part of the Rule spec, one chapter per section."""
from __future__ import annotations

import os
import random
import time
from collections.abc import Callable

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.text import Text

from . import screens as S
from . import spec
from . import ui_style as u
from .ui_style import FACT_SEP, G


def make_console(theme: str = "dark", **kw) -> Console:
    """ui_style reads DS_THEME when it builds the theme, so set it first."""
    os.environ["DS_THEME"] = theme
    return u.console(**kw)


class Tour:
    def __init__(self, theme: str = "dark", *, pause: bool = True, both: bool = True) -> None:
        self.theme = theme
        self.c = make_console(theme)
        self.pause = pause and self.c.is_terminal
        self.both = both
        self.chapters: list[tuple[str, Callable[[], None]]] = [
            ("Rule", self.intro),
            ("Canopy vs Rule", self.versus),
            ("Principles", self.principles),
            ("Colour roles", self.colour),
            ("Glyph vocabulary", self.glyphs),
            ("Grid and the footing", self.grid),
            ("Every message type", self.messages),
            ("Dialogs", self.dialogs),
            ("Motion", self.motion),
            ("Mascot", self.mascot),
            ("Where it lands in code", self.code_map),
            *[(f"Screen {n} · {title}", self._screen(n)) for n, title, _ in spec.SCREENS],
            ("Known gaps", self.gaps),
        ]

    # ── chrome ───────────────────────────────────────────────────────────────
    def header(self, n: int, title: str) -> None:
        """Modernist section head: ink chip with the number, uppercase name, heavy rule under it."""
        c = self.c
        c.print()
        c.print(Text.assemble((f" {n:>2} ", "reverse bold"), "  ", (title.upper(), "bold")))
        c.print(Text(G.h * u.DESIGN_WIDTH, style="rule"))

    def para(self, s: str, style: str = "") -> None:
        self.c.print(Text(s, style=style), width=u.DESIGN_WIDTH)

    def mock(self, rows: S.Rows, theme: str | None = None, caption: str = "") -> None:
        """Print a terminal mockup on its theme's ground so dark and light both read in any terminal."""
        theme = theme or self.theme
        c = make_console(theme) if theme != self.theme else self.c
        bg, fg, _ = u.BG[theme]
        tc = u.truecolor()
        if caption:
            self.c.print(Text.assemble((caption.upper(), "bold"), "  ", (theme, "dim")))
        for r in rows:
            r = r.copy()
            r.pad_right(u.DESIGN_WIDTH - r.cell_len)
            if tc:
                r.stylize_before(f"{fg} on {bg}")
            c.print(r, no_wrap=True, overflow="crop", width=max(u.DESIGN_WIDTH, c.width))
        self.c = make_console(self.theme)  # restore DS_THEME for the next mock

    def mocks(self, rows: Callable[[], S.Rows], caption: str = "") -> None:
        themes = ["dark", "light"] if self.both else [self.theme]
        for t in themes:
            self.mock(rows(), t, caption)
            self.c.print()

    def wait(self) -> bool:
        if not self.pause:
            return True
        ans = self.c.input(Text.assemble((G.prompt, "accent_text"), " ", ("enter next  q quits", "dim"), " "))
        return ans.strip().lower() != "q"

    def table(self, *cols: str) -> Table:
        t = Table(box=box.SIMPLE_HEAD, header_style="dim bold", border_style="rule", pad_edge=False,
                  show_edge=False, width=u.DESIGN_WIDTH)
        for col in cols:
            t.add_column(col.upper())
        return t

    # ── run ──────────────────────────────────────────────────────────────────
    def run(self, start: int = 0, only: int | None = None) -> None:
        picks = [only] if only is not None else range(start, len(self.chapters))
        for i in picks:
            title, fn = self.chapters[i]
            self.header(i, title)
            fn()
            if only is None and i < len(self.chapters) - 1 and not self.wait():
                break

    def listing(self) -> None:
        for i, (title, _) in enumerate(self.chapters):
            self.c.print(Text.assemble((f"{i:>3}", "muted bold"), "  ", title))

    # ── chapters ─────────────────────────────────────────────────────────────
    def intro(self) -> None:
        self.para(f"{spec.PRODUCT} · terminal design system · Modernist direction · {spec.VERSION}", "accent_text")
        self.c.print()
        self.para("The grid shows.", "bold")
        self.para(spec.TAGLINE, "bold")
        self.c.print()
        self.para(spec.SUMMARY)
        self.c.print()
        for k, v in spec.ASSUMPTIONS:
            self.c.print(u.labelled(k, Text(v, "muted"), upper=True), width=u.DESIGN_WIDTH)

    def versus(self) -> None:
        self.para("The same turn. Canopy is warm and rounded; Rule is ink, red and square, with a numbered "
                  "rule opening each turn.", "muted")
        self.c.print()
        self.mocks(S.rule_vs_canopy, "1b Rule")
        t = self.table("Canopy", "Rule")
        for a, b in spec.CHANGES_FROM_CANOPY:
            t.add_row(Text(a, "dim"), b)
        self.c.print(t)

    def principles(self) -> None:
        for i, (title, body) in enumerate(spec.PRINCIPLES, 1):
            self.c.print(Text(G.h * u.DESIGN_WIDTH, style="text"))
            self.c.print(Text.assemble((f"{i}  ", "accent bold"), (title, "bold")))
            self.para(body, "muted")
            self.c.print()

    def colour(self) -> None:
        self.para("Eight roles, both from Modernist's ramps. The dark theme inverts the page: ground = Modernist "
                  "text, text = Modernist ground. There is no ok/warn/err triad: done is text, warn and err are "
                  "red (err bold).", "muted")
        self.c.print()
        t = self.table("role", "dark", "", "light", "", "use")
        for role, d, dt, l, lt, use in spec.COLOURS:
            t.add_row(role, Text("██", style=d), Text(f"{d}\n{dt}", "dim"), Text("██", style=l),
                      Text(f"{l}\n{lt}", "dim"), Text(use, "muted"))
        self.c.print(t)
        ansi = FACT_SEP.join(f"{k} {v}" for k, v in spec.ANSI16.items())
        self.c.print(u.labelled("ansi-16", Text(ansi, "muted"), upper=True), width=u.DESIGN_WIDTH)
        self.c.print()
        for r in spec.COLOUR_RULES:
            self.c.print(Text.assemble((G.agent, "accent"), " ", r), width=u.DESIGN_WIDTH)
        self.c.print()
        self.para("In use, this terminal's theme:", "dim")
        for role in ("text", "muted", "dim", "rule", "accent", "accent_text"):
            self.c.print(Text.assemble(f"  {role:<12}", (f"the quick brown canoe {G.agent} {G.h * 6}", role)))

    def glyphs(self) -> None:
        t = self.table("glyph", "name", "means", "colour", "column")
        for g, name, means, colour, col in spec.GLYPHS:
            t.add_row(Text(g, "bold"), name, Text(means, "muted"), Text(colour, "dim"), Text(col, "dim"))
        self.c.print(t)
        self.para("Not used: " + ", ".join(spec.RETIRED) + ". The three systems never share a screen.", "dim")

    def grid(self) -> None:
        self.mocks(S.grid_diagram, "5a 80-column grid")
        for k, v in spec.GRID_NOTES:
            self.c.print(Text.assemble((k, "bold"), "  ", (v, "muted")), width=u.DESIGN_WIDTH)
            self.c.print()
        g = spec.GRID
        vals = [("design width", g["design_width"]), ("min width", g["min_width"]), ("indent", g["indent"]),
                ("result indent", g["result_indent"]), ("label width", g["label_width"]),
                ("fact sep", repr(g["fact_separator"]))]
        for k, v in vals:
            self.c.print(u.labelled(k, str(v)))
        self.c.print()
        self.c.print(Text.assemble(("Case  ", "bold"), (spec.CASE, "muted")), width=u.DESIGN_WIDTH)

    def messages(self) -> None:
        self.mocks(S.message_types, "6 every message type")

    def dialogs(self) -> None:
        self.para("Heavy frame, red edge while asking, uppercase title flush left, numbered options with ■ on "
                  "the focus and □ on the rest.", "muted")
        self.c.print()
        self.mocks(S.dialog_reference, "7 permission")

    def motion(self) -> None:
        for k, v in spec.MOTION:
            self.c.print(Text.assemble((k, "bold"), "  ", (v, "muted")), width=u.DESIGN_WIDTH)
        self.c.print()
        self.para("Spinner verbs: " + " · ".join(spec.VERBS), "dim")
        self.c.print()
        self.para("Live, in this terminal:", "dim")
        self.c.print()
        play_turn(self.c, fast=not self.c.is_terminal)

    def mascot(self) -> None:
        self.para(spec.MASCOT["note"], "muted")
        self.c.print()
        for ln in u.mascot_lines():
            self.c.print(Text("  ").append_text(ln))
        self.c.print()
        self.para("The pixels (I = ink, R = red), two rows per half-block cell:", "dim")
        for row in u.MASCOT:
            self.c.print(Text("  ").append_text(Text.assemble(*[
                (ch, {"I": "text", "R": "accent"}.get(ch, "dim")) for ch in row])))

    def code_map(self) -> None:
        t = self.table("token / helper", "in ui_style.py", "differs from Canopy")
        for a, b, d in spec.CODE_MAP:
            t.add_row(Text(a, "bold"), b, Text(d, "muted"))
        self.c.print(t)

    def _screen(self, n: int) -> Callable[[], None]:
        def show() -> None:
            note = next(note for k, _, note in spec.SCREENS if k == n)
            self.para(note, "muted")
            self.c.print()
            self.mocks(S.SCREENS[n], f"{n}")
        return show

    def gaps(self) -> None:
        for g in spec.KNOWN_GAPS:
            self.c.print(Text.assemble((G.warn, "accent"), " ", g), width=u.DESIGN_WIDTH)
        self.c.print()
        self.para("That's the whole system. `rule-cli demo` runs a live session in it.", "dim")


# ── motion, live ─────────────────────────────────────────────────────────────
QUADRANT = ["▖", "▘", "▝", "▗"]


def spin(c: Console, live: Live, above: list[Text], verb: str, secs: float, fast: bool) -> None:
    """One live line above the footing; ticks at 160 ms, seconds once a second."""
    steps = 2 if fast else int(secs / 0.16)
    for i in range(steps):
        line = S.working(QUADRANT[i % 4], verb, int(i * 0.16))
        live.update(Group(*above, Text(), line, Text(), *S.footing("queue a message  it sends after this turn",
                                                                   "esc interrupts")))
        time.sleep(0 if fast else 0.16)


def play_turn(c: Console, fast: bool = False, said: str = "add a --since flag to the metrics command",
              n: int = 2) -> None:
    """Thinking streams then folds, a tool runs then lands, the agent replies. Only the footing redraws."""
    for r in S.echo(n, said):
        c.print(r)
    thinking = ["The user wants an ISO date. Yesterday is the natural default because the",
                "purpose line says daily metrics for finance. Check how click options are",
                "declared in cli.py first…"]
    with Live(console=c, refresh_per_second=12, transient=True) as live:
        shown: list[Text] = []
        for i, t in enumerate(thinking):
            shown.append(u.thinking(t, first=i == 0))
            spin(c, live, shown, "Drafting", 0.8, fast)
    c.print(u.thought(3))
    steps = [("Read", "src/order_metrics/cli.py", "142 lines", 0, "Reading"),
             ("Edit", "src/order_metrics/cli.py", "+14 −1", 0, "Squaring"),
             ("Bash", "uv run pytest -q", "13 passed in 1.42s", 11, "Running tests")]
    for name, args, res, more, verb in steps:
        with Live(console=c, refresh_per_second=12, transient=True) as live:
            spin(c, live, [u.tool(name, args, state="running"), *u.result("…")], verb or random.choice(u.VERBS),
                 1.0, fast)
        c.print(u.tool(name, args))       # the ▪ lands where the ▘ was
        for r in u.result(res, more):
            c.print(r)
    c.print()
    for r in S.agent(Text.assemble("Done. ", ("--since", "bold"), " defaults to yesterday and the tests pass.")):
        c.print(r)
    c.print()
    c.print(u.facts("3 tools", "15.2s", "$0.0041"))
    c.print()
