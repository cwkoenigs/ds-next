"""Codex as the third agent: the client against a stand-in app-server (tests/fake_codex.py), the pieces
on their own, and, where Codex is installed, the real app-server with a stand-in model. The client
speaks claude-agent-sdk's types (`types` here), whichever agent `sdk` found on this machine."""
import asyncio
import json
import os
import shutil
import sys
import textwrap
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import claude_agent_sdk as types
import pytest

from ds_next import agent, codex, sdk, ui
from ds_next.codex import CodexClient, file_change, shell_command

FAKE = Path(__file__).with_name("fake_codex.py")


@pytest.fixture
def as_codex(monkeypatch):
    """The terminal with Codex as its agent, whatever this machine runs."""
    monkeypatch.setattr(sdk, "BACKEND", "codex")
    monkeypatch.setattr(sdk, "LABEL", "Codex")
    monkeypatch.setattr(sdk, "SDKClient", CodexClient)
    monkeypatch.setattr(agent.codetools, "code_bin", lambda: None)     # the code tools have a test of their own


@pytest.fixture
def fake(monkeypatch, tmp_path, as_codex):
    log = tmp_path / "log.jsonl"
    monkeypatch.setattr(codex, "command", lambda: [sys.executable, str(FAKE)])
    monkeypatch.setenv("FAKE_CODEX_LOG", str(log))
    return lambda method: [m for m in map(json.loads, log.read_text().splitlines())
                           if m.get("method") == method or (method == "reply" and "method" not in m)]


def turn(a, prompt="run the tests"):
    seen = {}

    async def go():
        try:
            return [m async for m in a.turn(prompt)]
        finally:
            seen["stderr"] = getattr(a._client, "_log", "")
            await a.close()
    try:
        return asyncio.run(asyncio.wait_for(go(), 20))
    except TimeoutError as e:        # say what the agent did, since nothing else will
        log = os.environ.get("FAKE_CODEX_LOG", "")
        received = Path(log).read_text()[-3000:] if log and Path(log).is_file() else ""
        raise AssertionError(f"no result in 20s\nthe agent's stderr: {seen.get('stderr')!r}\nit received:\n{received}") from e


def answering(answer):
    asked = []

    async def ask(name, inp, ctx):
        asked.append((name, inp))
        return answer
    return ask, asked


def test_a_turn_through_codex(fake, tmp_path, canon, skills):
    ask, asked = answering(sdk.PermissionResultAllow())
    a = agent.Agent(tmp_path, ask_permission=ask, canon=canon, skills=skills)
    msgs = turn(a)
    kinds = [type(m).__name__ for m in msgs]
    assert kinds == ["SystemMessage", "AssistantMessage", "AssistantMessage", "AssistantMessage", "UserMessage",
                     "AssistantMessage", "UserMessage", "AssistantMessage", "ResultMessage"]
    assert msgs[0].data == {"model": "gpt-test", "session_id": "thread-1"}
    assert msgs[3].content[0].name == "mcp__ds__canon_list" and msgs[3].content[0].input == {"tags": "python"}
    assert not msgs[4].content[0].is_error and "testing" in msgs[4].content[0].content      # the fixture canon, read in process
    assert msgs[5].content[0].name == "Bash" and msgs[5].content[0].input == {"command": "npm test"}
    assert msgs[6].content[0].content.startswith("78 passed")
    result = msgs[-1]
    assert (result.subtype, result.is_error, result.usage, result.session_id) == ("success", False, {"total_tokens": 45230}, "thread-1")
    assert asked == [("Bash", {"command": "npm test", "description": "Run the tests"})]      # canon_list only reads: never asks
    assert a.session_id == "thread-1"

    [init] = fake("initialize")
    assert init["params"]["capabilities"]["experimentalApi"] is True
    [thread] = fake("thread/start")
    p = thread["params"]
    assert (p["approvalPolicy"], p["sandbox"]) == ("untrusted", "workspace-write")
    assert "front door to the team's knowledge system" in p["developerInstructions"]
    assert {t["name"] for t in p["dynamicTools"]} >= {"canon_read", "scaffold_project", "capture"}
    assert {k: v["enabled"] for k, v in p["config"]["mcp_servers"].items()} == {"ds": False, "code": False}     # never served twice
    replies = [r["result"] for r in fake("reply")]
    assert replies[0]["success"] is True and replies[1] == {"decision": "accept"}


def test_a_no_declines_and_lets_the_model_ask(fake, tmp_path, canon, skills):
    ask, _ = answering(sdk.PermissionResultDeny(message="The user declined this call. Ask what to do instead."))
    msgs = turn(agent.Agent(tmp_path, ask_permission=ask, canon=canon, skills=skills))
    assert fake("reply")[-1]["result"] == {"decision": "decline"}
    declined = [b for m in msgs if isinstance(m, types.UserMessage) for b in m.content][-1]
    assert declined.is_error and declined.content == "declined"
    assert msgs[-1].is_error is False          # the turn stopped there; nothing failed


def test_a_no_that_interrupts_cancels(fake, tmp_path, canon, skills):
    ask, _ = answering(sdk.PermissionResultDeny(message="stop", interrupt=True))
    turn(agent.Agent(tmp_path, ask_permission=ask, canon=canon, skills=skills))
    assert fake("reply")[-1]["result"] == {"decision": "cancel"}


def test_a_turn_codex_never_confirms_ends_the_session(fake, monkeypatch, tmp_path, canon, skills):
    monkeypatch.setenv("FAKE_CODEX_SILENT_TURN", "1")
    monkeypatch.setattr(codex, "REQUEST_TIMEOUT", 0.5)
    a = agent.Agent(tmp_path, canon=canon, skills=skills)
    with pytest.raises(types.ClaudeSDKError, match="longer than 0.5s to answer turn/start"):
        turn(a)
    assert not a.connected


def test_the_code_tools_reach_codex_through_their_server(tmp_path):
    """A stdio MCP server's tools become dynamic tools; a read-only one runs without asking."""
    server = tmp_path / "code_server.py"
    server.write_text(textwrap.dedent('''
        from mcp.server.fastmcp import FastMCP
        app = FastMCP("code")

        @app.tool()
        def references(name: str) -> str:
            """Every use of a symbol."""
            return f"{name} is used in 2 places"

        app.run()
    '''))
    asked = []

    async def ask(name, inp, ctx):
        asked.append(name)
        return sdk.PermissionResultAllow()

    opts = codex.CodexOptions(cwd=str(tmp_path), mcp_servers={"code": {"type": "stdio", "command": sys.executable, "args": [str(server)]}},
                              system_prompt="", can_use_tool=ask, read_only={"mcp__code__references"})

    async def go():
        c = CodexClient(opts)
        try:
            specs = await c._serve()
            r = await c._request("item/tool/call", {"tool": "references", "arguments": {"name": "greet"}})
            return specs, r, c._tool_call({"type": "dynamicToolCall", "tool": "references", "arguments": {"name": "greet"}})
        finally:
            await c.disconnect()

    specs, r, call = asyncio.run(asyncio.wait_for(go(), 30))
    assert [s["name"] for s in specs] == ["references"] and specs[0]["inputSchema"]["properties"]["name"]["type"] == "string"
    assert r == {"success": True, "contentItems": [{"type": "inputText", "text": "greet is used in 2 places"}]}
    assert call == ("mcp__code__references", {"name": "greet"})
    assert asked == []


def test_the_pieces():
    assert sdk.LABELS["codex"] == "Codex" and "codex" in sdk.BACKENDS
    assert shell_command("/bin/bash -lc 'npm test'") == "npm test"
    assert shell_command("/bin/zsh -lc 'echo '\\''hi'\\'''") == "echo 'hi'"
    assert shell_command('bash -c "echo \\"x\\""') == 'echo "x"'
    assert shell_command("npm test") == "npm test"
    assert file_change([{"path": "src/a.ts", "kind": {"type": "update", "move_path": None}, "diff": "@@\n-old\n+new\n+more"}]) == \
        ("Edit", {"file_path": "src/a.ts", "old_string": "old", "new_string": "new\nmore"})
    assert file_change([{"path": "b.md", "kind": {"type": "add", "move_path": None}, "diff": "+hello"}]) == ("Write", {"file_path": "b.md", "content": "hello"})
    name, inp = file_change([{"path": "/w/safe.txt", "kind": {"type": "update", "move_path": None}, "diff": "@@\n-a\n+b"},
                             {"path": "/w/sensitive.txt", "kind": {"type": "delete", "move_path": None}, "diff": ""},
                             {"path": "/w/old.ts", "kind": {"type": "update", "move_path": "/w/new.ts"}, "diff": ""}])
    title, detail = ui.describe_permission(name, inp)
    assert [title, *detail.splitlines()[:3]] == ["Edit", "update /w/safe.txt", "delete /w/sensitive.txt", "update /w/old.ts → /w/new.ts"]


def test_where_codex_is_found(monkeypatch, tmp_path):
    monkeypatch.delenv("CODEX_CLI_PATH", raising=False)
    monkeypatch.setattr(codex.shutil, "which", lambda name: None)
    with pytest.raises(types.CLINotFoundError, match="Codex CLI not found"):
        codex.command()
    shim = tmp_path / "codex.CMD"
    shim.write_text("")
    monkeypatch.setenv("CODEX_CLI_PATH", str(shim))
    assert codex.command() == ["cmd", "/c", str(shim), "app-server"]      # npm's shim on Windows


# ---------------------------------------------------------------- the real app-server

class StandIn(BaseHTTPRequestHandler):
    """A stand-in for the Responses API Codex calls: the first request gets one tool call back, the
    next, carrying the tool's output, a short reply."""
    call: dict = {}
    outputs: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        if not self.path.endswith("/responses"):
            self.send_response(404)
            self.end_headers()
            return
        done = [i for i in body.get("input", []) if i.get("type") == "function_call_output"]
        StandIn.outputs += [i["output"] if isinstance(i.get("output"), str) else json.dumps(i.get("output")) for i in done]
        item = ({"type": "message", "id": "msg_2", "role": "assistant", "status": "completed",
                 "content": [{"type": "output_text", "text": "Done.", "annotations": []}]} if done else
                {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": StandIn.call["name"],
                 "arguments": json.dumps(StandIn.call["arguments"]), "status": "completed"})
        rid = "resp_2" if done else "resp_1"
        usage = {"input_tokens": 100, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 20,
                 "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 120}
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        for e in [{"type": "response.created", "response": {"id": rid, "object": "response", "status": "in_progress", "output": []}},
                  {"type": "response.output_item.added", "output_index": 0, "item": {**item, "status": "in_progress"}},
                  {"type": "response.output_item.done", "output_index": 0, "item": item},
                  {"type": "response.completed", "response": {"id": rid, "object": "response", "status": "completed", "output": [item], "usage": usage}}]:
            self.wfile.write(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def real_codex(monkeypatch, tmp_path, as_codex):
    if not shutil.which("codex"):
        pytest.skip("Codex is not installed")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), StandIn)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "config.toml").write_text(f'model = "stand-in"\nmodel_provider = "stand-in"\n\n[model_providers.stand-in]\n'
                                      f'name = "stand-in"\nbase_url = "http://127.0.0.1:{httpd.server_port}/v1"\nwire_api = "responses"\n')
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.delenv("CODEX_CLI_PATH", raising=False)
    StandIn.outputs = []

    def play(call, a):
        StandIn.call = call
        return turn(a, "go"), StandIn.outputs
    yield play
    httpd.shutdown()


def test_the_real_app_server_calls_a_ds_tool_without_asking(real_codex, tmp_path, canon, skills):
    ask, asked = answering(sdk.PermissionResultAllow())
    msgs, outputs = real_codex({"name": "canon_list", "arguments": {}}, agent.Agent(tmp_path, ask_permission=ask, canon=canon, skills=skills))
    calls = [b for m in msgs if isinstance(m, types.AssistantMessage) for b in m.content if isinstance(b, types.ToolUseBlock)]
    assert [c.name for c in calls] == ["mcp__ds__canon_list"]
    assert asked == [] and "testing" in outputs[0]           # what the model got back: the fixture canon
    assert msgs[-1].subtype == "success" and msgs[-1].usage == {"total_tokens": 120}


@pytest.mark.skipif(sys.platform == "win32", reason="the command is a POSIX one")
@pytest.mark.parametrize("answer, made", [("yes", True), ("no", False)])
def test_the_real_app_server_asks_before_a_command(real_codex, tmp_path, canon, skills, answer, made):
    allow = sdk.PermissionResultAllow() if answer == "yes" else sdk.PermissionResultDeny(message="declined")
    ask, asked = answering(allow)
    msgs, _ = real_codex({"name": "exec_command", "arguments": {"cmd": "touch made-by-codex.txt"}},
                         agent.Agent(tmp_path, ask_permission=ask, canon=canon, skills=skills))
    assert [n for n, _ in asked] == ["Bash"] and asked[0][1]["command"] == "touch made-by-codex.txt"
    assert (tmp_path / "made-by-codex.txt").exists() is made
    assert msgs[-1].is_error is False
