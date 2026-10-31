"""`decide`: the one writer of [standards.*] tables, as a function, a command and an agent tool."""
import asyncio
import datetime as dt
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ds_next import agent, cli, reconcile

TODAY = dt.date(2026, 10, 30)


def repo_with(tmp_path: Path, extra: str = "") -> Path:
    repo = tmp_path / "shop"
    (repo / ".ds").mkdir(parents=True)
    (repo / ".ds" / "manifest.toml").write_text(
        '[repo]\nname = "shop"\ntags = ["python", "package"]\ncreated = "2026-10-30"\n' + extra)
    return repo


def manifest(repo: Path) -> dict:
    return tomllib.loads((repo / ".ds" / "manifest.toml").read_text())


def test_adopt_and_decline_are_recorded_and_reconcile_sees_them(tmp_path, canon):
    repo = repo_with(tmp_path)
    assert reconcile.decide(repo, "adopt", ["testing", "adr-000"], by="Ann", canon=canon, today=TODAY) == ["testing", "adr-000"]
    assert reconcile.decide(repo, "decline", ["error-handling"], by="Ann", canon=canon, today=TODAY,
                            reason="  pinned to the old  handler until Q1 ") == ["error-handling"]
    m = manifest(repo)
    assert m["standards"]["testing"] == {"status": "adopted", "version": 1, "by": "Ann", "on": "2026-10-30"}
    assert m["standards"]["error-handling"] == {"status": "declined", "version": 1, "by": "Ann", "on": "2026-10-30",
                                                "reason": "pinned to the old handler until Q1", "revisit": "2027-01-28"}
    rep = reconcile.check(repo, canon, TODAY)
    assert rep.ok and sorted(rep.adopted) == ["adr-000", "testing"] and rep.declined == {"error-handling": "pinned to the old handler until Q1"}
    assert rep.pending == []                                   # idempotency does not apply to a package


def test_all_pending_takes_the_rest_and_skips_blocks(tmp_path, canon):
    repo = repo_with(tmp_path, '\n[standards.testing]\nstatus = "adopted"\nversion = 1\nby = "Ann"\non = "2026-10-30"\n'
                               '\n[blocks.block-demo]\nversion = 1\n')
    pending_before = reconcile.check(repo, canon, TODAY).pending
    assert pending_before == ["adr-000 v1", "error-handling v1"]
    done = reconcile.decide(repo, "adopt", [], by="Ann", canon=canon, today=TODAY, all_pending=True)
    assert done == ["adr-000", "error-handling"]
    rep = reconcile.check(repo, canon, TODAY)
    assert rep.pending == [] and rep.blocks == ["block-demo v1"]
    with pytest.raises(ValueError, match="name the standards"):
        reconcile.decide(repo, "adopt", [], by="Ann", canon=canon, today=TODAY, all_pending=True)   # nothing left


def test_an_existing_table_is_replaced_in_place_and_nothing_else_moves(tmp_path, canon):
    repo = repo_with(tmp_path, '\n[standards.testing]\nstatus = "declined"\nversion = 1\nby = "Bo"\non = "2026-10-01"\n'
                               'reason = "old"\nrevisit = "2026-12-01"\n\n[uses]\ncanon = ["index.json"]\n')
    reconcile.decide(repo, "adopt", ["testing"], by="Ann", canon=canon, today=TODAY)
    text = (repo / ".ds" / "manifest.toml").read_text()
    assert text.count("[standards.testing]") == 1 and "reason" not in text and '\n\n[uses]\ncanon = ["index.json"]\n' in text
    assert manifest(repo)["standards"]["testing"]["by"] == "Ann"
    reconcile.decide(repo, "decline", ["testing"], by="Ann", canon=canon, today=TODAY, reason="no", revisit="2027-03-01")
    assert manifest(repo)["standards"]["testing"]["revisit"] == "2027-03-01"


def test_refusals_write_nothing(tmp_path, canon):
    repo = repo_with(tmp_path)
    before = (repo / ".ds" / "manifest.toml").read_text()
    for kwargs, why in [
        ({"action": "adopt", "ids": ["nope", "testing"]}, "not in the canon: nope"),
        ({"action": "adopt", "ids": []}, "name the standards"),
        ({"action": "decline", "ids": ["testing"]}, "a decline needs a reason"),
        ({"action": "decline", "ids": ["testing"], "reason": "x", "revisit": "soon"}, "revisit must be a date like 2027-01-28"),
        ({"action": "keep", "ids": ["testing"]}, "adopt or decline"),
        ({"action": "adopt", "ids": ["testing"], "by": ""}, "by: who decides"),
    ]:
        kwargs.setdefault("by", "Ann")
        with pytest.raises(ValueError, match=why):
            reconcile.decide(repo, canon=canon, today=TODAY, **kwargs)
    assert (repo / ".ds" / "manifest.toml").read_text() == before
    with pytest.raises(ValueError, match="no .ds/manifest.toml"):
        reconcile.decide(tmp_path, "adopt", ["testing"], by="Ann", canon=canon, today=TODAY)


def test_cli_decide(tmp_path, canon, monkeypatch):
    repo = repo_with(tmp_path)
    monkeypatch.setenv("DS_CANON", str(canon.root))
    monkeypatch.setattr(cli.scaffold, "_git_user", lambda: "Ann")
    r = CliRunner().invoke(cli.app, ["decide", "adopt", "testing", "adr-000", "--path", str(repo)])
    assert r.exit_code == 0, r.output
    assert "adopted testing, adr-000" in r.output and "2 adopted" in r.output
    r = CliRunner().invoke(cli.app, ["decide", "decline", "error-handling", "--path", str(repo)])
    assert r.exit_code == 2 and "a decline needs a reason" in r.output
    r = CliRunner().invoke(cli.app, ["decide", "decline", "error-handling", "--reason", "later", "--path", str(repo)])
    assert r.exit_code == 0 and "1 declined" in r.output
    r = CliRunner().invoke(cli.app, ["decide", "adopt", "--all", "--path", str(tmp_path)])
    assert r.exit_code == 2 and "not a ds repo" in r.output
    assert manifest(repo)["standards"]["error-handling"]["by"] == "Ann"


def call(tools, name, args):
    t = next(t for t in tools if t.name == name)
    out = asyncio.run(t.handler(args))
    return out["content"][0]["text"], out.get("is_error", False)


def test_decide_standard_tool_writes_and_asks(tmp_path, canon, skills, monkeypatch):
    repo = repo_with(tmp_path)
    monkeypatch.setattr(agent.scaffold, "_git_user", lambda: "Ann")
    assert "decide_standard" in agent.WRITES and "mcp__ds__decide_standard" not in agent.READ_ONLY_IDS
    tools = agent.tools(canon, skills, repo)
    text, err = call(tools, "decide_standard", {"action": "adopt", "ids": "testing, adr-000"})
    assert not err and text.startswith("adopted testing, adr-000 in") and "still pending: error-handling v1" in text
    text, err = call(tools, "decide_standard", {"action": "decline", "ids": ["error-handling"]})
    assert err and "a decline needs a reason" in text
    text, err = call(tools, "decide_standard", {"action": "decline", "all": True, "reason": "not for a library"})
    assert not err and "declined error-handling" in text and "still pending" not in text
    assert manifest(repo)["standards"]["error-handling"]["reason"] == "not for a library"
    text, err = call(agent.tools(canon, skills, tmp_path), "decide_standard", {"action": "adopt", "ids": ["testing"]})
    assert err and "not a ds repo" in text
