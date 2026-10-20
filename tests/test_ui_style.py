"""The terminal design system's tokens: exact widths, roles that degrade, glyphs that stay."""
import os

from rich.console import Console
from rich.text import Text

from ds_next import ui_style as S


def width_of(line: Text) -> int:
    return line.cell_len


def test_frames_are_exact_at_80_and_60():
    for w in (80, 60):
        lines = S.frame("Allow scaffold_project?", [Text("purpose  − before"), None, Text("x" * 200)],
                        kind="approval", keys=Text(" y yes · n no"), w=w)
        assert all(width_of(ln) == w for ln in lines), [width_of(ln) for ln in lines]
        lines = S.frame("t", [], w=w)
        assert len(lines) == 2 and all(width_of(ln) == w for ln in lines)


def test_banner_is_exact_and_names_the_facts():
    lines = S.banner("v0.1.0", [("cwd", "~/x"), ("canon", "33 standards · 5 project types")],
                     ["/new starts a project"], "~/Developer/canon", "start, check and grow", w=80)
    assert all(width_of(ln) == 80 for ln in lines)
    text = "\n".join(ln.plain for ln in lines)
    assert "ds-next" in text and "33 standards" in text and "~/Developer/canon" in text


def test_lines_follow_the_grid():
    assert S.run("Bash", "uv run pytest -q").plain == "│ → Bash uv run pytest -q"
    assert S.result("13 passed", more=11).plain == "│   ⎿ 13 passed  ┄ 11 more lines · ctrl-o"
    assert S.result("ERROR: nope", error=True).plain == "│   ⎿ ERROR: nope"
    assert S.outcome("ok", "feed-model", "26 adopted").plain == "✓ feed-model  26 adopted"
    assert S.footer("#1", "3 turns", "15.2s").plain == "╰ #1 · 3 turns · 15.2s"
    assert S.labelled("pending", "llm-agents v1").plain == "  pending      llm-agents v1"
    assert S.error("x failed", "do y")[1].plain == "  do y"


def test_plain_mode_keeps_glyphs_and_drops_colour():
    con = Console(theme=S.theme(color=False), file=open(os.devnull, "w"), record=True, width=80)  # noqa: SIM115
    con.print(S.outcome("warn", "r", "1 pending"))
    assert con.export_text() == "⚠ r  1 pending\n"
    assert S.theme(color=False).styles["err"].color is None


def test_roles_fall_back_to_ansi_without_truecolor(monkeypatch):
    monkeypatch.delenv("COLORTERM", raising=False)
    assert S.theme().styles["accent"].color.name == "cyan"
    monkeypatch.setenv("COLORTERM", "truecolor")
    assert S.theme().styles["accent"].color.triplet.hex == "#94bce3"
    monkeypatch.setenv("DS_THEME", "light")
    assert S.theme().styles["accent"].color.triplet.hex == "#416180"
