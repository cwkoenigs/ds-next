"""The seven Rule screens, plus the spec page's reference mockups, as lists of Rich Text rows.

Each function returns the whole terminal at 80 columns: ruled transcript above, the heavy
square footing below. Content follows "Rule Screens.dc.html" line for line.
"""
from __future__ import annotations

from rich.text import Text

from . import ui_style as u
from .ui_style import FACT_SEP, G

MODEL_LINE = "claude-sonnet-4-5 · ~/Developer/order-metrics · ctx 34%"
PROJECT_HINT = "/new python cli order-metrics"
Rows = list[Text]


# ── footing ──────────────────────────────────────────────────────────────────
def cursor() -> Text:
    return Text(" ", style="reverse")


def box(hint: str = "", typed: str = "") -> Rows:
    """The pinned input box. Cursor after what's typed; a hint shows only while empty."""
    line = Text.assemble((G.prompt, "accent_text"), " ", typed, cursor())
    if hint and not typed:
        line.append(hint, "dim")
    return u.frame([line])


def status(left: str, right: str = MODEL_LINE) -> Text:
    """Bare status row: keys dim on the left, facts muted on the right, · dim between them."""
    (_, left_s), (_, right_s) = u.status_row(left, right, u.DESIGN_WIDTH)
    facts_ = right_s.strip()
    out = Text(left_s, style="dim").append(" " * (len(right_s) - len(right_s.lstrip(" "))))
    for i, part in enumerate(facts_.split(" · ")):
        if i:
            out.append(" · ", "dim")
        out.append(part, "muted")
    return out.append("  ")


def footing(hint: str = PROJECT_HINT, left: str = "? shortcuts", right: str = MODEL_LINE, typed: str = "") -> Rows:
    return [*box(hint, typed), status(left, right)]


# ── transcript pieces ────────────────────────────────────────────────────────
def agent(*lines: Text | str) -> Rows:
    """■ on the first line, col 3 for the rest. Lines are already wrapped to 78."""
    out = []
    for i, ln in enumerate(lines):
        head = Text(G.agent, style="accent") if i == 0 else Text(" ")
        out.append(Text.assemble(head, " ", ln if isinstance(ln, Text) else Text(ln)))
    return out


def code(s: str) -> Text:
    return Text(f" {s} ", style="code")


def changed(rows: list[tuple[str, str]], wid: int = 26) -> Rows:
    return [Text.assemble("  ", code(f), " " * (wid - len(f) - 1), (d, "muted")) for f, d in rows]


def echo(n: int, said: str) -> Rows:
    return [u.turn_rule(n), u.you(said), Text()]


BLANK = Text()


# ── 1 banner ─────────────────────────────────────────────────────────────────
BANNER_FACTS = [("cwd", "~/Developer"), ("canon", "16 standards  2 scaffolds"),
                ("skills", "5 from skills-os"), ("docs", "docs-ds found")]
BANNER_HINTS = ["/new starts a project", "/help lists commands", "ctrl-d leaves"]


def banner() -> Rows:
    return [*u.banner("0.1.0", BANNER_FACTS, BANNER_HINTS, "projects from the canon"), BLANK,
            *footing("/new python cli order-metrics  or ask a question")]


# ── 2 /new form ──────────────────────────────────────────────────────────────
def form_row(label: str, value: Text | str, *, required: bool = False, focus: bool = False) -> Text:
    lab = f"{label.upper():<{u.LABEL_W - 1}}{'*' if required else ' '}"
    return Text.assemble((lab, "accent_text" if focus else "dim"), " ", value)


def new_form(n: int = 1) -> Rows:
    rows: list[Text | None] = [
        form_row("type", Text.assemble("‹ Python command-line tool ›", FACT_SEP, ("1/2", "dim"))),
        form_row("name", "order-metrics", required=True),
        form_row("purpose", Text.assemble("Pull daily order metrics from Snowflake for finance", cursor()),
                 required=True, focus=True),
        form_row("owner", "cwkoenigs"),
        None,
        form_row("applies", FACT_SEP.join(["python-package", "cli-ux", "logging", "testing", "security", "docs"])),
        form_row("into", "~/Developer/order-metrics"),
    ]
    return [*echo(n, PROJECT_HINT), *u.frame(rows, edge="accent", title=Text("NEW PROJECT FROM THE CANON", "accent bold")),
            BLANK, *footing(PROJECT_HINT, "tab next  ←→ cycle  enter create  esc cancel")]


# ── 3 working ────────────────────────────────────────────────────────────────
def created() -> Text:
    return u.outcome("ok", "order-metrics", FACT_SEP.join(["python-cli v1", "6 standards", "~/Developer/order-metrics"]))


def working(frame: str = "▝", verb: str = "Measuring", secs: int = 4) -> Text:
    return Text.assemble((frame, "accent"), " ", Text.from_markup(u.status_label(verb, secs)))


def working_screen() -> Rows:
    return [
        u.turn_rule(1), u.you(PROJECT_HINT), BLANK, created(), BLANK,
        *echo(2, "add a --since flag to the metrics command"),
        u.thinking("The user wants an ISO date. Yesterday is the natural default because the", first=True),
        u.thinking("purpose line says daily metrics for finance. Check how click options are"),
        u.thinking("declared in cli.py first…"),
        BLANK,
        u.tool("Read", "src/order_metrics/cli.py", state="running"), *u.result("reading…"),
        BLANK, working(), BLANK,
        *footing("queue a message  it sends after this turn", "esc interrupts"),
    ]


# ── 4 agent turn ─────────────────────────────────────────────────────────────
def turn_body() -> Rows:
    since = ("--since", "bold")
    return [
        u.thought(3),
        *agent(Text.assemble("I'll add ", since, " as an ISO date and default it to yesterday, which is"),
               "what the finance team asked for in the purpose line."),
        BLANK,
        u.tool("Read", "src/order_metrics/cli.py"), *u.result("142 lines"),
        u.tool("Edit", "src/order_metrics/cli.py"), *u.result("+14 −1"),
        u.tool("Bash", "uv run pytest -q"), *u.result("13 passed in 1.42s", 11),
        BLANK,
        *agent(Text.assemble("Done. ", since, " defaults to yesterday and the tests pass.")),
    ]


def turn_screen() -> Rows:
    return [
        *echo(2, "add a --since flag to the metrics command"), *turn_body(), BLANK,
        u.heading("Changed"),
        *changed([("src/order_metrics/cli.py", "new option, ISO date, default yesterday"),
                  ("tests/test_cli.py", "two cases: explicit date, default")]),
        BLANK, u.facts("3 tools", "15.2s", "$0.0041"), BLANK,
        *footing(),
    ]


# ── 5 approval ───────────────────────────────────────────────────────────────
APPROVAL_OPTIONS = ["Yes", Text.assemble("Yes, and don't ask again for ", code("uv run"), " in this project"),
                    Text.assemble("No, and tell ds-next what to do differently", FACT_SEP, ("esc", "dim"))]


def approval_dialog(focus: int = 1) -> Rows:
    """Same shape as ui_style.dialog(), with styled option text (inline code chip, dim esc)."""
    rows: list[Text | None] = [Text("uv run pytest -q", "bold"), Text("Run the test suite to check the new flag", "muted"),
                               None, Text("PROCEED?", "bold")]
    for i, opt in enumerate(APPROVAL_OPTIONS, 1):
        mark, num = ((G.agent, "accent_text"), (str(i), "bold")) if i == focus else ((G.option, "dim"), (str(i), "muted"))
        rows.append(Text.assemble(mark, " ", num, FACT_SEP, opt))
    return u.frame(rows, edge="accent", title=Text("BASH COMMAND", "accent bold"))


def approval_screen() -> Rows:
    return [
        *agent("The flag parses. I want to run the suite to confirm nothing else moved."), BLANK,
        u.tool("Bash", "uv run pytest -q", state="running"), BLANK,
        *approval_dialog(), BLANK,
        *footing(PROJECT_HINT, "enter chooses  1-3 answer  esc declines"),
    ]


# ── 6 slash popup ────────────────────────────────────────────────────────────
COMMANDS = [("/status", "Project, canon and docs status"),
            ("/standards", "List the 16 standards and what applies here"),
            ("/skills", "Skills loaded from skills-os"),
            ("/scaffold", "Re-run a scaffold on the current project")]


def popup_screen(typed: str = "/s", selected: int = 0) -> Rows:
    items = [c for c in COMMANDS if c[0].startswith(typed)] or COMMANDS
    return [
        *agent(Text.assemble("Done. ", ("--since", "bold"), " defaults to yesterday and the tests pass.")), BLANK,
        u.facts("3 tools", "15.2s", "$0.0041"), BLANK,
        *box(typed=typed), *u.popup_rows(items, selected), status("↑↓ move  tab complete  esc close"),
    ]


# ── 7 /status ────────────────────────────────────────────────────────────────
def standards_row(items: list[tuple[str, str]], per_line: int = 4) -> Rows:
    """✓ in ink, ⚠ in accent. Wraps at the value column rather than past col 80."""
    out = []
    for start in range(0, len(items), per_line):
        val = Text()
        for i, (kind, name) in enumerate(items[start:start + per_line]):
            if i:
                val.append(FACT_SEP)
            val.append(getattr(G, kind), "accent" if kind != "ok" else "text").append(" " + name)
        out.append(u.labelled("standards" if start == 0 else "", val))
    return out


def status_screen(n: int = 3) -> Rows:
    std = [("ok", "python-package"), ("ok", "cli-ux"), ("ok", "logging"), ("ok", "testing"),
           ("warn", "security"), ("ok", "docs")]
    return [
        *echo(n, "/status"),
        Text.assemble("  ", ("order-metrics", "bold"), FACT_SEP, ("python-cli v1  ~/Developer/order-metrics", "muted")),
        BLANK,
        *standards_row(std),
        u.labelled("security", Text("1 finding: secrets read from env without a schema", "muted")),
        u.labelled("", Text("/explain security", "muted")),
        u.labelled("docs", FACT_SEP.join(["docs-ds", "3 pages", "built 2h ago"])),
        u.labelled("canon", FACT_SEP.join(["16 standards", "2 scaffolds", "up to date"])),
        u.labelled("session", FACT_SEP.join(["4 turns", "9 tools", "$0.0128", "ctx 34%"])),
        BLANK, *footing(),
    ]


SCREENS = {1: banner, 2: new_form, 3: working_screen, 4: turn_screen, 5: approval_screen, 6: popup_screen,
           7: status_screen}


# ── spec page mockups ────────────────────────────────────────────────────────
def label(s: str) -> Text:
    return Text(s, style="dim")


def message_types() -> Rows:
    """Spec §6: every message type, each under a dim caption."""
    return [
        label("turn rule · numbered, flush left · before every prompt"), u.turn_rule(4),
        label("you"), u.you("add a --since flag to the metrics command"), BLANK,
        label("thinking · dim, no italics, folds to one line"),
        u.thinking("The user wants an ISO date. Yesterday is the natural default because the", first=True),
        u.thinking("purpose line says daily metrics for finance…"), u.thought(3), BLANK,
        label("agent · ■ accent, text at col 3, headings uppercase, code on surface"),
        *agent(Text.assemble("I'll add ", ("--since", "bold"), " as an ISO date. Run ", code("uv run pytest"), " after.")),
        BLANK,
        label("tool + result · ▪ ink when done, └ result, fold aligned under it"),
        u.tool("Bash", "uv run pytest -q"), *u.result("13 passed in 1.42s", 11), BLANK,
        label("running tool · ▫ outline"),
        u.tool("Read", "src/order_metrics/cli.py", state="running"), *u.result("reading…"), BLANK,
        label("failed tool · the square and the first line go red"),
        u.tool("canon_read", "securty", state="failed"), *u.result("Error: securty is not a standard", error=True),
        Text("    did you mean security?", style="dim"), BLANK,
        label("working · one live line, quadrant spinner"), working("▘", "Drafting"), BLANK,
        label("outcomes · local commands · ink for done, red for anything that needs you"),
        u.outcome("ok", "order-metrics", "python-cli v1  6 standards applied"),
        u.outcome("warn", "security", "1 finding  /explain security"),
        u.outcome("err", "docs-ds", "not found  set DS_DOCS or run /docs"), BLANK,
        label("turn summary · dim, two-space columns, no separators"), u.facts("3 tools", "15.2s", "$0.0041"),
    ]


def grid_diagram() -> Rows:
    """Spec §5a: the 80-column grid, the turn rule, the four pinned rows."""
    return [
        Text("col 1 3 5" + " " * 67 + "80", style="dim"),
        Text("│ │ │" + " " * 72 + "│", style="rule"),
        u.turn_rule(1),
        Text.assemble((G.prompt, "accent_text"), " ", ("you — echoed flat after the turn rule", "bold")),
        Text.assemble((G.agent, "accent"), " ", ("agent text at col 3, wraps to col 3", "dim")),
        Text.assemble(G.tool, " ", ("Tool args — name bold, args muted, same row", "dim")),
        *u.result("result at col 5, under the tool name", 11),
        label("· thinking and its fold share col 1 with the squares"), BLANK,
        label("the footing · heavy square box · bare status row · always last"),
        *u.frame([Text.assemble((G.prompt, "accent_text"), " ", ("input · grows downward when wrapping", "dim"))]),
        status("? shortcuts", "model · cwd · ctx 34%  right-aligned"), BLANK,
        label("rhythm   a rule before every prompt · blank after it · none between tool and └"),
    ]


def rule_vs_canopy() -> Rows:
    """Spec §1b: the reference turn in Rule."""
    return [*echo(3, "add a --since flag to the metrics command"), *turn_body(), BLANK,
            u.heading("Changed"),
            *changed([("src/order_metrics/cli.py", "new option, ISO date, default yesterday"),
                      ("tests/test_cli.py", "two cases: explicit date, default")]),
            BLANK, u.facts("3 tools", "15.2s", "$0.0041"), BLANK, *footing()]


def dialog_reference() -> Rows:
    """Spec §7: permission dialog after an edit."""
    return [u.tool("Edit", "src/order_metrics/cli.py"), *u.result("+14 −1"), BLANK, *approval_dialog(), BLANK,
            *footing(PROJECT_HINT, "enter chooses  1-3 answer  esc declines")]
