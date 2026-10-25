import json

import pytest
from rule_cli import screens as S
from rule_cli import spec
from rule_cli import ui_style as u
from rule_cli.cli import main

MOCKS = {**{f"screen-{n}": fn for n, fn in S.SCREENS.items()}, "messages": S.message_types,
         "grid": S.grid_diagram, "versus": S.rule_vs_canopy, "dialog": S.dialog_reference}


@pytest.mark.parametrize("name", MOCKS)
def test_rows_fit_80_and_frames_are_exactly_80(name):
    for row in MOCKS[name]():
        assert row.cell_len <= u.DESIGN_WIDTH, row.plain
        if row.plain[:1] and row.plain[0] in "┏┃┗":
            assert row.cell_len == u.DESIGN_WIDTH, row.plain


def test_combined_roles_resolve():
    c = u.console(force_terminal=True)
    for combo in u.COMBOS:
        assert c.get_style(combo) != c.get_style("none"), combo


def test_turn_rule_numbers_flush_left():
    assert u.turn_rule(3).plain.startswith("━━ 03 ━")


def test_status_row_drops_cwd_when_keys_are_long():
    row = S.status("tab next  ←→ cycle  enter create  esc cancel").plain
    assert "~/Developer" not in row and row.endswith("claude-sonnet-4-5 · ctx 34%  ")


def test_spec_json_has_every_section(capsys):
    assert main(["spec", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert len(d["principles"]) == 8 and len(d["colour"]["roles"]) == 8 and len(d["screens"]) == 7
    assert d["mascot"]["pixels"] == u.MASCOT


def test_tour_runs_every_chapter(capsys):
    assert main(["tour", "--no-pause"]) == 0
    out = capsys.readouterr().out
    for title, *_ in spec.PRINCIPLES:
        assert title in out
    for n, title, _ in spec.SCREENS:
        assert title.upper() in out
