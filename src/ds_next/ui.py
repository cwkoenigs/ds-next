"""The terminal: a Claude-Code-style REPL over Agent.

Slash commands that only read the knowledge base run locally and instantly. `/new` is a picker
and a one-screen form, both local; the model then reviews the draft against the canon, fetches
the accepted scaffold, and creates the repo. Everything else is a turn with Cortex Code. A
skills-os skill typed as a slash command (/so-capture ...) is handed to the agent to follow.
"""
from __future__ import annotations

import asyncio
import functools
import html
import http.server
import json
import signal
import tempfile
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from cortex_agent_sdk.cortexcode import (
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

from . import __version__, docs, reconcile, scaffold
from .agent import SERVER, Agent
from .kb import Canon, Scaffold, Skills, docs_shell_path
from .widgets import Field, form, pick

ACCENT = "#d97757"        # the Claude Code orange
DIM = "grey50"
COMMANDS = {
    "/new": "start a project from a canon scaffold: /new, /new python, /new python cli <name>",
    "/canon": "list standards, or /canon <id> to read one",
    "/skills": "list skills-os procedures, or /skills <name> to read one",
    "/status": "reconcile this repo against the canon",
    "/docs": "render this repo (or the whole knowledge base) with docs-ds and serve it",
    "/captures": "list drafts waiting to be proposed to the canon",
    "/model": "show or set the Cortex model",
    "/effort": "show or set thinking effort: minimal, low, medium, high",
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
                state["asked"] = asks(b.text)
            elif isinstance(b, ThinkingBlock):
                state["step"] = "Thinking"      # private reasoning stays private, as in Claude Code
            elif isinstance(b, ToolUseBlock):
                state["step"] = f"Running {_short(b.name)}"
                state.setdefault("tools", {})[b.id] = b.name
                head = Text(_short(b.name), style="bold")
                arg = _arg_summary(b.input)
                if arg:
                    head.append(f"({arg})")
                console.print(_bullet(head, style="green"))
    elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
        for b in msg.content:
            if isinstance(b, ToolResultBlock):
                state["step"] = "Thinking"
                text = _result_text(b)
                lines = text.splitlines() or ["(no output)"]
                more = f" … +{len(lines) - 1} lines" if len(lines) > 1 else ""
                style = "red" if b.is_error or text.startswith("ERROR:") else DIM
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


def asks(text: str) -> bool:
    """Whether a reply ends by asking something, even when an example follows the question mark."""
    tail = text.strip().splitlines()[-3:] if text.strip() else []
    return any("?" in line for line in tail)


def _norm(v: Any) -> Any:
    if v in (None, "", [], {}):
        return None
    return [str(x).strip().lower() for x in v] if isinstance(v, list) else v


def changed_keys(draft: dict, args: dict) -> list[str]:
    keys = (set(draft) | set(args)) - {"scaffold_version"}
    return sorted(k for k in keys if _norm(draft.get(k)) != _norm(args.get(k)))


def same_draft(draft: dict, args: dict) -> bool:
    """Whether the model is creating exactly what the form submitted (a version number aside)."""
    return not changed_keys(draft, args)


class Approver:
    """Answers Cortex's can_use_tool requests.

    One question at a time: Cortex can ask for parallel tool calls at once, and two prompts on
    one terminal would send an answer to the wrong one. The whole input is shown. Only an
    explicit y, a or n counts; Enter alone asks again. Submitting the /new form approves exactly
    that draft, and nothing else."""

    def __init__(self, ask: Callable[[str, str], Awaitable[str]]):
        self.ask = ask
        self.always: set[str] = set()
        self.draft: dict | None = None
        self._lock = asyncio.Lock()

    def reset(self) -> None:
        self.always.clear()
        self.draft = None

    async def __call__(self, tool_name: str, inp: dict[str, Any], ctx: Any):
        async with self._lock:
            title, detail = describe_permission(tool_name, inp)
            if title in self.always:
                return PermissionResultAllow()
            if title == "scaffold_project" and self.draft:
                try:
                    args = json.loads(detail)
                except ValueError:
                    args = {}
                if same_draft(self.draft, args):
                    self.draft = None
                    return PermissionResultAllow()
                detail = "Changed from your form:\n" + "\n".join(
                    f"  {k}: {self.draft.get(k, '')!r} → {args.get(k, '')!r}"
                    for k in changed_keys(self.draft, args)) + "\n\n" + detail
            while True:
                answer = (await self.ask(title, detail)).strip().lower()
                if answer in ("a", "always"):
                    self.always.add(title)
                    return PermissionResultAllow()
                if answer in ("y", "yes"):
                    return PermissionResultAllow()
                if answer in ("n", "no"):
                    return PermissionResultDeny(message="The user declined this call. Ask what to do instead.")


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
    """Commands, then for /new the scaffold menu path one word at a time: /new python cli."""

    def __init__(self, extra: dict[str, str], scaffolds: dict[str, Scaffold] | None = None):
        self.items = {**COMMANDS, **extra}
        self.scaffolds = scaffolds or {}

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/new "):
            *done, partial = text[5:].split(" ")
            seen = set()
            for sc in self.scaffolds.values():
                if list(sc.path[:len(done)]) == done and len(sc.path) > len(done):
                    word = sc.path[len(done)]
                    if word.startswith(partial) and word not in seen:
                        seen.add(word)
                        leaf = len(sc.path) == len(done) + 1
                        yield Completion(word, start_position=-len(partial),
                                         display_meta=sc.title if leaf else "…")
            return
        if not text.startswith("/") or " " in text:
            return
        for cmd, desc in self.items.items():
            if cmd.startswith(text):
                yield Completion(cmd, start_position=-len(text), display_meta=desc[:60])


class Repl:
    def __init__(self, cwd: Path, model: str | None = None, connection: str | None = None,
                 effort: str | None = "low"):
        self.cwd = Path(cwd).resolve()
        self.console = Console(highlight=False)
        self.canon = Canon()
        self.skills = Skills()
        self.approver = Approver(self._prompt_approval)
        self._sigint = None
        self.agent = Agent(self.cwd, ask_permission=self.approver, model=model,
                           connection=connection, effort=effort, canon=self.canon, skills=self.skills)
        self.state: dict = {}
        self._status = None
        self._server: http.server.ThreadingHTTPServer | None = None
        self._where = ""
        home = Path.home() / ".ds"
        home.mkdir(exist_ok=True)
        self.session = PromptSession(
            history=FileHistory(str(home / "history")),
            completer=SlashCompleter({f"/{n}": s.description for n, s in self.skills.all.items()},
                                     self.canon.scaffolds),
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
            Text(f"  canon:  {len(self.canon.standards)} standards, {len(self.canon.scaffolds)} scaffolds "
                 f"at {_tilde(self.canon.root)}", style=DIM),
            Text(f"  skills: {len(self.skills.all)} from skills-os · docs-ds {shell}", style=DIM),
        )
        self.console.print(Panel(body, border_style=ACCENT, expand=False, padding=(0, 2)))
        self.console.print()

    def _refresh_where(self) -> None:
        try:
            repo = reconcile.find_repo(self.cwd)
            self._where = reconcile.check(repo, self.canon).summary() if repo else "not a ds repo"
        except Exception as e:  # noqa: BLE001 - the toolbar must never take the terminal down
            self._where = f"status unavailable ({type(e).__name__})"

    def _toolbar(self):
        where = self._where
        model = self.state.get("model") or self.agent.model or "auto"
        esc = html.escape
        return HTML(f"  <b>{esc(self.cwd.name)}</b> · {esc(where)} · model {esc(str(model))} · "
                    f"effort {esc(str(self.agent.effort or 'default'))} · "
                    f"{'connected' if self.agent.connected else 'idle'}")

    # -- permissions
    async def _prompt_approval(self, title: str, detail: str) -> str:
        """Show the whole request and read one answer. Stops the spinner while it asks and puts
        the turn's Ctrl-C handler back afterwards, since the prompt replaces it."""
        if self._status:
            self._status.stop()
        try:
            self.console.print(Panel(Text(detail or "(no input)"), title=f"[bold]{title}[/bold]",
                                     title_align="left", border_style="yellow", expand=False))
            return await PromptSession().prompt_async(
                HTML("  Allow? <b>y</b>es · <b>a</b>lways this session · <b>n</b>o › "))
        except (KeyboardInterrupt, EOFError):
            return "n"
        finally:
            if self._sigint is not None:
                asyncio.get_running_loop().add_signal_handler(signal.SIGINT, self._sigint)
            if self._status:
                self._status.start()

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
                r = docs.build(content, title, stage / "site", protect=[repo] if repo else [])
            except (ValueError, FileNotFoundError) as e:
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

    def _choose_scaffold(self, words: list[str]) -> tuple[list[Scaffold], list[str]]:
        """Scaffolds whose menu path starts with the typed words, and the words left over."""
        matches = list(self.canon.scaffolds.values())
        used = 0
        for depth, w in enumerate(words):
            narrowed = [sc for sc in matches if len(sc.path) > depth and sc.path[depth] == w]
            if not narrowed:
                break
            matches, used = narrowed, depth + 1
        return [sc for sc in matches if sc.accepted], words[used:]

    async def cmd_new(self, arg: str) -> None:
        candidates, rest = self._choose_scaffold(arg.split())
        if not candidates:
            self.console.print(Text("The canon has no accepted scaffold for that. /new alone lists them.", style="red"))
            return
        if len(candidates) == 1:
            sc = candidates[0]
        else:
            chosen = await pick("New project from the canon. Which scaffold?",
                                [(c.id, " › ".join(c.path), f"{c.title} · v{c.version}") for c in candidates])
            if chosen is None:
                self.console.print(Text("  ⎿  cancelled", style=DIM))
                return
            sc = self.canon.scaffolds[chosen]
        self.console.print(_bullet(Text.assemble(("Scaffold ", ""), (sc.id, "bold"), (f" v{sc.version} · {sc.title}", DIM)),
                                   style="green"))
        name = rest[0] if rest and scaffold.NAME_RE.match(rest[0]) else ""
        fields = [
            Field("name", "name", name, "lowercase-with-dashes; also the folder and the command", True),
            Field("purpose", "purpose", " ".join(rest[1:]) if name else " ".join(rest),
                  "one line: what it does and for whom", True),
            Field("snowflake", "snowflake", "", "DATABASE.SCHEMA it reads or writes; empty for none"),
            Field("notes", "notes", "", "the one thing future-you should know; optional"),
            Field("owner", "owner", scaffold._git_user(), "who answers for this repo"),
            Field("tags", "extra tags", "", f"comma-separated, beyond {', '.join(sc.tags)}"),
            Field("test_cmd", "test", sc.defaults.get("test_cmd", ""), "from the scaffold"),
            Field("lint_cmd", "lint", sc.defaults.get("lint_cmd", ""), "from the scaffold"),
            Field("declines", "declines", "", "standards to decline now, as id: reason; id: reason"),
        ]

        def answers(v: dict[str, str]) -> scaffold.Answers:
            declines = {}
            for part in filter(None, (p.strip() for p in v["declines"].split(";"))):
                sid, _, why = part.partition(":")
                declines[sid.strip()] = why.strip()
            return scaffold.Answers(name=v["name"], purpose=v["purpose"], scaffold=sc.id, owner=v["owner"],
                                    test_cmd=v["test_cmd"], lint_cmd=v["lint_cmd"], snowflake=v["snowflake"],
                                    notes=v["notes"], tags=[t for t in v["tags"].split(",") if t.strip()],
                                    declines=declines)

        def footer(v: dict[str, str]) -> str:
            tags = list(dict.fromkeys([*sc.tags, *(["snowflake"] if v["snowflake"] else []),
                                       *(t.strip().lower() for t in v["tags"].split(",") if t.strip())]))
            n = len(self.canon.applicable(tags))
            return f"{n} standards apply · tags {', '.join(tags)}"

        def validate(v: dict[str, str]):
            try:
                a = answers(v)
            except ValueError as e:
                return ("name" if "name" in str(e) else "purpose", str(e))
            try:
                scaffold.render(a, self.canon, self.skills)
            except ValueError as e:
                return ("declines", str(e))
            if (self.cwd / a.name).exists():
                return ("name", f"{a.name}/ already exists here")
            return None

        v = await form(f"{sc.title} · fill in, check, Enter", fields, footer, validate)
        if v is None:
            self.console.print(Text("  ⎿  cancelled", style=DIM))
            return
        a = answers(v).resolve(self.canon)
        draft = {k: val for k, val in {
            "scaffold": sc.id, "name": a.name, "purpose": a.purpose, "owner": a.owner, "snowflake": a.snowflake,
            "notes": a.notes, "tags": [t for t in a.tags if t not in sc.tags and t != "snowflake"],
            "test_cmd": a.test_cmd, "lint_cmd": a.lint_cmd, "declines": a.declines}.items() if val}
        shown = Text()
        for k in ("name", "purpose", "snowflake", "notes", "owner", "tags", "declines"):
            if k in draft:
                shown.append(f"{k:<10}", style=DIM).append(f"{draft[k]}\n")
        shown.append(footer(v), style=ACCENT)
        self.console.print(_bullet(shown))
        self.console.print()
        self.approver.draft = draft
        await self.turn("New project draft from the /new form. Review it against the canon, then fetch the "
                        f"accepted scaffold and create it, as your instructions say.\n\n{json.dumps(draft, indent=1)}")

    async def cmd_effort(self, arg: str) -> None:
        if arg:
            if arg not in ("minimal", "low", "medium", "high", "xhigh", "max"):
                self.console.print(Text("effort is one of minimal, low, medium, high, xhigh, max", style="red"))
                return
            await self.agent.set_effort(arg)
        self.console.print(Text(f"effort: {self.agent.effort or 'default'}", style=DIM))

    async def cmd_model(self, arg: str) -> None:
        if arg:
            await self.agent.set_model(arg)
        self.console.print(Text(f"model: {self.agent.model or self.state.get('model') or 'auto'}", style=DIM))

    async def cmd_clear(self, _: str) -> None:
        await self.agent.reset()
        self.approver.reset()
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

        self._sigint = on_sigint
        loop.add_signal_handler(signal.SIGINT, on_sigint)
        self.state["step"] = "Connecting to Cortex Code" if not self.agent.connected else "Thinking"
        self.state["asked"] = False
        started = time.monotonic()

        def label() -> str:
            secs = int(time.monotonic() - started)
            return f"[{ACCENT}]✻[/] {self.state['step']}… [{DIM}]{secs}s · ctrl-c to interrupt[/]"

        self._status = self.console.status(label(), spinner="dots", spinner_style=ACCENT)
        self._status.start()

        async def tick():
            while True:
                await asyncio.sleep(0.5)
                if self._status:
                    self._status.update(label())

        ticker = asyncio.ensure_future(tick())
        try:
            async for msg in self.agent.turn(prompt):
                render(self.console, msg, self.state)
                if self._status:
                    self._status.update(label())
        except CortexCodeSDKError as e:
            self.console.print(Text(f"Cortex Code: {e}", style="red"))
            await self.agent.reset()
        finally:
            ticker.cancel()
            self._status.stop()
            self._status = None
            self._sigint = None
            loop.remove_signal_handler(signal.SIGINT)
        if interrupted:
            self.console.print(Text("  ⎿  Interrupted by user", style="red"))

    async def handle(self, line: str) -> bool:
        """Returns False to exit."""
        line = line.strip()
        if not line:
            if self.state.get("asked"):
                # Enter on its own keeps what the user already gave; it never accepts an invented value
                self.console.print(Text("  ⎿  (Enter) keep my answers as they are and continue", style=DIM))
                await self.turn("Keep my answers exactly as they are and continue. Do not change any value "
                                "I gave and do not fill in anything I did not give.")
            else:
                self.console.print(Text("  Type a message, or / for commands. /new starts a project.", style=DIM))
            return True
        if not line.startswith("/"):
            await self.turn(line)
            return True
        cmd, _, arg = line.partition(" ")
        arg = arg.strip()
        if cmd in ("/exit", "/quit"):
            return False
        if cmd[1:] in self.skills.all:
            await self.turn(f"Follow the {cmd[1:]} skill: skill_read it first, then do what it says."
                            + (f" Context from me: {arg}" if arg else ""))
        elif cmd in ("/model", "/clear", "/new", "/effort"):
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


def main(cwd: Path, model: str | None = None, connection: str | None = None, effort: str | None = "low") -> None:
    asyncio.run(Repl(cwd, model, connection, effort).run())
