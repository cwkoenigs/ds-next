"""Rule: ds-next terminal style in the Modernist direction. Ink on ground, one red, heavy square
rules, a numbered rule per turn, pinned square input box, numbered dialogs, canoe mascot.

Same helper names as the Canopy module where the concept is the same so a renderer can swap
`ui_style_canopy` for `ui_style_rule`. Design reference: "Rule Terminal Design System" / "Rule Screens".
"""
from __future__ import annotations

import os
import random
from dataclasses import dataclass

from rich.console import Console, RenderableType
from rich.spinner import SPINNERS
from rich.style import Style
from rich.text import Text
from rich.theme import Theme

# ── colour roles from the Modernist ramps: (dark, light, ansi-16) ────────────
PALETTE = {
    "text":        ("#f3f2f2", "#201e1d", "default"),
    "muted":       ("#bab6b6", "#605d5d", "bright_black"),      # neutral-400 / 700
    "dim":         ("#7d7979", "#9b9797", "bright_black"),      # neutral-600 / 500
    "rule":        ("#9b9797", "#605d5d", "bright_black"),      # neutral-500 / 700
    "accent":      ("#ff563c", "#ec3013", "red"),               # accent-500 / accent
    "accent_text": ("bold #ff9783", "bold #ae1800", "bold red"),  # accent-400 / 700
    "surface":     ("on #2d2b2b", "on #eae9e9", "on bright_black"),
    "code":        ("#f3f2f2 on #2d2b2b", "#201e1d on #eae9e9", "on bright_black"),
    "on_accent":   ("on #ff563c", "on #ec3013", "on red"),
    "on_text":     ("on #f3f2f2", "on #201e1d", "reverse"),
}
BG = {"dark": ("#201e1d", "#f3f2f2", "#2d2b2b"), "light": ("#f3f2f2", "#201e1d", "#eae9e9")}


def is_dark() -> bool:
    return os.environ.get("DS_THEME", "dark") != "light"


def truecolor() -> bool:
    return os.environ.get("COLORTERM", "") in ("truecolor", "24bit")


def theme(*, color: bool = True) -> Theme:
    dark, tc = is_dark(), truecolor()
    styles = {}
    for role, (d, l, ansi) in PALETTE.items():
        styles[role] = ("bold" if role == "accent_text" else "") if not color else ((d if dark else l) if tc else ansi)
    # Rich looks a style name up whole, so "muted bold" must be its own theme entry.
    parse = lambda name: " ".join(styles.get(p, p) for p in name.split())
    for combo in COMBOS:
        styles[combo] = Style.parse(parse(combo) or "none")
    return Theme(styles)


# role combinations the builders use; registered in theme() so they resolve
COMBOS = ["muted bold", "accent bold", "text on_accent", "accent on_text", "dim on_text"]


def console(*, color: bool = True, **kw) -> Console:
    return Console(theme=theme(color=color), highlight=False, **kw)


_ANSI = {"default": "", "black": "ansiblack", "red": "ansired", "green": "ansigreen", "yellow": "ansiyellow",
         "blue": "ansiblue", "magenta": "ansimagenta", "cyan": "ansicyan", "white": "ansiwhite",
         "bright_black": "ansibrightblack", "dim": ""}


def _pt(style: str) -> str:
    out, toks, i = [], style.split(), 0
    while i < len(toks):
        t = toks[i]
        if t == "on" and i + 1 < len(toks):
            c = toks[i + 1]
            out.append("bg:" + (c if c.startswith("#") else _ANSI.get(c, c)))
            i += 2
            continue
        out.append(t if t.startswith("#") or t in ("bold", "italic", "underline", "reverse") else _ANSI.get(t, t))
        i += 1
    return " ".join(x for x in out if x)


def pt_style() -> dict[str, str]:
    dark, tc = is_dark(), truecolor()
    col = {r: _pt((v[0] if dark else v[1]) if tc else v[2]) for r, v in PALETTE.items()}
    bg, fg, sf = BG["dark" if dark else "light"]
    return {
        "prompt": col["accent_text"], "dim": col["dim"], "muted": col["muted"], "accent": col["accent"],
        "strong": col["accent_text"], "err": col["accent_text"], "label": col["dim"], "focus": col["accent_text"],
        "title": col["accent"] + " bold", "field": "", "error": col["accent_text"],
        "frame.border": col["rule"], "frame.border.active": col["accent"], "frame.label": col["accent"] + " bold",
        "bottom-toolbar": f"bg:{bg} {col['muted']}", "bottom-toolbar.text": f"bg:{bg} {col['muted']}",
        "bottom-toolbar.key": f"bg:{bg} {col['dim']}",
        "completion-menu": f"bg:{bg} {col['dim']}",
        "completion-menu.completion": f"bg:{bg} {fg}",
        "completion-menu.completion.current": f"bg:{bg} {fg} bold",
        "completion-menu.meta.completion": f"bg:{bg} {col['dim']}",
        "completion-menu.meta.completion.current": f"bg:{bg} {col['muted']}",
        "scrollbar.background": f"bg:{bg}", "scrollbar.button": f"bg:{sf}",
    }


# ── glyphs: squares, heavy lines ─────────────────────────────────────────────
@dataclass(frozen=True)
class _Glyphs:
    prompt: str = "›"
    agent: str = "■"     # agent speaking · focused option     accent
    tool: str = "▪"      # tool done (text) · failed (accent)
    pending: str = "▫"   # tool running                        dim
    option: str = "□"    # unselected dialog option            dim
    result: str = "└"    # first result line · fold            dim
    think: str = "·"     # thinking lead · fold · fact sep in status row
    ok: str = "✓"
    warn: str = "⚠"
    err: str = "✗"
    h: str = "━"
    v: str = "┃"
    corners: tuple = ("┏", "┓", "┗", "┛")


G = _Glyphs()
SPINNERS["quadrant"] = {"interval": 160, "frames": ["▖", "▘", "▝", "▗"]}
SPINNER = "quadrant"
VERBS = ["Drafting", "Ruling", "Measuring", "Squaring", "Aligning", "Plotting", "Setting", "Composing",
         "Inking", "Paddling", "Portaging", "Sounding", "Charting"]


def verb() -> str:
    return random.choice(VERBS)


# ── grid ─────────────────────────────────────────────────────────────────────
INDENT = 2          # speech, tool calls → col 3
RESULT_INDENT = 4   # result text        → col 5 (└ at col 3)
LABEL_W = 12
FACT_SEP = "  "     # two spaces between facts; no · in flow
DESIGN_WIDTH = 80


def width(c: Console) -> int:
    return max(60, c.width)


# ── builders ─────────────────────────────────────────────────────────────────
def turn_rule(n: int, w: int = DESIGN_WIDTH) -> Text:
    """━━ 03 ━━━━… — opens every prompt; the number is flush left."""
    return Text.assemble((G.h * 2 + " ", "rule"), (f"{n:02d}", "muted bold"), (" " + G.h * (w - 6), "rule"))


def you(line: str) -> Text:
    return Text.assemble((G.prompt, "accent_text"), " ", line)


def agent_lines(c: Console, body: RenderableType) -> None:
    lines = c.render_lines(body, c.options.update_width(width(c) - INDENT), pad=False)
    for i, segs in enumerate(lines):
        head = Text(G.agent + " ", style="accent") if i == 0 else Text("  ")
        c.print(head, Text.assemble(*((s.text, s.style or "") for s in segs)).rstrip(), sep="")


def heading(text: str) -> Text:
    """Markdown heading inside agent text: uppercase, bold, col 3."""
    return Text(" " * INDENT + text.upper(), style="bold")


def tool(name: str, args: str = "", *, state: str = "done") -> Text:
    glyph, style = {"running": (G.pending, "dim"), "done": (G.tool, "text"), "failed": (G.tool, "accent")}[state]
    t = Text.assemble((glyph, style), " ", (name, "bold"))
    if args:
        t.append(" " + args, "muted")
    return t


def result(first: str, more: int = 0, *, error: bool = False, key: str = "ctrl-o") -> list[Text]:
    out = [Text.assemble(" " * INDENT, (f"{G.result} {first}", "accent_text" if error else "dim"))]
    if more:
        out.append(Text.assemble(" " * RESULT_INDENT, (f"{G.result} {more} more lines{FACT_SEP}{key}", "dim")))
    return out


def thinking(line: str, *, first: bool = False) -> Text:
    return Text((G.think + " " if first else "  ") + line, style="dim")


def thought(secs: float, *, key: str = "ctrl-o") -> Text:
    return Text(f"{G.think} Thought for {secs:.0f}s{FACT_SEP}{key}", style="dim")


def outcome(kind: str, subject: str, detail: str = "") -> Text:
    """ok → ink; warn → accent; err → accent bold. Colour means 'needs you', not 'kind'."""
    style = {"ok": "text", "warn": "accent", "err": "accent_text"}[kind]
    t = Text.assemble((getattr(G, kind), style), " ", (subject, "bold"))
    if detail:
        t.append(FACT_SEP).append(detail, "muted")
    return t


def facts(*items: str, indent: int = INDENT) -> Text:
    """Dim fact row: `3 tools  15.2s  $0.0041`."""
    return Text(" " * indent + FACT_SEP.join(items), style="dim")


def status_label(step: str | None, secs: int) -> str:
    return f"[accent]{step or verb()}[/]{FACT_SEP}[dim]{secs}s{FACT_SEP}esc interrupts[/]"


def labelled(label: str, value: Text | str, *, indent: int = INDENT, upper: bool = False) -> Text:
    lab = label.upper() if upper else label
    t = Text(" " * indent).append(f"{lab:<{LABEL_W}} ", style="dim")
    return t.append_text(value if isinstance(value, Text) else Text(value))


# ── frames: heavy, square, title flush left ──────────────────────────────────
def frame(rows: list[Text | None], *, edge: str = "rule", title: Text | None = None, w: int = DESIGN_WIDTH) -> list[Text]:
    iw = w - 2
    tl, tr, bl, br = G.corners
    if title is not None:
        out = [Text.assemble((tl + G.h + " ", edge), title, (" " + G.h * (iw - 3 - title.cell_len) + tr, edge))]
    else:
        out = [Text(tl + G.h * iw + tr, style=edge)]
    for r in rows:
        r = Text() if r is None else r.copy()
        r.truncate(iw - 1)
        r.pad_right(iw - 1 - r.cell_len)
        out.append(Text.assemble((G.v + " ", edge), r, (G.v, edge)))
    out.append(Text(bl + G.h * iw + br, style=edge))
    return out


def input_frame(typed: Text | str, *, hint: str = "", w: int = DESIGN_WIDTH) -> list[Text]:
    typed = Text(typed) if isinstance(typed, str) else typed
    line = Text.assemble((G.prompt, "accent_text"), " ").append_text(typed)
    if not typed.plain and hint:
        line.append(" " + hint, "dim")
    return frame([line], w=w)


def dialog(title: str, body: list[Text | str], options: list[str], *, default: int = 1,
           question: str = "PROCEED?", w: int = DESIGN_WIDTH) -> list[Text]:
    """Red heavy frame, uppercase title, ■ on the default, □ on the rest, esc = last option."""
    rows: list[Text | None] = [Text(b) if isinstance(b, str) else b for b in body] + [None, Text(question, style="bold")]
    for i, o in enumerate(options, 1):
        if i == default:
            rows.append(Text.assemble((G.agent, "accent_text"), " ", (str(i), "bold"), FACT_SEP, o))
        else:
            rows.append(Text.assemble((G.option, "dim"), " ", (str(i), "muted"), FACT_SEP, o))
    return frame(rows, edge="accent", title=Text(title.upper(), style="accent bold"), w=w)


def status_row(left: str, right: str, w: int) -> list[tuple[str, str]]:
    """Bare status row under the box. Drops cwd, then model, so it always fits one row."""
    parts = right.split(" · ")
    while len(parts) > 1 and len(left) + len(" · ".join(parts)) + 6 > w:
        parts.pop(0 if len(parts) == 2 else 1)
    right = " · ".join(parts)
    gap = max(1, w - len(left) - len(right) - 4)
    return [("class:bottom-toolbar.key", f"  {left}"), ("class:bottom-toolbar", " " * gap + right + "  ")]


def popup_rows(items: list[tuple[str, str]], selected: int = 0) -> list[Text]:
    out = []
    for i, (cmd, desc) in enumerate(items):
        if i == selected:
            out.append(Text.assemble(" ", (G.agent, "accent_text"), " ", (f"{cmd:<14}", "bold"), (desc, "muted")))
        else:
            out.append(Text.assemble("   ", f"{cmd:<14}", (desc, "dim")))
    return out


# ── mascot: a canoe in ink with a red paddle; water in red (28×20, half-blocks) ─
MASCOT = """\
.......................RR...
......................RRRR..
......................RRRR..
.....................RRRR...
....................RR......
...................RR.......
..................RR........
.................RR.........
................RR..........
...............RR...........
..............RR............
I............RR............I
II..........RR............II
IIIIIIIIIIIIIIIIIIIIIIIIIIII
.IIIIIIIIIIIIIIIIIIIIIIIIII.
..IIIIIIIIIIIIIIIIIIIIIIII..
....IIIIIIIIIIIIIIIIIIII....
.......IIIIIIIIIIIIII.......
............................
.RR.RR...RR.RR....RR.RR.RR..
""".splitlines()
_INK = {"I": "text", "R": "accent"}


def mascot_lines() -> list[Text]:
    out = []
    for top, bot in zip(MASCOT[0::2], MASCOT[1::2]):
        t = Text()
        for a, b in zip(top, bot):
            ia, ib = _INK.get(a), _INK.get(b)
            if not ia and not ib:
                t.append(" ")
            elif ia == ib:
                t.append("█", style=ia)
            elif ia and ib:
                t.append("▀", style=f"{ia} on_{ib}")
            elif ia:
                t.append("▀", style=ia)
            else:
                t.append("▄", style=ib)
        out.append(t)
    return out


def banner(version: str, facts_: list[tuple[str, str]], hints: list[str], tagline: str,
           w: int = DESIGN_WIDTH) -> list[Text]:
    """Heavy two-pane frame shown once. Word-mark and labels uppercase, flush left."""
    li, e = 30, "rule"
    ri = w - 3 - li
    title = Text.assemble(("DS-NEXT", "bold"), (f" {version}", "dim"))
    out = [Text.assemble(("┏━ ", e), title, (" " + G.h * (li - 3 - title.cell_len) + "┳" + G.h * ri + "┓", e))]
    left = [Text(" ").append_text(m) for m in mascot_lines()] + [
        Text(), Text(" DS-NEXT", style="bold"), Text(" " + tagline, style="muted")]
    right = [Text()] + [Text.assemble(("  " + f"{k.upper():<10}", "dim"), v) for k, v in facts_] + [Text()]
    right += [Text("  " + h, style="dim") for h in hints]
    for i in range(max(len(left), len(right))):
        l_ = (left[i] if i < len(left) else Text()).copy()
        r_ = (right[i] if i < len(right) else Text()).copy()
        l_.truncate(li); l_.pad_right(li - l_.cell_len)
        r_.truncate(ri); r_.pad_right(ri - r_.cell_len)
        out.append(Text.assemble((G.v, e), l_, (G.v, e), r_, (G.v, e)))
    out.append(Text("┗" + G.h * li + "┻" + G.h * ri + "┛", style=e))
    return out
