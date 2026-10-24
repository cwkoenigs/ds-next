"""rule-cli: the Rule terminal design system as a runnable sample.

    rule-cli                 walk through every part of the spec (same as `tour`)
    rule-cli tour [-c N]     the walkthrough, or one chapter of it
    rule-cli chapters        list the chapters
    rule-cli screen [N]      print screen N (1-7) or all of them, dark and light
    rule-cli spec [--json]   the spec as data
    rule-cli html [-o FILE]  the tour as one web page, for reading on a phone
    rule-cli demo            a live session drawn in Rule
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from rich.text import Text

from . import screens as S
from . import spec
from . import ui_style as u
from .tour import Tour, make_console, play_turn
from .ui_style import G


def _theme_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--theme", choices=["dark", "light"], default=os.environ.get("DS_THEME", "dark"),
                   help="theme for prose and the live demo (default: $DS_THEME or dark)")
    p.add_argument("--color", choices=["truecolor", "ansi16"],
                   help="force the colour depth (default: from $COLORTERM)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rule-cli", description="The Rule terminal design system, walked through.")
    sub = ap.add_subparsers(dest="cmd")

    t = sub.add_parser("tour", help="walk through every part of the spec")
    t.add_argument("-c", "--chapter", type=int, help="show one chapter (see `chapters`)")
    t.add_argument("--from", dest="start", type=int, default=0, help="start at this chapter")
    t.add_argument("--no-pause", action="store_true", help="don't wait for enter between chapters")
    t.add_argument("--one-theme", action="store_true", help="show mockups in --theme only, not dark and light")
    _theme_args(t)

    sub.add_parser("chapters", help="list the tour's chapters")

    s = sub.add_parser("screen", help="print one screen (1-7) or all")
    s.add_argument("n", nargs="?", type=int, choices=range(1, 8), metavar="N")
    s.add_argument("--one-theme", action="store_true")
    _theme_args(s)

    j = sub.add_parser("spec", help="print the spec")
    j.add_argument("--json", action="store_true", help="as JSON")

    h = sub.add_parser("html", help="write the tour as one web page (readable on a phone)")
    h.add_argument("-o", "--out", default="rule-tour.html")

    d = sub.add_parser("demo", help="a live session drawn in Rule")
    _theme_args(d)

    a = ap.parse_args(argv)
    if getattr(a, "color", None):
        os.environ["COLORTERM"] = "truecolor" if a.color == "truecolor" else ""
    cmd = a.cmd or "tour"

    if cmd == "tour":
        tour = Tour(getattr(a, "theme", "dark"), pause=not getattr(a, "no_pause", False),
                    both=not getattr(a, "one_theme", False))
        try:
            tour.run(getattr(a, "start", 0), getattr(a, "chapter", None))
        except (KeyboardInterrupt, EOFError):
            tour.c.print()
        return 0
    if cmd == "chapters":
        Tour(pause=False).listing()
        return 0
    if cmd == "screen":
        tour = Tour(a.theme, pause=False, both=not a.one_theme)
        for n in [a.n] if a.n else range(1, 8):
            title = spec.SCREENS[n - 1][1]
            tour.header(n, title)
            tour.chapters[[c[0] for c in tour.chapters].index(f"Screen {n} · {title}")][1]()
        return 0
    if cmd == "spec":
        if a.json:
            json.dump(spec.as_dict(), sys.stdout, ensure_ascii=False, indent=2)
            print()
        else:
            Tour(pause=False, both=False).run(0)
        return 0
    if cmd == "html":
        from .html import build
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(build())
        print(a.out)
        return 0
    if cmd == "demo":
        return demo(a.theme)
    ap.print_help()
    return 2


# ── demo: a session in Rule ──────────────────────────────────────────────────
HELP = [("/new", "Start a project from the canon"), *S.COMMANDS, ("/help", "This list"), ("/exit", "Leave")]


def demo(theme: str) -> int:
    c = make_console(theme)
    for r in S.banner()[:-4]:
        c.print(r)
    n = 0
    while True:
        c.print()
        for r in S.footing("/new python cli order-metrics  or ask a question"):
            c.print(r)
        try:
            said = c.input(Text.assemble((G.prompt, "accent_text"), " ")).strip()
        except (EOFError, KeyboardInterrupt):
            c.print()
            return 0
        if not said:
            continue
        if said in ("/exit", "/quit"):
            return 0
        n += 1
        c.print()
        if said == "/help" or said == "/":
            for r in [u.turn_rule(n), u.you(said), Text()]:
                c.print(r)
            for r in u.popup_rows(HELP, 0):
                c.print(r)
        elif said.startswith("/new"):
            for r in S.new_form(n)[:-5]:
                c.print(r)
            c.print(S.created())
        elif said == "/status":
            for r in S.status_screen(n)[:-5]:
                c.print(r)
        elif said.startswith("/"):
            for r in [u.turn_rule(n), u.you(said), Text(),
                      u.outcome("err", said, "not a command  /help lists them")]:
                c.print(r)
        else:
            play_turn(c, said=said, n=n)
            if not approve(c):
                c.print(u.outcome("warn", "declined", "tell ds-next what to do differently"))
    return 0


def approve(c) -> bool:
    for r in [*S.agent("The flag parses. I want to run the suite to confirm nothing else moved."), Text(),
              u.tool("Bash", "uv run pytest -q", state="running"), Text(), *S.approval_dialog(),
              S.status("enter chooses  1-3 answer  esc declines")]:
        c.print(r)
    try:
        ans = c.input(Text.assemble((G.prompt, "accent_text"), " ")).strip() or "1"
    except (EOFError, KeyboardInterrupt):
        ans = "3"
    c.print(Text.assemble((G.prompt, "accent_text"), " ", ("Yes", "bold") if ans in "12" else ("No", "bold")))
    if ans not in ("1", "2"):
        return False
    c.print(u.tool("Bash", "uv run pytest -q"))
    for r in u.result("13 passed in 1.42s", 11):
        c.print(r)
    c.print()
    c.print(u.facts("4 tools", "18.9s", "$0.0052"))
    return True


if __name__ == "__main__":
    raise SystemExit(main())
