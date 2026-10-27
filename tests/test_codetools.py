"""Code tools and Snowflake search wiring: offered only when installed, every code tool a read."""
import asyncio
import subprocess
from types import SimpleNamespace

from ds_next import agent, codetools


def fake_which(present):
    return lambda name: f"/bin/{name}" if name in present else None


def test_nothing_offered_when_nothing_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(codetools.shutil, "which", fake_which(set()))
    assert codetools.mcp_servers(tmp_path) == {} and codetools.read_only_ids({}) == set()
    assert "`code` tools" not in agent.code_tools(tmp_path)


def test_servers_and_approvals(monkeypatch, tmp_path, canon, skills):
    monkeypatch.setattr(codetools.shutil, "which", fake_which({"ds-code"}))
    monkeypatch.setattr(codetools, "os", SimpleNamespace(name="posix"))
    servers = codetools.mcp_servers(tmp_path)
    assert servers["code"] == {"type": "stdio", "command": "/bin/ds-code", "args": ["mcp", str(tmp_path.resolve())]}
    a = agent.Agent(tmp_path, ask_permission=lambda *x: asyncio.sleep(0, "asked"), canon=canon, skills=skills)
    opts = a.options()
    assert set(opts.mcp_servers) == {"ds", "code"} and opts.allowed_tools == []

    def permit(name):
        return asyncio.run(a._permit("MCP", {"resource": f"{name}\nInput: {{}}"}, None))

    for read in [f"mcp__code__{t}" for t in codetools.CODE_TOOLS] + ["mcp__ds__snowflake_search"]:
        assert permit(read).behavior == "allow", read
    assert permit("mcp__code__write_file") == "asked"          # only the eight tools ds-code serves
    assert "change_impact before finishing a change" in agent.code_tools(tmp_path)


def test_windows_starts_the_npm_shim_through_cmd(monkeypatch, tmp_path):
    monkeypatch.setattr(codetools.shutil, "which", fake_which({"ds-code"}))
    monkeypatch.setattr(codetools, "os", SimpleNamespace(name="nt"))       # this module only: pathlib reads os.name too
    server = codetools.mcp_servers(tmp_path)["code"]
    assert server["command"] == "cmd" and server["args"] == ["/c", "/bin/ds-code", "mcp", str(tmp_path.resolve())]


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

    monkeypatch.setattr(agent.sdk, "SDKClient", FakeClient)
    monkeypatch.setattr(codetools.shutil, "which", fake_which({"ds-code"}))
    a = agent.Agent(tmp_path, canon=canon, skills=skills)

    async def go():
        await a.connect()
        await a.close()
        return asyncio.current_task()

    task = asyncio.run(go())
    assert [t for _, t in seen] == [task, task]


class QuietClient:
    def __init__(self, options, gate=None):
        self.events = []

    async def connect(self):
        self.events.append("connect")

    async def query(self, prompt):
        pass

    async def receive_response(self):
        yield type("M", (), {"session_id": "s1"})()
        await asyncio.sleep(3600)

    async def interrupt(self):
        self.events.append("interrupt")

    async def disconnect(self):
        self.events.append("disconnect")


def test_a_silent_stream_stalls_but_an_approval_does_not(monkeypatch, tmp_path, canon, skills):
    monkeypatch.setattr(codetools.shutil, "which", fake_which(set()))
    made = []
    monkeypatch.setattr(agent.sdk, "SDKClient", lambda o: made.append(QuietClient(o)) or made[-1])
    a = agent.Agent(tmp_path, canon=canon, skills=skills)
    a.idle_timeout = 0.2

    async def drain():
        return [m async for m in a.turn("hi")]

    import pytest
    with pytest.raises(agent.TurnStalled):
        asyncio.run(asyncio.wait_for(drain(), 5))
    assert made[0].events == ["connect", "interrupt", "disconnect"] and a.options().resume == "s1"

    async def slow_person(name, inp, ctx):
        await asyncio.sleep(0.6)
        return "allowed"

    b = agent.Agent(tmp_path, ask_permission=slow_person, canon=canon, skills=skills)
    b.idle_timeout = 0.2

    class Asks(QuietClient):
        async def receive_response(self):
            yield type("M", (), {"session_id": "s1"})()
            await b._permit("Bash", {"resource": "ls"}, None)
            yield type("M", (), {"session_id": "s1"})()

    monkeypatch.setattr(agent.sdk, "SDKClient", lambda o: Asks(o))

    async def drain_b():
        return [m async for m in b.turn("hi")]

    assert len(asyncio.run(asyncio.wait_for(drain_b(), 5))) == 2
