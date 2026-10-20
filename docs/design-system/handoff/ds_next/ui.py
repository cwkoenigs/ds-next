"""The terminal: a Claude-Code-style REPL over Agent, drawn with ui_style.

Slash commands that only read the knowledge base run locally and instantly. `/new` is a picker
and a one-screen form, both local; the model then reviews the draft against the canon, fetches
the accepted scaffold, and creates the repo. Everything else is a turn with Cortex Code. A
skills-os skill typed as a slash command (/so-capture ...) is handed to the agent to follow.
"""
from __future__ import annotations

import asyncio
import difflib
import functools
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
from prompt_toolkit.application import get_app
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

from . import __version__, docs, reconcile, scaffold
from . import ui_style as S
from .agent import SERVER, Agent, TurnStalled
from .kb import Canon, Scaffold, Skills, docs_shell_path
from .ui_style import G
from .widgets import Field, form

COMMANDS = {
    "/new": "start a project from a canon scaffold: /new, /new python, /new python cli <name>",
    "/canon": "list standards, or /canon <id> to read one",
    "/skills": "list skills-os procedures, or /skills <name> to read one",
    "/status": "reconcile this repo against the canon",
    "/last": "full output of the last tool call",
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
            return v if len(v) <= 60 else v[:57] + "…"
    s = json.dumps(inp, ensure_ascii=False)
    return "" if s == "{}" else (s if len(s) <= 60 else s[:57] + "…")


def _first_sentence(s: str, width: int = 90) -> str:
    s = s.split(". ")[0].rstrip(".")
    return s if len(s) <= width else s[:width].rsplit(" ", 1)[0] + "…"


def _tilde(p: Path, width: int = 60) -> str:
    s = str(p).replace(str(Path.home()), "~", 1)
    return s if len(s) <= width else "…" + s[-(width - 1):]


def _result_text(block: ToolResultBlock) -> str:
    c = block.content
    if isinstance(c, list):
        c = "\n".join(p.get("text", "") for p in c if isinstance(p, dict))
    return (c or "").strip()


def render(console: Console, msg: Any, state: dict) -> None:
    """Print one SDK message on the rail."""
    if isinstance(msg, AssistantMessage):
        for b in msg.content:
            if isinstance(b, TextBlock) and b.text.strip():
                S.agent_lines(console, Markdown(b.text.strip()))
                state["asked"] = asks(b.text)
            elif isinstance(b, ThinkingBlock):
                state["step"] = "Thinking"      # private reasoning stays private
            elif isinstance(b, ToolUseBlock):
                state["step"] = f"Running {_short(b.name)}"
                state.setdefault("tools", {})[b.id] = b.name
                state["calls"] = state.get("calls", 0) + 1
                console.print(S.run(_short(b.name), _arg_summary(b.input)))
    elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
        for b in msg.content:
            if isinstance(b, ToolResultBlock):
                state["step"] = "Thinking"
                text = _result_text(b)
                state["last_result"] = text
                lines = text.splitlines() or ["(no output)"]
                error = b.is_error or text.startswith("ERROR:")
                first = lines[0].removeprefix("ERROR:").strip() if error else lines[0]
                console.print(S.result(("ERROR " if error else "") + first[:66], more=len(lines) - 1, error=error))
    elif isinstance(msg, SystemMessage) and msg.subtype == "init":
        state["model"] = msg.data.get("model")
    elif isinstance(msg, ResultMessage):
        secs = msg.duration_ms / 1000
        n = state.get("calls", 0)
        parts = [f"#{state.get('turn_no', 1)}", f"{n} tool call{'s' if n != 1 else ''}", f"{secs:.1f}s"]
        if msg.total_cost_usd:
            parts.append(f"${msg.total_cost_usd:.4f}")
        if msg.is_error or msg.subtype != "success":
            console.print(S.result(f"{msg.subtype}: {'; '.join(msg.errors or [])}", error=True))
        console.print(S.footer(*parts))


def extra_tags(typed: str, scaffold_tags: tuple[str, ...]) -> list[str]:
    tags = [t.strip().lower() for t in typed.split(",") if t.strip()]
    return [t for t in dict.fromkeys(tags) if t not in scaffold_tags]


def asks(text: str) -> bool:
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
    return not changed_keys(draft, args)


Changed = list[tuple[str, str, str]]


class Approver:
    """Answers Cortex's can_use_tool requests, one at a time. Submitting the /new form approves
    exactly that draft; anything the model changed is shown as a − / + diff."""

    def __init__(self, ask: Callable[[str, str, Changed], Awaitable[str]]):
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
            changed: Changed = []
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
                changed = [(k, str(self.draft.get(k, "")), str(args.get(k, ""))) for k in changed_keys(self.draft, args)]
                rest = {k: v for k, v in args.items() if k not in {c[0] for c in changed}}
                detail = " · ".join(f"{k} {v}" for k, v in rest.items())
            while True:
                answer = (await self.ask(title, detail, changed)).strip().lower()
                if answer in ("a", "always"):
                    self.always.add(title)
                    return PermissionResultAllow()
                if answer in ("y", "yes"):
                    return PermissionResultAllow()
                if answer in ("n", "no"):
                    return PermissionResultDeny(message="The user declined this call. Ask what to do instead.")


def describe_permission(tool_name: str, inp: dict[str, Any]) -> tuple[str, str]:
    resource = str(inp.get("resource", "")) if isinstance(inp, dict) else ""
    if tool_name == "MCP":
        first, _, rest = resource.partition("\n")
        detail = rest.removeprefix("Input:").strip()
        return _short(first.strip()), detail
    return tool_name, resource or json.dumps(inp, indent=1)


# ---------------------------------------------------------------- local commands

class SlashCompleter(Completer):
    """Commands, then for /new the scaffold menu path one word at a time: /new python cli."""

    def __init__(self, commands: dict[str, str], skills: dict[str, str], scaffolds: dict[str, Scaffold] | None = None):
        self.items = {**{c: (d, "command") for c, d in commands.items()},
                      **{f"/{n}": (d, "skill") for n, d in skills.items()}}
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
                        yield Completion(word, start_position=-len(partial), display_meta=sc.title if leaf else "…")
            return
        if not text.startswith("/") or " " in text:
            return
        for cmd, (desc, kind) in self.items.items():
            if cmd.startswith(text):
                meta = _first_sentence(desc, 46).ljust(46) + f"  {kind:>8}"
                yield Completion(cmd, start_position=-len(text), display=cmd.ljust(20), display_meta=meta)


class Repl:
    def __init__(self, cwd: Path, model: str | None = None, connection: str | None = None,
                 effort: str | None = "low"):
        self.cwd = Path(cwd).resolve()
        self.console = S.console()
        self.canon = Canon()
        self.skills = Skills()
        self.approver = Approver(self._prompt_approval)
        self._sigint = None
        self.agent = Agent(self.cwd, ask_permission=self.approver, model=model,
                           connection=connection, effort=effort, canon=self.canon, skills=self.skills)
        self.state: dict = {}
        self.turn_no = 0
        self._status = None
        self._server: http.server.ThreadingHTTPServer | None = None
        self._where = ""
        home = Path.home() / ".ds"
        home.mkdir(exist_ok=True)
        self.pt_style = Style.from_dict(S.pt_style())
        self.session = PromptSession(
            history=FileHistory(str(home / "history")),
            completer=SlashCompleter(COMMANDS, {n: s.description for n, s in self.skills.all.items()},
                                     self.canon.scaffolds),
            complete_while_typing=True,
            bottom_toolbar=self._toolbar,
            style=self.pt_style,
            reserve_space_for_menu=8,
        )

    def _w(self) -> int:
        return S.width(self.console)

    def _print(self, lines) -> None:
        for line in lines:
            self.console.print(line)

    # -- chrome
    def banner(self) -> None:
        shell = "found" if docs_shell_path() else "not found"
        facts = [("cwd", _tilde(self.cwd, 30)),
                 ("canon", f"{len(self.canon.standards)} standards · {len(self.canon.scaffolds)} scaffolds"),
                 ("skills", f"{len(self.skills.all)} from skills-os"),
                 ("docs", f"docs-ds {shell}"),
                 ("model", f"{self.agent.model or 'auto'} · effort {self.agent.effort or 'default'}")]
        self._print(S.banner(f"v{__version__}", facts,
                             ["/new starts a project · /help lists commands", "ctrl-d leaves · ctrl-c twice too"],
                             _tilde(self.canon.root, 60), "start, check and grow", w=self._w()))
        self.console.print()

    def _refresh_where(self) -> None:
        try:
            repo = reconcile.find_repo(self.cwd)
            self._where = reconcile.check(repo, self.canon).summary() if repo else "not a ds repo"
        except Exception as e:  # noqa: BLE001 - the toolbar must never take the terminal down
            self._where = f"status unavailable ({type(e).__name__})"

    def _toolbar(self):
        model = self.state.get("model") or self.agent.model or "auto"
        left = f"{self.cwd.name} · {self._where} · {model} · {self.agent.effort or 'default'} · " \
               f"{'connected' if self.agent.connected else 'idle'}"
        try:
            cols = get_app().output.get_size().columns
        except Exception:  # noqa: BLE001
            cols = self._w()
        return S.toolbar(left, f"#{self.turn_no}", cols)

    def _prompt_message(self):
        cols = self._w()
        tag = " New session " if self.turn_no == 0 else f" #{self.turn_no + 1} "
        return [("class:rule", "┌" + "─" * (cols - 3 - len(tag))), ("class:band", tag), ("class:rule", "─┐\n"),
                ("class:rule", "│ "), ("class:prompt", G.prompt + " ")]

    # -- permissions
    async def _prompt_approval(self, title: str, detail: str, changed: Changed = ()) -> str:
        """A warn-edged frame on the rail; − / + for what the model changed from the form."""
        if self._status:
            self._status.stop()
        try:
            rows: list[Text | None] = []
            for k, before, after in changed:
                rows.append(S.labelled(k, Text(f"− {before}", style="err"), indent=0))
                rows.append(S.labelled("", Text(f"+ {after}", style="ok"), indent=0))
            for ln in (detail or "(no input)").splitlines()[:6]:
                rows.append(Text(ln, style="muted"))
            head = Text.assemble((f"Allow {title}?", "warn bold"), (" · changed from your form", "dim") if changed else "")
            keys = Text.assemble((" y ", "key"), (" yes · ", "dim"), ("a", "bold"), (" always this session · ", "dim"),
                                 ("n", "bold"), (" no", "dim"))
            self.console.print(Text(G.rail, style="rule"))
            self._print(S.frame(head, rows, kind="approval", keys=keys, w=self._w(), prefix=Text(G.rail + " ", style="rule")))
            return await PromptSession(style=self.pt_style).prompt_async(
                [("class:rule", G.rail + "   "), ("class:prompt", G.prompt + " ")])
        except (KeyboardInterrupt, EOFError):
            return "n"
        finally:
            if self._sigint is not None:
                asyncio.get_running_loop().add_signal_handler(signal.SIGINT, self._sigint)
            if self._status:
                self._status.start()

    # -- local commands
    def cmd_help(self, _: str) -> None:
        for c, d in COMMANDS.items():
            self.console.print(Text.assemble("  ", (f"{c:<22}", "bold"), (d, "muted")))
        self.console.print(Text.assemble("  ", (f"{'/<skill>':<22}", "bold"), ("run a skills-os skill, e.g. /so-best-practice-audit", "muted")))
        self.console.print(Text.assemble("  ", (f"{'anything else':<22}", "bold"), ("goes to Cortex Code, with the knowledge base as tools", "muted")))
        self.console.print(S.hint("ctrl-o open last fold · ctrl-c interrupt · ctrl-d leave"))

    def _adoption(self, sid: str, rep) -> Text:
        if rep is None:
            return Text("")
        if sid in rep.pending:
            return Text("○ pending", style="dim")
        if sid in rep.declined:
            return Text("− declined" + (" · past revisit" if sid in rep.overdue else ""), style="dim")
        return Text(G.ok, style="ok")

    def cmd_canon(self, arg: str) -> None:
        if arg in self.canon.standards:
            s = self.canon.standards[arg]
            self.console.print(S.outcome("ok", s.id, f"v{s.version} · {s.status} · applies to {', '.join(s.applies_to)}"))
            S.agent_lines(self.console, Markdown(self.canon.read(arg)))
            return
        tags = [t.strip() for t in arg.split(",") if t.strip()]
        stds = self.canon.applicable(tags) if tags else sorted(self.canon.standards.values(), key=lambda s: s.id)
        repo = reconcile.find_repo(self.cwd)
        rep = reconcile.check(repo, self.canon) if repo else None
        self.console.print(Text(f"  {'standard':<18}{'v':<4}{'applies to':<20}this project", style="dim"))
        for s in stds:
            self.console.print(Text.assemble("  ", (f"{s.id:<18}", "bold"), (f"{s.version:<4}", "muted"),
                                             f"{', '.join(s.applies_to)[:19]:<20}", self._adoption(s.id, rep)))
        self.console.print(S.fold(f"{len(stds)} standards · /canon <id> reads one"))

    def cmd_skills(self, arg: str) -> None:
        if arg in self.skills.all:
            self.console.print(S.outcome("ok", f"/{arg}", "skills-os"))
            S.agent_lines(self.console, Markdown(self.skills.all[arg].read()))
            return
        for s in self.skills.all.values():
            self.console.print(Text.assemble("  ", (f"/{s.name:<21}", "bold"), (_first_sentence(s.description, 54), "muted")))

    def cmd_status(self, _: str) -> None:
        repo = reconcile.find_repo(self.cwd)
        if repo is None:
            self.console.print(S.hint("not a ds repo · /new creates one"))
            return
        r = reconcile.check(repo, self.canon)
        kind = "ok" if r.ok and not r.pending else ("warn" if r.ok else "err")
        self.console.print(S.outcome(kind, repo.name, r.summary()))
        if r.type:
            self.console.print(S.labelled("scaffold", r.type))
        for p in r.pending:
            self.console.print(S.labelled("pending", Text.assemble((p, "bold"), (" · new", "muted"))))
        for sid, why in r.declined.items():
            self.console.print(S.labelled("declined", Text.assemble((sid, "bold"), (f" · {why}", "muted"),
                                                                     (" · past revisit", "warn") if sid in r.overdue else "")))
        for e in r.errors:
            self._print(S.error(e))

    def cmd_last(self, _: str) -> None:
        text = self.state.get("last_result")
        if not text:
            self.console.print(S.hint("no tool output yet"))
            return
        for ln in text.splitlines():
            self.console.print(Text(" " * S.RESULT_INDENT + ln, style="muted"))

    def cmd_captures(self, _: str) -> None:
        base = reconcile.find_repo(self.cwd) or self.cwd
        drafts = sorted((base / ".ds" / "captures").glob("*.md"))
        if not drafts:
            self.console.print(S.hint("no drafts · ask the agent to capture something worth keeping"))
        for d in drafts:
            self.console.print(Text("  " + str(d.relative_to(base)), style="accent"))

    def cmd_docs(self, _: str) -> None:
        repo = reconcile.find_repo(self.cwd)
        stage = Path(tempfile.mkdtemp(prefix="ds-next-docs-"))
        with self.console.status(S.status_label("Building with docs-ds", 0), spinner=S.SPINNER, spinner_style="accent"):
            content, title = docs.stage(stage, self.canon, self.skills, repo)
            try:
                r = docs.build(content, title, stage / "site", protect=[repo] if repo else [])
            except (ValueError, FileNotFoundError) as e:
                self._print(S.error(str(e)))
                return
        if r.returncode != 0:
            self._print(S.error("docs-ds failed", (r.stdout + r.stderr)[-600:]))
            return
        if self._server:
            self._server.shutdown()
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(stage / "site"))
        handler.log_message = lambda *a, **k: None  # type: ignore[method-assign]
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        port = self._server.server_address[1]
        self.console.print(S.outcome("ok", title, f"serving at http://127.0.0.1:{port}/"))

    def _choose_scaffold(self, words: list[str]) -> tuple[list[Scaffold], list[str]]:
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
            self._print(S.error("the canon has no accepted scaffold for that", "/new alone lists them"))
            return
        by_id = {c.id: c for c in candidates}
        name = rest[0] if rest and scaffold.NAME_RE.match(rest[0]) else ""

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
            return f"{n} standards apply · {c.id} v{c.version} · {', '.join(c.tags)}"

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

        v = await form("New project from the canon", fields, footer, validate, width=self._w())
        if v is None:
            self.console.print(S.hint("cancelled"))
            return
        sc = by_id[v["type"]]
        a = answers(v).resolve(self.canon)
        self.console.print(S.outcome("ok", sc.id, f"v{sc.version} · {a.name} · {a.purpose[:40]}{'…' if len(a.purpose) > 40 else ''}"))
        self.console.print()
        draft = {"scaffold": sc.id, "name": a.name, "purpose": a.purpose, "owner": a.owner}
        self.approver.draft = draft
        await self.turn("New project draft from the /new form. Review it against the canon, then fetch the "
                        f"accepted scaffold and create it, as your instructions say.\n\n{json.dumps(draft, indent=1)}")

    async def cmd_effort(self, arg: str) -> None:
        if arg:
            if arg not in ("minimal", "low", "medium", "high", "xhigh", "max"):
                self._print(S.error("effort is one of minimal, low, medium, high, xhigh, max"))
                return
            await self.agent.set_effort(arg)
        self.console.print(S.labelled("effort", self.agent.effort or "default"))

    async def cmd_model(self, arg: str) -> None:
        if arg:
            await self.agent.set_model(arg)
        self.console.print(S.labelled("model", self.agent.model or self.state.get("model") or "auto"))

    async def cmd_clear(self, _: str) -> None:
        await self.agent.reset()
        self.approver.reset()
        self.state.clear()
        self.turn_no = 0
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
        self.turn_no += 1
        self.state.update(step="Connecting to Cortex Code" if not self.agent.connected else "Thinking",
                          asked=False, turn_no=self.turn_no, calls=0)
        self.console.print(Text(f"#{self.turn_no}", style="dim"))
        started = time.monotonic()

        def label() -> str:
            return S.status_label(self.state["step"], int(time.monotonic() - started))

        self._status = self.console.status(label(), spinner=S.SPINNER, spinner_style="accent")
        self._status.start()

        async def tick():
            while True:
                await asyncio.sleep(1.0)
                if self._status:
                    self._status.update(label())

        ticker = asyncio.ensure_future(tick())
        try:
            async for msg in self.agent.turn(prompt):
                render(self.console, msg, self.state)
                if self._status:
                    self._status.update(label())
        except TurnStalled as e:
            self.console.print(S.result(str(e), error=True))
        except CortexCodeSDKError as e:
            self._print(S.error(f"Cortex Code refused: {e}", "retry, or /clear for a fresh session"))
            await self.agent.reset()
        finally:
            ticker.cancel()
            self._status.stop()
            self._status = None
            self._sigint = None
            loop.remove_signal_handler(signal.SIGINT)
        if interrupted:
            self.console.print(S.result(f"interrupted after {int(time.monotonic() - started)}s · session kept", error=True))
            self.console.print(S.footer(f"#{self.turn_no}"))

    async def handle(self, line: str) -> bool:
        """Returns False to exit."""
        line = line.strip()
        if not line:
            if self.state.get("asked"):
                self.console.print(S.hint("(Enter) keep my answers as they are and continue"))
                await self.turn("Keep my answers exactly as they are and continue. Do not change any value "
                                "I gave and do not fill in anything I did not give.")
            else:
                self.console.print(S.hint("type a message, or / for commands · /new starts a project"))
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
            near = difflib.get_close_matches(cmd, [*COMMANDS, *(f"/{n}" for n in self.skills.all)], 1)
            self._print(S.error(f"{cmd} is not a command", "/help lists them" + (f" · did you mean {near[0]}?" if near else "")))
        return True

    async def run(self) -> None:
        self.banner()
        try:
            last_interrupt = 0.0
            while True:
                self._refresh_where()
                try:
                    line = await self.session.prompt_async(self._prompt_message())
                except KeyboardInterrupt:
                    now = time.monotonic()
                    if now - last_interrupt < 2.0:
                        break
                    last_interrupt = now
                    self.console.print(S.hint("ctrl-c again to leave · or /exit"))
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
