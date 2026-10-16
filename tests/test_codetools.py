"""Code graph, LSP and Snowflake search wiring: offered only when installed, reads approved, edits asked."""
import asyncio
import subprocess

from ds_next import agent, codetools


def fake_which(present):
    return lambda name: f"/bin/{name}" if name in present else None


def test_nothing_offered_when_nothing_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(codetools.shutil, "which", fake_which(set()))
    assert codetools.mcp_servers(tmp_path) == {} and codetools.read_only_ids({}) == set()
    assert "not installed" in codetools.index(tmp_path)
    assert "graph" not in agent.code_tools(tmp_path)


def test_servers_and_approvals(monkeypatch, tmp_path, canon, skills):
    monkeypatch.setattr(codetools.shutil, "which", fake_which({"codebase-memory-mcp", "serena"}))
    servers = codetools.mcp_servers(tmp_path)
    assert servers["graph"]["args"] == ["--tool-profile=analysis"]          # the read-only surface
    assert str(tmp_path.resolve()) in servers["lsp"]["args"]
    a = agent.Agent(tmp_path, ask_permission=lambda *x: asyncio.sleep(0, "asked"), canon=canon, skills=skills)
    opts = a.options()
    assert set(opts.mcp_servers) == {"ds", "graph", "lsp"} and opts.allowed_tools == []

    def permit(name):
        return asyncio.run(a._permit("MCP", {"resource": f"{name}\nInput: {{}}"}, None))

    for read in ("mcp__graph__search_graph", "mcp__graph__trace_path", "mcp__lsp__find_referencing_symbols",
                 "mcp__ds__snowflake_search"):
        assert permit(read).behavior == "allow", read
    for edit in ("mcp__lsp__rename_symbol", "mcp__lsp__replace_symbol_body", "mcp__lsp__write_memory",
                 "mcp__lsp__safe_delete_symbol", "mcp__graph__index_repository"):
        assert permit(edit) == "asked", edit
    assert "find_referencing_symbols" in agent.code_tools(tmp_path)
    assert codetools.graph_project(tmp_path) in agent.code_tools(tmp_path)


def test_graph_project_name_matches_codebase_memory():
    assert codetools.graph_project("/Users/x/Developer/ds-rebuild") == "Users-x-Developer-ds-rebuild"


def test_index_summary_and_failures(monkeypatch, tmp_path):
    monkeypatch.setattr(codetools.shutil, "which", fake_which({"codebase-memory-mcp"}))
    assert "not a git repository" in codetools.index(tmp_path)
    (tmp_path / ".git").mkdir()
    out = '{"project": "p", "nodes": 345, "edges": 1113}'
    monkeypatch.setattr(codetools.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out, ""))
    assert codetools.index(tmp_path) == "graph: 345 symbols, 1113 edges in p"
    monkeypatch.setattr(codetools.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "boom"))
    assert "failed: boom" in codetools.index(tmp_path)


def test_snowflake_search(monkeypatch):
    monkeypatch.setattr(codetools.shutil, "which", fake_which({"cortex"}))
    assert codetools.snowflake_search("sql; rm -rf /", "x")[1] is True        # only the three kinds
    calls = []

    def run(cmd, **k):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, '{"results": "Found 1 result"}', "")

    monkeypatch.setattr(codetools.subprocess, "run", run)
    assert codetools.snowflake_search("docs", "dynamic tables", "conn") == ("Found 1 result", False)
    assert calls[0][1:] == ["search", "docs", "dynamic tables", "--connection", "conn"]


def test_connect_and_close_happen_in_the_callers_task(monkeypatch, tmp_path, canon, skills):
    """The SDK's task group must be entered and exited in one task; gather() once broke that."""
    seen = []

    class FakeClient:
        def __init__(self, options):
            pass

        async def connect(self):
            seen.append(("connect", asyncio.current_task()))

        async def disconnect(self):
            seen.append(("disconnect", asyncio.current_task()))

    monkeypatch.setattr(agent, "CortexCodeSDKClient", FakeClient)
    monkeypatch.setattr(codetools.shutil, "which", fake_which({"codebase-memory-mcp"}))
    monkeypatch.setattr(codetools, "index", lambda repo: "graph: indexed")
    (tmp_path / ".git").mkdir()
    a = agent.Agent(tmp_path, canon=canon, skills=skills)

    async def go():
        await a.connect()
        await a.close()
        return asyncio.current_task()

    task = asyncio.run(go())
    assert [t for _, t in seen] == [task, task] and a.index_summary == "graph: indexed"
