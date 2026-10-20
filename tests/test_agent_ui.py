"""The agent's tools (called directly, no model) and the terminal's rendering."""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cortex_agent_sdk.cortexcode import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from rich.console import Console

from ds_next import agent, reconcile
from ds_next.ui import describe_permission, render


def call(tools, name, args):
    t = next(t for t in tools if t.name == name)
    out = asyncio.run(t.handler(args))
    return out["content"][0]["text"], out.get("is_error", False)


def test_read_tools(tmp_path, canon, skills):
    tools = agent.tools(canon, skills, tmp_path)
    text, _ = call(tools, "canon_list", {"tags": "python,cli"})
    assert text.splitlines()[0].startswith("adr-000 v1")
    assert "error-handling" not in text
    assert call(tools, "canon_read", {"id": "testing"})[0].startswith("# Testing")
    assert call(tools, "canon_read", {"id": "nope"})[1] is True
    assert "so-capture:" in call(tools, "skills_list", {})[0]
    assert "not a ds repo" in call(tools, "project_status", {})[0]


def test_scaffold_tool_then_status(tmp_path, canon, skills):
    tools = agent.tools(canon, skills, tmp_path)
    listed, _ = call(tools, "scaffold_list", {})
    assert "python-cli v3 accepted type=cli outputs=none [python > cli]" in listed
    assert "ml-pipeline v3 accepted type=ml-pipeline outputs=model,features [ml-pipeline]" in listed
    got, _ = call(tools, "scaffold_get", {"id": "python-cli"})
    assert '"version": 3' in got and "About python-cli" in got
    stale, err = call(tools, "scaffold_project", {"scaffold": "python-cli", "scaffold_version": 2,
                                                  "name": "demo-cli", "purpose": "A demo"})
    assert err and "scaffold_get" in stale          # must fetch the accepted scaffold first
    text, err = call(tools, "scaffold_project", {"scaffold": "python-cli", "scaffold_version": 3,
                                                 "name": "demo-cli", "purpose": "A demo", "owner": "", "snowflake": ""})
    assert not err and "from python-cli v3" in text and "0 pending, 0 errors" in text
    status, _ = call(agent.tools(canon, skills, tmp_path / "demo-cli"), "project_status", {})
    assert '"adopted"' in status and "demo-cli" in status
    again, err = call(tools, "scaffold_project", {"scaffold": "python-cli", "scaffold_version": 3,
                                                  "name": "demo-cli", "purpose": "A demo"})
    assert err and "not empty" in again


def test_capture_writes_a_canon_shaped_draft(tmp_path, canon, skills):
    text, _ = call(agent.tools(canon, skills, tmp_path), "capture",
                   {"title": "SPCS images need linux/amd64", "body": "Build with --platform."})
    draft = tmp_path / ".ds" / "captures" / "spcs-images-need-linux-amd64.md"
    assert str(draft) in text
    assert "status: proposed" in draft.read_text() and "applies_to: [\"*\"]" in draft.read_text()


def test_system_prompt_names_the_parts(tmp_path, canon, skills):
    p = agent.system_prompt(tmp_path, canon, skills)
    assert "4 versioned standards" in p and "3 project scaffolds" in p and "2 procedures" in p
    assert "Never ask one question at a time" in p


def test_render_like_claude_code():
    con = Console(record=True, width=100, color_system=None)
    state: dict = {}
    render(con, AssistantMessage([TextBlock("Here are the **standards**."),
                                  ToolUseBlock("t1", "mcp__ds__canon_read", {"id": "testing"}),
                                  ToolUseBlock("t2", "bash", {"command": "uv run pytest -q"})], "m"), state)
    render(con, UserMessage([ToolResultBlock("t1", [{"type": "text", "text": "# Testing\nline2\nline3"}])]), state)
    render(con, ResultMessage("success", 1500, 1000, False, 2, "s"), state)
    out = con.export_text()
    assert "⏺ Here are the standards." in out
    assert "⏺ canon_read(testing)" in out and "⏺ Bash(uv run pytest -q)" in out
    assert "⎿  # Testing … +2 lines" in out and "2 turns · 1.5s" in out


def test_permission_payloads():
    # the shapes Cortex Code 1.2.14 actually sends to can_use_tool
    assert describe_permission("MCP", {"action": "execute_command",
                                       "resource": 'mcp__ds__scaffold_project\nInput: {\n "name": "x"\n}'}) \
        == ("scaffold_project", '{\n "name": "x"\n}')
    assert describe_permission("Bash", {"action": "execute_command", "resource": "echo hi"}) == ("Bash", "echo hi")


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("DS_LIVE") != "1", reason="set DS_LIVE=1 to call Cortex Code")
def test_live_one_shot_scaffold(tmp_path):
    """The whole loop through the real Cortex Code: the agent reads the canon, then scaffolds."""
    exe = Path(sys.executable).parent / "ds-next"
    prompt = ("Create a new project now from the python-cli scaffold: name live-demo, purpose "
              "'Prove ds-next end to end', owner tester, no Snowflake, no declines. It is already "
              "confirmed. Reply with one line.")
    r = subprocess.run([str(exe), "ask", "--yes", prompt], cwd=tmp_path, capture_output=True,
                       text=True, timeout=300, check=False)
    assert "scaffold_get" in r.stdout and "scaffold_project" in r.stdout, r.stdout + r.stderr
    rep = reconcile.check(tmp_path / "live-demo")
    assert rep.ok and not rep.pending


def test_permit_auto_allows_reads_and_asks_for_writes(tmp_path, canon, skills):
    asked = []

    async def ui(name, inp, ctx):
        asked.append(name)
        return "ui-decision"

    a = agent.Agent(tmp_path, ask_permission=ui, canon=canon, skills=skills)
    read = asyncio.run(a._permit("MCP", {"resource": "mcp__ds__canon_read\nInput: {}"}, None))
    assert read.behavior == "allow" and asked == []
    assert asyncio.run(a._permit("MCP", {"resource": "mcp__ds__scaffold_project\nInput: {}"}, None)) == "ui-decision"
    assert asyncio.run(a._permit("Bash", {"resource": "rm -rf /"}, None)) == "ui-decision"
    assert a.options().allowed_tools == []          # an allowlist would block everything else


def test_new_completes_the_scaffold_path(canon):
    from prompt_toolkit.document import Document

    from ds_next.ui import SlashCompleter
    c = SlashCompleter({}, canon.scaffolds)
    words = lambda t: [x.text for x in c.get_completions(Document(t), None)]
    assert words("/new ") == ["python", "ml-pipeline"]
    assert words("/new python ") == ["cli", "draft"]
    assert words("/new python c") == ["cli"]
    assert words("/ne") == ["/new"]


def test_form_approval_covers_only_the_submitted_draft():
    from ds_next.ui import changed_keys, same_draft
    draft = {"scaffold": "python-package", "name": "clark-test", "purpose": "python project", "owner": "ck",
             "test_cmd": "uv run pytest -q"}
    assert same_draft(draft, {**draft, "scaffold_version": 1, "snowflake": "", "tags": []})
    # what the model did once: swapped in its own example purpose
    invented = {**draft, "scaffold_version": 1, "purpose": "Shared utilities for data pipeline orchestration"}
    assert not same_draft(draft, invented) and changed_keys(draft, invented) == ["purpose"]


def test_asks_detects_questions_with_trailing_examples():
    from ds_next.ui import asks
    assert asks('What does this package do? One line is enough (e.g., "CLI tool for X").')
    assert asks("Create it?")
    assert not asks("Project created at clark-test/. 16 standards adopted.")


def test_tool_names_from_other_servers():
    from ds_next.ui import _short
    assert (_short("mcp__ds__canon_read"), _short("mcp__graph__trace_path"), _short("bash")) == (
        "canon_read", "graph.trace_path", "Bash")
