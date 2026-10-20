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
from .agent import SERVER, Agent, TurnStalled
from .kb import Canon, Scaffold, Skills, docs_shell_path
from .widgets import Field, form, pick

# The look is updater's (Hermes style, plain terminal colours so it follows the user's theme):
# a magenta box for the banner, cyan ◆ for what the agent says and → for what it runs, dim │ for
# output, green ✓, yellow ⚠, red ✗.
BRAND = "bold magenta"
ACCENT = "cyan"
HEAD = "bold cyan"
OK = "green"
WARN = "yellow"
ERR = "red"
DIM = "dim"
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
    """ds tools by their own name, other MCP servers' tools as server.tool, built-ins capitalised."""
    prefix = f"mcp__{SERVER}__"
    if name.startswith(prefix):
        return name[len(prefix):]
    if name.startswith("mcp__") and name.count("__") >= 2:
        _, server, tool_name = name.split("__", 2)
        return f"{server}.{tool_name}"
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


def _bullet(body, glyph: str = "◆", style: str = HEAD) -> Table:
    t = Table.grid(padding=(0, 1))
    t.add_column(width=1, no_wrap=True)
    t.add_column()
    t.add_row(Text(glyph, style=style), body)
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
                console.print(_bullet(head, "→", ACCENT))
    elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
        for b in msg.content:
            if isinstance(b, ToolResultBlock):
                state["step"] = "Thinking"
                text = _result_text(b)
                lines = text.splitlines() or ["(no output)"]
                more = f" … +{len(lines) - 1} lines" if len(lines) > 1 else ""
                bad = b.is_error or text.startswith("ERROR:")
                console.print(Text(f"  {'✗' if bad else '│'} {lines[0][:100]}{more}", style=ERR if bad else DIM))
    elif isinstance(msg, SystemMessage) and msg.subtype == "init":
        state["model"] = msg.data.get("model")
    elif isinstance(msg, ResultMessage):
        secs = msg.duration_ms / 1000
        parts = [f"{msg.num_turns} turn{'s' if msg.num_turns != 1 else ''}", f"{secs:.1f}s"]
        if msg.total_cost_usd:
            parts.append(f"${msg.total_cost_usd:.4f}")
        if msg.is_error or msg.subtype != "success":
            console.print(Text(f"  ✗ {msg.subtype}: {'; '.join(msg.errors or [])}", style=ERR))
        console.print(Text("  " + " · ".join(parts), style=DIM))


def extra_tags(typed: str, scaffold_tags: tuple[str, ...]) -> list[str]:
    """The tags the user typed in the form, minus the scaffold's own. Kept as typed: a tag such as
    snowflake must survive even when the schema field that would also imply it is blank."""
    tags = [t.strip().lower() for t in typed.split(",") if t.strip()]
    return [t for t in dict.fromkeys(tags) if t not in scaffold_tags]


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
            Text.assemble(("▼ ds-next", "bold"), (f"  v{__version__}", DIM)),
            Text(""),
            Text("Start, check and grow projects from the team's canon."),
            Text(""),
            Text("/new starts a project · /help lists commands · /exit leaves", style=DIM),
            Text(""),
            Text(f"cwd:    {_tilde(self.cwd)}", style=DIM),
            Text(f"canon:  {len(self.canon.standards)} standards, {len(self.canon.scaffolds)} project types "
                 f"at {_tilde(self.canon.root)}", style=DIM),
            Text(f"skills: {len(self.skills.all)} from skills-os · docs-ds {shell}", style=DIM),
        )
        self.console.print(Panel(body, border_style=BRAND, expand=False, padding=(0, 2)))
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
        glyph, style = ("✓", OK) if r.ok and not r.pending else (("⚠", WARN) if r.ok else ("✗", ERR))
        self.console.print(_bullet(Text(r.summary(), style="bold"), glyph, style))
        for p in r.pending:
            self.console.print(Text(f"  │ pending {p}", style=WARN))
        for sid, why in r.declined.items():
            self.console.print(Text(f"  │ declined {sid}: {why}" + (" (past revisit)" if sid in r.overdue else ""),
                                    style=DIM))
        for e in r.errors:
            self.console.print(Text(f"  │ {e}", style=ERR))

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
        with self.console.status(f"[{ACCENT}]→[/] Building with docs-ds…", spinner="dots"):
            content, title = docs.stage(stage, self.canon, self.skills, repo)
            try:
                r = docs.build(content, title, stage / "site", protect=[repo] if repo else [])
            except (ValueError, FileNotFoundError) as e:
                self.console.print(Text(str(e), style=ERR))
                return
        if r.returncode != 0:
            self.console.print(Text((r.stdout + r.stderr)[-1500:], style=ERR))
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
                                   style=OK))

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
            self.console.print(Text("The canon has no accepted scaffold for that. /new alone lists them.", style=ERR))
            return
        by_id = {c.id: c for c in candidates}
        name = rest[0] if rest and scaffold.NAME_RE.match(rest[0]) else ""
        # Three answers. The type decides the rest (tags, test and lint commands); standards are
        # declined later, from /status, when one actually gets in the way.
        def describe(c: Scaffold) -> str:
            return f"{c.title} · outputs: {', '.join(c.outputs) or 'none'}"

        fields = [
            Field("type", "type", candidates[0].id, "←/→ or space to change the project type",
                  choices=[(c.id, describe(c)) for c in candidates]),
            Field("name", "name", name, scaffold.NAME_RULE, True, example="feed-model",
                  normalize=scaffold.normalize_name, check=scaffold.name_problem),
            Field("purpose", "purpose", " ".join(rest[1:]) if name else " ".join(rest),
                  "one line: what it does and for whom", True,
                  example="Weekly feed use per barn, for the barn managers"),
            Field("owner", "owner", scaffold._git_user(), "who answers for this repo; the git user by default"),
        ]

        def answers(v: dict[str, str]) -> scaffold.Answers:
            return scaffold.Answers(name=v["name"], purpose=v["purpose"], scaffold=v["type"], owner=v["owner"])

        def footer(v: dict[str, str]) -> str:
            c = by_id[v["type"]]
            n = len(self.canon.applicable(list(c.tags)))
            return f"{n} standards apply · v{c.version} · tags {', '.join(c.tags)}"

        def validate(v: dict[str, str]):
            try:
                a = answers(v)
            except ValueError as e:
                return ("name" if "name" in str(e) else "purpose", str(e))
            try:
                scaffold.render(a, self.canon, self.skills)
            except ValueError as e:
                return ("purpose", str(e))
            if (self.cwd / a.name).exists():
                return ("name", f"{a.name}/ already exists here")
            return None

        v = await form("New project from the canon · fill in, check, Enter", fields, footer, validate)
        if v is None:
            self.console.print(Text("  │ cancelled", style=DIM))
            return
        sc = by_id[v["type"]]
        self.console.print(_bullet(Text.assemble(("Scaffold ", ""), (sc.id, "bold"), (f" v{sc.version} · {sc.title}", DIM)),
                                   "✓", OK))
        a = answers(v).resolve(self.canon)
        draft = {"scaffold": sc.id, "name": a.name, "purpose": a.purpose, "owner": a.owner}
        shown = Text()
        for k in ("name", "purpose", "owner"):
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
                self.console.print(Text("effort is one of minimal, low, medium, high, xhigh, max", style=ERR))
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
            return f"[{ACCENT}]→[/] {self.state['step']}… [{DIM}]{secs}s · ctrl-c to interrupt[/]"

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
        except TurnStalled as e:
            self.console.print(Text(f"  │ {e}", style=WARN))
        except CortexCodeSDKError as e:
            self.console.print(Text(f"Cortex Code: {e}", style=ERR))
            await self.agent.reset()
        finally:
            ticker.cancel()
            self._status.stop()
            self._status = None
            self._sigint = None
            loop.remove_signal_handler(signal.SIGINT)
        if interrupted:
            self.console.print(Text("  │ Interrupted by user", style=ERR))

    async def handle(self, line: str) -> bool:
        """Returns False to exit."""
        line = line.strip()
        if not line:
            if self.state.get("asked"):
                # Enter on its own keeps what the user already gave; it never accepts an invented value
                self.console.print(Text("  │ (Enter) keep my answers as they are and continue", style=DIM))
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
            self.console.print(Text(f"Unknown command {cmd}. /help lists them.", style=ERR))
        return True

    async def run(self) -> None:
        self.banner()
        try:
            last_interrupt = 0.0
            while True:
                self._refresh_where()
                try:
                    line = await self.session.prompt_async(HTML('<style fg="ansicyan"><b>›</b></style> '))
                except KeyboardInterrupt:
                    # the Claude Code habit: one ctrl-c clears the line, a second within two seconds leaves
                    now = time.monotonic()
                    if now - last_interrupt < 2.0:
                        break
                    last_interrupt = now
                    self.console.print(Text("  ctrl-c again to leave, or /exit", style=DIM))
                    continue
                except EOFError:
                    break
                last_interrupt = 0.0
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
