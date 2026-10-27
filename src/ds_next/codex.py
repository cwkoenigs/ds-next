"""Codex as the terminal's third agent: the codex CLI's app-server, JSON-RPC over stdin and stdout, the
protocol OpenAI's editor extensions use.

Unlike `codex exec`, the app-server asks before a command runs or a file changes, and it calls tools
the client serves. So every tool reaches Codex as a "dynamic tool" served from here: ds-next's own (its
in-process MCP server, called through the server's handlers) and the code tools (ds-code, through an
MCP client session). Each call goes through the same can_use_tool as with the other agents.

CodexClient has the SDK clients' shape (connect, query, receive_response, interrupt, set_model,
disconnect) and turns Codex's notifications into the SDK's message types, so nothing else changes.
The app-server and its dynamic tools are marked experimental: upgrading Codex means re-running
tests/test_codex.py, whose last tests drive the real binary.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    CLINotFoundError,
    PermissionResultAllow,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from claude_agent_sdk import ClaudeSDKError as SDKError
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

Obj = dict[str, Any]
REQUEST_TIMEOUT = 60.0        # seconds a request waits for Codex; the tests set less


def command() -> list[str]:
    """How to start the app-server: CODEX_CLI_PATH, else `codex` on PATH. npm installs it on Windows as
    a .cmd shim, which only starts through cmd."""
    path = os.environ.get("CODEX_CLI_PATH") or shutil.which("codex")
    if not path or not Path(path).exists():
        raise CLINotFoundError("Codex CLI not found: install it (npm install -g @openai/codex) or set CODEX_CLI_PATH")
    return (["cmd", "/c", path] if Path(path).suffix.lower() in (".cmd", ".bat") else [path]) + ["app-server"]


@dataclass
class CodexOptions:
    """What a Codex session needs; sdk.options builds it from the terminal's one set of values."""
    cwd: str
    mcp_servers: dict[str, Any]
    system_prompt: str
    can_use_tool: Any
    model: str | None = None
    effort: str | None = None
    resume: str | None = None
    read_only: frozenset[str] | set[str] = field(default_factory=frozenset)


def shell_command(cmd: str) -> str:
    """Codex runs a command through a login shell; `/bin/bash -lc 'npm test'` reads as `npm test`."""
    m = re.match(r"""^(?:\S*/)?(?:bash|zsh|sh)\s+-l?c\s+(['"])([\s\S]*)\1$""", cmd.strip())
    if not m:
        return cmd
    return m[2].replace("'\\''", "'") if m[1] == "'" else re.sub(r'\\(["\\$`])', r"\1", m[2])


def _str(v: Any) -> str:
    return v if isinstance(v, str) else ""


def file_change(changes: Any) -> tuple[str, Obj]:
    """A file change as Claude Code names it: Write for one new file, else Edit with its old and new
    lines. A patch over several files, or one that deletes or moves a file, also lists each file and
    what happens to it, so the approval names every one."""
    items = changes if isinstance(changes, list) else []
    first = items[0] if items else {}
    files = []
    for c in items:
        kind = c.get("kind") or {}
        to = _str(kind.get("move_path"))
        files.append({"kind": _str(kind.get("type")) or "update", "path": _str(c.get("path")), **({"to": to} if to else {})})
    plain = len(files) == 1 and files[0]["kind"] in ("add", "update") and "to" not in files[0]
    diff = "\n".join(_str(c.get("diff")) for c in items).split("\n")
    added = "\n".join(line[1:] for line in diff if line.startswith("+") and not line.startswith("+++"))
    removed = "\n".join(line[1:] for line in diff if line.startswith("-") and not line.startswith("---"))
    path = _str(first.get("path"))
    if plain and files[0]["kind"] == "add":
        return "Write", {"file_path": path, "content": added}
    return "Edit", {"file_path": path, **({} if plain else {"files": files}), "old_string": removed, "new_string": added}


def _content_text(content: Any) -> str:
    return "\n".join(_str(c.get("text")) for c in content if isinstance(c, dict) and c.get("text")) if isinstance(content, list) else ""


class AppServer:
    """One JSON-RPC connection: requests out with awaited replies; notifications and Codex's own
    requests in, each handled by the callbacks given."""

    def __init__(self, proc: asyncio.subprocess.Process, on_notification, on_request, timeout: float | None = None):
        self.proc = proc
        self.on_notification = on_notification
        self.on_request = on_request
        self.timeout = REQUEST_TIMEOUT if timeout is None else timeout
        self._next = 1
        self._waiting: dict[int, asyncio.Future] = {}
        self._tasks: set[asyncio.Task] = set()
        self._reader = asyncio.ensure_future(self._read())

    async def request(self, method: str, params: Obj) -> Obj:
        """A request and its reply. One that never comes fails after `timeout`: a Codex that stays up
        but stops answering would otherwise hold the session's start, or an interrupt, for good."""
        rid, self._next = self._next, self._next + 1
        fut = asyncio.get_running_loop().create_future()
        self._waiting[rid] = fut
        await self._write({"id": rid, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, self.timeout)
        except asyncio.TimeoutError:
            raise SDKError(f"Codex took longer than {self.timeout:g}s to answer {method}") from None
        finally:
            self._waiting.pop(rid, None)

    async def notify(self, method: str, params: Obj | None = None) -> None:
        await self._write({"method": method, **({"params": params} if params is not None else {})})

    async def _write(self, m: Obj) -> None:
        stdin = self.proc.stdin
        if stdin is None or stdin.is_closing():
            return
        stdin.write((json.dumps(m) + "\n").encode())
        with contextlib.suppress(ConnectionError):
            await stdin.drain()

    async def _read(self) -> None:
        assert self.proc.stdout is not None
        while line := await self.proc.stdout.readline():
            try:
                m = json.loads(line)
            except ValueError:
                continue                     # not protocol: ignore
            if "method" not in m:
                fut = self._waiting.get(m.get("id"))
                if fut is not None and not fut.done():
                    if m.get("error"):
                        fut.set_exception(SDKError((m["error"] or {}).get("message") or "Codex refused the request"))
                    else:
                        fut.set_result(m.get("result") or {})
            elif "id" in m:
                t = asyncio.ensure_future(self._answer(m["id"], m["method"], m.get("params") or {}))
                self._tasks.add(t)
                t.add_done_callback(self._tasks.discard)
            else:
                self.on_notification(m["method"], m.get("params") or {})
        for fut in self._waiting.values():  # the process is gone: nothing waiting will be answered
            if not fut.done():
                fut.set_exception(SDKError("Codex stopped"))

    async def _answer(self, rid: Any, method: str, params: Obj) -> None:
        try:
            await self._write({"id": rid, "result": await self.on_request(method, params)})
        except Exception as e:        # noqa: BLE001 - every failure is answered, so Codex never waits for good
            await self._write({"id": rid, "error": {"code": -32603, "message": str(e)}})

    async def close(self) -> None:
        """Once the process is gone: stop answering, and let the reader see the end of its output."""
        for t in self._tasks:
            t.cancel()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self._reader, 2)


class CodexClient:
    """A Codex session with the SDK clients' interface."""

    def __init__(self, options: CodexOptions):
        self.o = options
        self.model = options.model
        self._proc: asyncio.subprocess.Process | None = None
        self._rpc: AppServer | None = None
        self._stack = contextlib.AsyncExitStack()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._tools: dict[str, tuple[str, Any]] = {}    # tool name: (server, how to call it)
        self._items: dict[str, Obj] = {}                  # tool items by id, for the approval that follows
        self.thread_id = ""
        self._turn_id = ""
        self._started = 0.0
        self._tokens: int | None = None
        self._error = ""
        self._log = ""                 # the end of Codex's stderr, read as it comes so the pipe never fills
        self._drain: asyncio.Task | None = None

    # -- the tools Codex is given

    async def _serve(self) -> list[Obj]:
        """Every MCP server's tools as dynamic tools: an in-process server through its own handlers, a
        stdio server through a client session kept open for the session. One that does not start is
        left out; the first server to name a tool keeps it."""
        specs: list[Obj] = []
        for server, cfg in self.o.mcp_servers.items():
            try:
                if cfg.get("type") == "sdk":
                    handlers = cfg["instance"].request_handlers
                    listed = (await handlers[types.ListToolsRequest](types.ListToolsRequest(method="tools/list"))).root.tools

                    async def call(name: str, args: Obj, handlers=handlers) -> types.CallToolResult:
                        req = types.CallToolRequest(method="tools/call", params=types.CallToolRequestParams(name=name, arguments=args))
                        return (await handlers[types.CallToolRequest](req)).root
                else:
                    params = StdioServerParameters(command=cfg["command"], args=cfg.get("args", []))
                    read, write = await self._stack.enter_async_context(stdio_client(params))
                    session = await self._stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                    listed = (await session.list_tools()).tools
                    call = session.call_tool
            except Exception:      # noqa: BLE001 - a server that will not start costs its tools, not the session
                continue
            for t in listed:
                if t.name not in self._tools:
                    self._tools[t.name] = (server, call)
                    specs.append({"type": "function", "name": t.name, "description": t.description or "", "inputSchema": t.inputSchema})
        return specs

    async def _allowed(self, name: str, inp: Obj) -> Any:
        """The terminal's own approval: a read-only tool passes, everything else asks the person. The
        answer is read by its `behavior`, so either SDK's PermissionResult types will do."""
        if name in self.o.read_only:
            return PermissionResultAllow()
        return await self.o.can_use_tool(name, inp, None)

    @staticmethod
    def _decision(r: Any) -> str:
        """accept; or decline, which tells the model and lets it ask what to do instead, as a denial
        does with Claude Code; or cancel, which ends the turn, when the denial says to interrupt."""
        if getattr(r, "behavior", None) == "allow":
            return "accept"
        return "cancel" if getattr(r, "interrupt", False) else "decline"

    # -- Codex's requests: approvals and tool calls

    async def _request(self, method: str, p: Obj) -> Obj:
        if method == "item/commandExecution/requestApproval":
            cmd = _str(p.get("command")) or _str(self._items.get(_str(p.get("itemId")), {}).get("command"))
            return {"decision": self._decision(await self._allowed("Bash", {"command": shell_command(cmd), "description": _str(p.get("reason"))}))}
        if method == "item/fileChange/requestApproval":
            name, inp = file_change(self._items.get(_str(p.get("itemId")), {}).get("changes"))
            if p.get("reason"):
                inp["description"] = _str(p["reason"])
            return {"decision": self._decision(await self._allowed(name, inp))}
        if method == "item/tool/call":
            tool, args = _str(p.get("tool")), p.get("arguments") or {}
            if tool not in self._tools:
                return {"success": False, "contentItems": [{"type": "inputText", "text": f"ERROR: no tool {tool}"}]}
            server, call = self._tools[tool]
            decision = self._decision(r := await self._allowed(f"mcp__{server}__{tool}", args))
            if decision != "accept":
                if decision == "cancel":
                    asyncio.ensure_future(self.interrupt())
                return {"success": False, "contentItems": [{"type": "inputText", "text": getattr(r, "message", "") or "declined"}]}
            res = await call(tool, args)
            return {"success": not res.isError, "contentItems": [{"type": "inputText", "text": _content_text([c.model_dump() for c in res.content])}]}
        if method == "mcpServer/elicitation/request":
            return {"action": "decline", "content": None, "_meta": None}     # no server ds-next starts asks anything
        raise SDKError(f"ds-next does not handle {method}")

    # -- Codex's notifications, as the SDK's messages

    def _tool_call(self, item: Obj) -> tuple[str, Obj] | None:
        kind = item.get("type")
        if kind == "commandExecution":
            return "Bash", {"command": shell_command(_str(item.get("command")))}
        if kind == "fileChange":
            return file_change(item.get("changes"))
        if kind == "mcpToolCall":
            return f"mcp__{_str(item.get('server'))}__{_str(item.get('tool'))}", item.get("arguments") or {}
        if kind == "dynamicToolCall":
            tool = _str(item.get("tool"))
            return f"mcp__{self._tools.get(tool, ('ds', None))[0]}__{tool}", item.get("arguments") or {}
        if kind == "webSearch":
            return "WebSearch", {"query": _str(item.get("query"))}
        return None

    @staticmethod
    def _tool_output(item: Obj) -> tuple[str, bool]:
        kind, status = item.get("type"), item.get("status")
        if kind == "commandExecution":
            code = item.get("exitCode")
            out = _str(item.get("aggregatedOutput")).strip()
            failed = status in ("failed", "declined") or (isinstance(code, int) and code != 0)
            return out or ("declined" if status == "declined" else f"exit {code if code is not None else '?'}"), failed
        if kind == "fileChange":
            paths = "\n".join(_str(c.get("path")) for c in item.get("changes") or [])
            return paths or "no files", status in ("failed", "declined")
        if kind == "mcpToolCall":
            error = (item.get("error") or {}).get("message")
            return (_str(error), True) if error else (_content_text((item.get("result") or {}).get("content")), False)
        if kind == "dynamicToolCall":
            return _content_text(item.get("contentItems")), item.get("success") is False
        return "", False

    def _notification(self, method: str, p: Obj) -> None:
        put = self._queue.put_nowait
        if method == "turn/started":
            self._turn_id = _str((p.get("turn") or {}).get("id")) or self._turn_id
        elif method == "item/started":
            item = p.get("item") or {}
            call = self._tool_call(item)
            if call:
                self._items[_str(item.get("id"))] = item
                put(AssistantMessage(content=[ToolUseBlock(id=_str(item.get("id")), name=call[0], input=call[1])], model=self.model or ""))
        elif method == "item/completed":
            item = p.get("item") or {}
            if item.get("type") == "agentMessage":
                if _str(item.get("text")).strip():
                    put(AssistantMessage(content=[TextBlock(text=_str(item["text"]))], model=self.model or ""))
            elif item.get("type") == "reasoning":
                text = "\n".join(item.get("summary") or item.get("content") or [])
                if text.strip():
                    put(AssistantMessage(content=[ThinkingBlock(thinking=text, signature="")], model=self.model or ""))
            elif self._tool_call(item):
                text, failed = self._tool_output(item)
                self._items.pop(_str(item.get("id")), None)
                put(UserMessage(content=[ToolResultBlock(tool_use_id=_str(item.get("id")), content=text, is_error=failed)]))
        elif method == "thread/tokenUsage/updated":
            self._tokens = ((p.get("tokenUsage") or {}).get("last") or {}).get("totalTokens")
        elif method == "error":
            if not p.get("willRetry"):
                self._error = _str((p.get("error") or {}).get("message"))
        elif method == "turn/completed":
            turn = p.get("turn") or {}
            status = _str(turn.get("status"))
            ms = turn.get("durationMs") if isinstance(turn.get("durationMs"), int) else int((time.monotonic() - self._started) * 1000)
            # An interrupted turn is reported by whoever interrupted it (the person, or the stall
            # watchdog), so only a failure is an error here.
            failed = status not in ("completed", "interrupted")
            error = _str((turn.get("error") or {}).get("message")) or self._error or status
            put(ResultMessage(subtype="error_during_execution" if failed else "success", duration_ms=ms, duration_api_ms=ms,
                              is_error=failed, num_turns=1, session_id=self.thread_id,
                              usage={"total_tokens": self._tokens} if self._tokens else None, errors=[error] if failed else None))
            self._turn_id, self._error, self._tokens = "", "", None

    # -- the session

    async def connect(self) -> None:
        argv = command()
        try:
            # A session of its own (POSIX), so ending it ends whatever Codex started that still holds its pipes.
            self._proc = await asyncio.create_subprocess_exec(*argv, cwd=self.o.cwd, stdin=asyncio.subprocess.PIPE,
                                                              stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                              limit=1 << 24, **({} if os.name == "nt" else {"start_new_session": True}))
        except OSError as e:
            raise CLINotFoundError(f"Codex did not start: {e}") from e
        self._rpc = AppServer(self._proc, self._notification, self._request)
        self._drain = asyncio.ensure_future(self._read_stderr())
        try:
            tools = await self._serve()
            await self._rpc.request("initialize", {"clientInfo": {"name": "ds-next", "title": "ds-next", "version": "0.1.0"},
                                                   "capabilities": {"experimentalApi": True, "requestAttestation": False}})
            await self._rpc.notify("initialized")
            # The user's own Codex config may register the same servers (`ds-next setup` adds `ds`);
            # served here already, they are switched off, defined in full so it is valid either way.
            off = {"ds": {"command": "ds-next", "args": ["mcp"], "enabled": False},
                   "code": {"command": "ds-code", "args": ["mcp"], "enabled": False}}
            thread = {"cwd": self.o.cwd, "model": self.model, "approvalPolicy": "untrusted", "sandbox": "workspace-write",
                      "developerInstructions": self.o.system_prompt, "dynamicTools": tools, "config": {"mcp_servers": off}}
            started = await self._rpc.request("thread/resume" if self.o.resume else "thread/start",
                                              {**thread, "threadId": self.o.resume} if self.o.resume else thread)
        except BaseException:
            await self.disconnect()
            raise
        self.thread_id = _str((started.get("thread") or {}).get("id"))
        self.model = _str(started.get("model")) or _str((started.get("thread") or {}).get("model")) or self.model
        self._queue.put_nowait(SystemMessage(subtype="init", data={"model": self.model, "session_id": self.thread_id}))

    async def query(self, prompt: str) -> None:
        assert self._rpc is not None
        self._started = time.monotonic()
        params = {"threadId": self.thread_id, "input": [{"type": "text", "text": prompt, "text_elements": []}],
                  **({"model": self.model} if self.model else {}), **({"effort": self.o.effort} if self.o.effort else {})}
        try:
            r = await self._rpc.request("turn/start", params)
        except SDKError:
            # A turn Codex never confirmed may still be running: end the process, so nothing of it (an
            # approval, a result) lands after the terminal has moved on. The next message resumes it.
            await self.disconnect()
            raise
        self._turn_id = _str((r.get("turn") or {}).get("id")) or self._turn_id

    async def receive_response(self):
        """The turn's messages, up to and including its ResultMessage."""
        while True:
            if self._proc is not None and self._proc.returncode is not None and self._queue.empty():
                last = self._log.strip().splitlines()
                raise SDKError(f"Codex stopped (exit {self._proc.returncode}): {last[-1] if last else 'no reason given'}")
            try:
                msg = await asyncio.wait_for(self._queue.get(), 1.0)
            except asyncio.TimeoutError:
                continue
            yield msg
            if isinstance(msg, ResultMessage):
                return

    async def _read_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        while chunk := await self._proc.stderr.read(4096):
            self._log = (self._log + chunk.decode(errors="replace"))[-2000:]

    async def interrupt(self) -> None:
        if self._rpc is not None and self.thread_id and self._turn_id:
            with contextlib.suppress(SDKError):
                await self._rpc.request("turn/interrupt", {"threadId": self.thread_id, "turnId": self._turn_id})

    async def set_model(self, model: str | None) -> None:
        self.model = model       # the next turn starts with it

    async def disconnect(self) -> None:
        """End Codex: the end of its input first, which it exits on; then, after 2 s, its whole process
        group. Never waits for good: a process left holding a pipe would make wait() hang."""
        proc = self._proc
        if proc is not None and proc.returncode is None:
            with contextlib.suppress(Exception):
                proc.stdin.close()
            try:
                await asyncio.wait_for(proc.wait(), 2)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(proc.pid, signal.SIGKILL) if os.name != "nt" else proc.kill()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(proc.wait(), 2)
        if self._rpc is not None:
            rpc, self._rpc = self._rpc, None
            await rpc.close()
        if self._drain is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._drain, 2)
        await self._stack.aclose()   # the code tools' server, if one started
