"""The terminal: a Claude-Code-style REPL over Agent.

Slash commands that only read the knowledge base run locally and instantly. Everything else is
a turn with Cortex Code. A skills-os skill name typed as a slash command (/so-capture ...) is
handed to the agent with an instruction to follow that skill.
"""
from __future__ import annotations

import asyncio
import functools
import http.server
import json
import signal
import tempfile
import threading
from pathlib import Path
from typing import Any

from cortex_code_agent_sdk import (
    AssistantMessage,
    CortexCodeSDKError,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__, docs, reconcile
from .agent import SERVER, Agent
from .kb import Canon, Skills, docs_shell_path

ACCENT = "#d97757"        # the Claude Code orange
DIM = "grey50"
COMMANDS = {
    "/new": "start a project: the agent interviews you, then scaffolds it from the canon",
    "/canon": "list standards, or /canon <id> to read one",
    "/skills": "list skills-os procedures, or /skills <name> to read one",
    "/status": "reconcile this repo against the canon",
    "/docs": "render this repo (or the whole knowledge base) with docs-ds and serve it",
    "/captures": "list drafts waiting to be proposed to the canon",
    "/model": "show or set the Cortex model",
    "/clear": "start a fresh session",
    "/help": "this list",
    "/exit": "leave",
}


# ---------------------------------------------------------------- rendering (pure, testable)

def _short(name: str) -> str:
    prefix = f"mcp__{SERVER}__"
    if name.startswith(prefix):
        return name[len(prefix):]
    return name[:1].upper() + name[1:]


def _arg_summary(inp: dict[str, Any]) -> str:
    for key in ("command", "file_path", "path", "pattern", "id", "name", "query", "url", "title"):
        if key in inp and isinstance(inp[key], str):
            v = inp[key].replace("\n", " ")
            return v if len(v) <= 70 else v[:67] + "…"
    s = json.dumps(inp, ensure_ascii=False)
    return "" if s == "{}" else (s if len(s) <= 70 else s[:67] + "…")


def _first_sentence(s: str, width: int = 90) -> str:
    s = s.split(". ")[0].rstrip(".")
    return s if len(s) <= width else s[:width].rsplit(" ", 1)[0] + "…"


def _tilde(p: Path, width: int = 60) -> str:
    s = str(p).replace(str(Path.home()), "~", 1)
    return s if len(s) <= width else "…" + s[-(width - 1):]


def _bullet(body, style: str = "white") -> Table:
    t = Table.grid(padding=(0, 1))
    t.add_column(width=1, no_wrap=True)
    t.add_column()
    t.add_row(Text("⏺", style=style), body)
    return t


def _result_text(block: ToolResultBlock) -> str:
    c = block.content
    if isinstance(c, list):
        c = "\n".join(p.get("text", "") for p in c if isinstance(p, dict))
    return (c or "").strip()


def render(console: Console, msg: Any, state: dict) -> None:
    """Print one SDK message the way Claude Code would."""
    if isinstance(msg, AssistantMessage):
        for b in msg.content:
            if isinstance(b, TextBlock) and b.text.strip():
                console.print(_bullet(Markdown(b.text.strip())))
            elif isinstance(b, ThinkingBlock) and b.thinking.strip():
                console.print(Text(f"✻ {b.thinking.strip().splitlines()[0][:100]}", style=f"italic {DIM}"))
            elif isinstance(b, ToolUseBlock):
                state.setdefault("tools", {})[b.id] = b.name
                head = Text(_short(b.name), style="bold")
                arg = _arg_summary(b.input)
                if arg:
                    head.append(f"({arg})")
                console.print(_bullet(head, style="green"))
    elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
        for b in msg.content:
            if isinstance(b, ToolResultBlock):
                text = _result_text(b)
                lines = text.splitlines() or ["(no output)"]
                more = f" … +{len(lines) - 1} lines" if len(lines) > 1 else ""
                style = "red" if b.is_error else DIM
                console.print(Text(f"  ⎿  {lines[0][:100]}{more}", style=style))
    elif isinstance(msg, SystemMessage) and msg.subtype == "init":
        state["model"] = msg.data.get("model")
    elif isinstance(msg, ResultMessage):
        secs = msg.duration_ms / 1000
        parts = [f"{msg.num_turns} turn{'s' if msg.num_turns != 1 else ''}", f"{secs:.1f}s"]
        if msg.total_cost_usd:
            parts.append(f"${msg.total_cost_usd:.4f}")
        if msg.is_error or msg.subtype != "success":
            console.print(Text(f"  ⎿  {msg.subtype}: {'; '.join(msg.errors or [])}", style="red"))
        console.print(Text("  " + " · ".join(parts), style=DIM))


def describe_permission(tool_name: str, inp: dict[str, Any]) -> tuple[str, str]:
    """Cortex sends a kind ("MCP", "Bash", "Write"...) and a resource string. Returns
    (title, detail), naming ds tools by their short name."""
    resource = str(inp.get("resource", "")) if isinstance(inp, dict) else ""
    if tool_name == "MCP":
        first, _, rest = resource.partition("\n")
        detail = rest.removeprefix("Input:").strip()
        return _short(first.strip()), detail
    return tool_name, resource or json.dumps(inp, indent=1)


# ---------------------------------------------------------------- local commands

class SlashCompleter(Completer):
    def __init__(self, extra: dict[str, str]):
        self.items = {**COMMANDS, **extra}

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return
        for cmd, desc in self.items.items():
            if cmd.startswith(text):
                yield Completion(cmd, start_position=-len(text), display_meta=desc[:60])


class Repl:
    def __init__(self, cwd: Path, model: str | None = None, connection: str | None = None):
        self.cwd = Path(cwd).resolve()
        self.console = Console(highlight=False)
        self.canon = Canon()
        self.skills = Skills()
        self.agent = Agent(self.cwd, ask_permission=self._ask_permission, model=model,
                           connection=connection, canon=self.canon, skills=self.skills)
        self.always: set[str] = set()
        self.state: dict = {}
        self._status = None
        self._server: http.server.ThreadingHTTPServer | None = None
        self._where = ""
        home = Path.home() / ".ds"
        home.mkdir(exist_ok=True)
        self.session = PromptSession(
            history=FileHistory(str(home / "history")),
            completer=SlashCompleter({f"/{n}": s.description for n, s in self.skills.all.items()}),
            complete_while_typing=True,
            bottom_toolbar=self._toolbar,
        )

    # -- chrome
    def banner(self) -> None:
        shell = "found" if docs_shell_path() else "not found"
        body = Group(
            Text.assemble(("✻ ", ACCENT), ("Welcome to ", "bold"), ("ds-next", f"bold {ACCENT}"),
                          (f" v{__version__}", DIM)),
            Text(""),
            Text("  /new to start a project · /help for commands · ctrl-c interrupts", style=DIM),
            Text(""),
            Text(f"  cwd:    {_tilde(self.cwd)}", style=DIM),
            Text(f"  canon:  {len(self.canon.standards)} standards at {_tilde(self.canon.root)}", style=DIM),
            Text(f"  skills: {len(self.skills.all)} from skills-os · docs-ds {shell}", style=DIM),
        )
        self.console.print(Panel(body, border_style=ACCENT, expand=False, padding=(0, 2)))
        self.console.print()

    def _refresh_where(self) -> None:
        repo = reconcile.find_repo(self.cwd)
        self._where = reconcile.check(repo, self.canon).summary() if repo else "not a ds repo"

    def _toolbar(self):
        where = self._where
        model = self.state.get("model") or self.agent.model or "auto"
        return HTML(f"  <b>{self.cwd.name}</b> · {where} · model {model} · "
                    f"{'connected' if self.agent.connected else 'idle'}")

    # -- permissions
    async def _ask_permission(self, tool_name: str, inp: dict[str, Any], ctx: Any):
        title, detail = describe_permission(tool_name, inp)
        if title in self.always:
            return PermissionResultAllow()
        if self._status:
            self._status.stop()
        try:
            self.console.print(Panel(Text(detail[:1500] or "(no input)"), title=f"[bold]{title}[/bold]",
                                     title_align="left", border_style="yellow", expand=False))
            answer = await PromptSession().prompt_async(
                HTML("  Allow? <b>y</b>es · <b>a</b>lways this session · <b>n</b>o › "))
        except (KeyboardInterrupt, EOFError):
            answer = "n"
        finally:
            if self._status:
                self._status.start()
        answer = answer.strip().lower()
        if answer.startswith("a"):
            self.always.add(title)
            return PermissionResultAllow()
        if answer.startswith("y") or answer == "":
            return PermissionResultAllow()
        return PermissionResultDeny(message="The user declined this call. Ask what to do instead.")

    # -- local commands
    def cmd_help(self, _: str) -> None:
        t = Table(box=None, show_header=False, padding=(0, 2))
        for c, d in COMMANDS.items():
            t.add_row(Text(c, style=ACCENT), d)
        t.add_row(Text("/<skill>", style=ACCENT), "run a skills-os skill, e.g. /so-best-practice-audit")
        t.add_row(Text("anything else", style=ACCENT), "goes to Cortex Code, with the knowledge base as tools")
        self.console.print(t)

    def cmd_canon(self, arg: str) -> None:
        if arg in self.canon.standards:
            s = self.canon.standards[arg]
            self.console.print(Panel(Markdown(self.canon.read(arg)), title=f"{s.id} v{s.version} · {s.status}",
                                     title_align="left", border_style=DIM))
            return
        tags = [t.strip() for t in arg.split(",") if t.strip()]
        stds = self.canon.applicable(tags) if tags else sorted(self.canon.standards.values(), key=lambda s: s.id)
        t = Table(box=None, padding=(0, 2), header_style=DIM)
        for col in ("id", "v", "applies to", "status", "title"):
            t.add_column(col)
        for s in stds:
            t.add_row(Text(s.id, style=ACCENT), str(s.version), ",".join(s.applies_to), s.status, s.title)
        self.console.print(t)

    def cmd_skills(self, arg: str) -> None:
        if arg in self.skills.all:
            self.console.print(Panel(Markdown(self.skills.all[arg].read()), title=arg, title_align="left",
                                     border_style=DIM))
            return
        t = Table(box=None, padding=(0, 2), show_header=False)
        for s in self.skills.all.values():
            t.add_row(Text(f"/{s.name}", style=ACCENT), _first_sentence(s.description))
        self.console.print(t)

    def cmd_status(self, _: str) -> None:
        repo = reconcile.find_repo(self.cwd)
        if repo is None:
            self.console.print(Text("Not a ds repo. /new creates one.", style=DIM))
            return
        r = reconcile.check(repo, self.canon)
        style = "green" if r.ok and not r.pending else ("yellow" if r.ok else "red")
        self.console.print(_bullet(Text(r.summary(), style="bold"), style=style))
        for p in r.pending:
            self.console.print(Text(f"  ⎿  pending {p}", style="yellow"))
        for sid, why in r.declined.items():
            self.console.print(Text(f"  ⎿  declined {sid}: {why}" + (" (past revisit)" if sid in r.overdue else ""),
                                    style=DIM))
        for e in r.errors:
            self.console.print(Text(f"  ⎿  {e}", style="red"))

    def cmd_captures(self, _: str) -> None:
        base = reconcile.find_repo(self.cwd) or self.cwd
        drafts = sorted((base / ".ds" / "captures").glob("*.md"))
        if not drafts:
            self.console.print(Text("No drafts. Ask the agent to capture something worth keeping.", style=DIM))
        for d in drafts:
            self.console.print(Text(f"  {d.relative_to(base)}", style=ACCENT))

    def cmd_docs(self, _: str) -> None:
        repo = reconcile.find_repo(self.cwd)
        stage = Path(tempfile.mkdtemp(prefix="ds-next-docs-"))
        with self.console.status(f"[{ACCENT}]✻[/] Building with docs-ds…", spinner="dots"):
            content, title = docs.stage(stage, self.canon, self.skills, repo)
            try:
                r = docs.build(content, title, stage / "site")
            except FileNotFoundError as e:
                self.console.print(Text(str(e), style="red"))
                return
        if r.returncode != 0:
            self.console.print(Text((r.stdout + r.stderr)[-1500:], style="red"))
            return
        if self._server:
            self._server.shutdown()
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(stage / "site"))
        handler.log_message = lambda *a, **k: None  # type: ignore[method-assign]
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        port = self._server.server_address[1]
        self.console.print(_bullet(Text.assemble(("Serving ", ""), (title, "bold"), " at ",
                                                 (f"http://127.0.0.1:{port}/", f"underline {ACCENT}")),
                                   style="green"))

    async def cmd_model(self, arg: str) -> None:
        if arg:
            await self.agent.set_model(arg)
        self.console.print(Text(f"model: {self.agent.model or self.state.get('model') or 'auto'}", style=DIM))

    async def cmd_clear(self, _: str) -> None:
        await self.agent.reset()
        self.always.clear()
        self.state.clear()
        self.console.clear()
        self.banner()

    # -- the turn
    async def turn(self, prompt: str) -> None:
        loop = asyncio.get_running_loop()
        interrupted = False

        def on_sigint():
            nonlocal interrupted
            interrupted = True
            asyncio.ensure_future(self.agent.interrupt())

        loop.add_signal_handler(signal.SIGINT, on_sigint)
        label = "Connecting to Cortex Code…" if not self.agent.connected else "Working…"
        self._status = self.console.status(f"[{ACCENT}]✻[/] {label} [{DIM}](ctrl-c to interrupt)[/]",
                                           spinner="dots", spinner_style=ACCENT)
        self._status.start()
        try:
            async for msg in self.agent.turn(prompt):
                if self._status:
                    self._status.update(f"[{ACCENT}]✻[/] Working… [{DIM}](ctrl-c to interrupt)[/]")
                render(self.console, msg, self.state)
        except CortexCodeSDKError as e:
            self.console.print(Text(f"Cortex Code: {e}", style="red"))
            await self.agent.reset()
        finally:
            self._status.stop()
            self._status = None
            loop.remove_signal_handler(signal.SIGINT)
        if interrupted:
            self.console.print(Text("  ⎿  Interrupted by user", style="red"))

    async def handle(self, line: str) -> bool:
        """Returns False to exit."""
        line = line.strip()
        if not line:
            return True
        if not line.startswith("/"):
            await self.turn(line)
            return True
        cmd, _, arg = line.partition(" ")
        arg = arg.strip()
        if cmd in ("/exit", "/quit"):
            return False
        if cmd == "/new":
            await self.turn("I want to start a new project" + (f" named {arg}" if arg else "")
                            + ". Run the interview.")
        elif cmd[1:] in self.skills.all:
            await self.turn(f"Follow the {cmd[1:]} skill: skill_read it first, then do what it says."
                            + (f" Context from me: {arg}" if arg else ""))
        elif cmd in ("/model", "/clear"):
            await getattr(self, f"cmd_{cmd[1:]}")(arg)
        elif cmd in COMMANDS:
            getattr(self, f"cmd_{cmd[1:]}")(arg)
        else:
            self.console.print(Text(f"Unknown command {cmd}. /help lists them.", style="red"))
        return True

    async def run(self) -> None:
        self.banner()
        try:
            while True:
                self._refresh_where()
                try:
                    line = await self.session.prompt_async(HTML(f'<style fg="{ACCENT}">›</style> '))
                except KeyboardInterrupt:
                    continue
                except EOFError:
                    break
                self.console.print()
                if not await self.handle(line):
                    break
                self.console.print()
        finally:
            if self._server:
                self._server.shutdown()
            await self.agent.close()


def main(cwd: Path, model: str | None = None, connection: str | None = None) -> None:
    asyncio.run(Repl(cwd, model, connection).run())
