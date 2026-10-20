"""`ds-next` with no arguments opens the terminal. The subcommands are the same verbs without a
model, for scripts, hooks and CI — same glyphs and columns, colour only on a TTY."""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

import typer
from rich.markdown import Markdown
from rich.text import Text

from . import docs as docs_mod
from . import reconcile as reconcile_mod
from . import scaffold
from . import ui_style as S
from .kb import Canon, Skills

app = typer.Typer(add_completion=False, invoke_without_command=True,
                  help="ds, rebuilt small: the team's knowledge system in a Claude-Code-style terminal.")
canon_app = typer.Typer(help="Read the canon.", no_args_is_help=True)
app.add_typer(canon_app, name="canon")
out = S.console(color=sys.stdout.isatty(), soft_wrap=True)


def _err(what: str, fix: str = "") -> None:
    for line in S.error(what, fix):
        out.print(line)


@app.callback()
def main(ctx: typer.Context,
         model: str | None = typer.Option(None, "--model", "-m", help="Cortex model"),
         connection: str | None = typer.Option(None, "--connection", "-c", help="Snowflake connection"),
         effort: str = typer.Option("low", "--effort", help="thinking effort: minimal, low, medium, high")):
    if ctx.invoked_subcommand is None:
        from .ui import main as repl
        repl(Path.cwd(), model, connection, effort)


@app.command()
def new(name: str,
        answers: Path = typer.Option(..., "--answers", help="TOML file with the interview answers"),
        directory: Path = typer.Option(Path("."), "--dir", help="parent directory")):
    """Scaffold a repo from an answers file, without the agent (the terminal's /new runs the same code)."""
    try:
        a = scaffold.Answers.from_toml(answers)
        if a.name != name:
            raise ValueError(f"answers file is for {a.name!r}, not {name!r}")
        files = scaffold.write(a, directory / name)
    except (ValueError, TypeError, FileExistsError) as e:
        _err(f"not created: {e}")
        raise typer.Exit(2)
    rep = reconcile_mod.check(directory / name)
    out.print(S.outcome("ok", name, f"{len(files)} files · {(directory / name).resolve()}"))
    out.print(S.labelled("canon", rep.summary()))


def _report(repo: Path, rep) -> None:
    kind = "ok" if rep.ok and not rep.pending else ("warn" if rep.ok else "err")
    out.print(S.outcome(kind, repo.name, rep.summary()))
    if rep.outputs:
        out.print(S.labelled("outputs", f"{', '.join(rep.outputs)} · declared by the {rep.type or 'scaffold'} type"))
    for p in rep.pending:
        out.print(S.labelled("pending", p))
    for sid, why in rep.declined.items():
        out.print(S.labelled("declined", f"{sid} · {why}" + (" · past revisit" if sid in rep.overdue else "")))
    for e in rep.errors:
        _err(e)
    if rep.pending:
        out.print(S.hint("open ds-next and run /status to adopt"))


@app.command()
def reconcile(path: Path = typer.Argument(Path("."), help="repo, or a directory inside one"),
              quiet: bool = typer.Option(False, "--quiet", help="one line; for the pre-push hook")):
    """Offline check against the canon. Exit 1 only on a broken pointer or a bad manifest."""
    repo = reconcile_mod.find_repo(path.resolve())
    if repo is None:
        _err(f"{path.resolve()} is not a ds repo")
        raise typer.Exit(1)
    rep = reconcile_mod.check(repo)
    if quiet:
        if rep.pending:
            out.print(S.outcome("warn", "ds", f"{len(rep.pending)} standard(s) pending · {', '.join(rep.pending)} · "
                                              "open ds-next and run /status"))
        for e in rep.errors:
            _err(e)
    else:
        _report(repo, rep)
    raise typer.Exit(0 if rep.ok else 1)


@canon_app.command("list")
def canon_list(tags: str = typer.Option("", help="comma-separated repo tags")):
    """Standards, optionally only those that apply to the tags."""
    c = Canon()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    out.print(Text(f"  {'standard':<18}{'v':<4}{'applies to':<20}title", style="dim"))
    for s in (c.applicable(tag_list) if tag_list else sorted(c.standards.values(), key=lambda s: s.id)):
        out.print(Text.assemble("  ", (f"{s.id:<18}", "bold"), (f"{s.version:<4}", "muted"),
                                f"{', '.join(s.applies_to)[:19]:<20}", (s.title, "muted")))


@canon_app.command("read")
def canon_read(sid: str):
    """Print a standard."""
    out.print(Markdown(Canon().read(sid)))


def _first_sentence(s: str) -> str:
    from .ui import _first_sentence as f
    return f(s)


@app.command()
def blocks():
    """The canon's accepted code blocks."""
    for b in Canon().blocks.values():
        out.print(Text.assemble("  ", (f"{b.id:<28}", "bold"), (f"v{b.version:<4}{b.status:<10}", "muted"), b.title))


@app.command()
def add(block: str, path: Path = typer.Argument(Path("."), help="repo, or a directory inside one")):
    """Add an accepted canon block to this repo, without the agent."""
    repo = reconcile_mod.find_repo(path.resolve())
    if repo is None:
        _err(f"{path.resolve()} is not a ds repo")
        raise typer.Exit(1)
    try:
        done = scaffold.add_block(repo, block, Canon())
    except (ValueError, FileExistsError) as e:
        _err(f"not added: {e}")
        raise typer.Exit(2) from None
    out.print(S.outcome("ok", f"{done['block']} v{done['version']}", f"{done['note']} · {', '.join(done['files']) or 'no files'}"))
    if done["requires"]:
        out.print(S.labelled("requires", f"{', '.join(done['requires'])} · run uv sync"))
    if done["manual"]:
        out.print(S.labelled("by hand", ", ".join(done["manual"])))


@app.command()
def skills():
    """skills-os procedures."""
    for s in Skills().all.values():
        out.print(Text.assemble("  ", (f"/{s.name:<21}", "bold"), (_first_sentence(s.description), "muted")))


@app.command()
def docs(output: Path = typer.Option(None, "--out", help="build directory (default: a temp dir)")):
    """Build this repo's docs, or the whole knowledge base outside a repo, with docs-ds."""
    repo = reconcile_mod.find_repo(Path.cwd())
    stage = Path(tempfile.mkdtemp(prefix="ds-next-docs-"))
    content, title = docs_mod.stage(stage, Canon(), Skills(), repo)
    target = output or stage / "site"
    try:
        r = docs_mod.build(content, title, target, protect=[repo] if repo else [])
    except (ValueError, FileNotFoundError) as e:
        _err(str(e))
        raise typer.Exit(1) from None
    if r.returncode != 0:
        _err("docs-ds failed", (r.stdout + r.stderr)[-2000:])
        raise typer.Exit(1)
    out.print(S.outcome("ok", title, str(target.resolve())))


@app.command()
def setup(check: bool = typer.Option(False, "--check", help="report what would change; write nothing")):
    """Connect this machine's Cortex Code to the knowledge system. Safe to rerun."""
    from . import setup as setup_mod

    ok = setup_mod.setup_cortex(check, lambda line: out.print(S.labelled("", line)))
    if not check:
        out.print(S.hint("restart Cortex Code to pick this up"))
    raise typer.Exit(0 if ok else 1)


@app.command()
def ask(prompt: str = typer.Argument(..., help="the request; @file reads it from a file"),
        yes: bool = typer.Option(False, "--yes", help="allow ds write tools (scaffold, block_add, code_add, capture)"),
        yes_all: bool = typer.Option(False, "--yes-all", help="allow every tool, Bash and file edits included"),
        effort: str = typer.Option("low", "--effort", help="thinking effort: minimal, low, medium, high, max"),
        model: str | None = typer.Option(None, "--model", "-m")):
    """One turn through Cortex Code, printed the way the terminal prints it."""
    from cortex_agent_sdk.cortexcode import PermissionResultAllow, PermissionResultDeny

    from .agent import Agent, TurnStalled
    from .ui import describe_permission, render

    if prompt.startswith("@"):
        prompt = Path(prompt[1:]).read_text()

    async def permit(tool_name, inp, ctx):
        title, detail = describe_permission(tool_name, inp)
        if yes_all or (yes and title in ("scaffold_project", "block_add", "code_add", "capture")):
            if yes_all:
                out.print(S.result(f"approved by --yes-all: {title} {detail.splitlines()[0][:60] if detail else ''}"))
            return PermissionResultAllow()
        return PermissionResultDeny(message=f"{title} is not allowed in a one-shot run; rerun with --yes "
                                    "for ds write tools, --yes-all for everything, or use the terminal.")

    async def go():
        agent = Agent(Path.cwd(), ask_permission=permit, model=model, effort=effort)
        state: dict = {"turn_no": 1}
        try:
            async for msg in agent.turn(prompt):
                render(out, msg, state)
        except TurnStalled as e:
            out.print(S.result(str(e), error=True))
            raise typer.Exit(3) from None
        finally:
            await agent.close()

    asyncio.run(go())


@app.command()
def mcp() -> None:
    """Serve the knowledge-base tools over stdio MCP, for any MCP client (the same tools Cortex gets)."""
    from mcp.server.stdio import stdio_server

    from .agent import SERVER, create_sdk_mcp_server, tools

    server = create_sdk_mcp_server(SERVER, tools=tools(Canon(), Skills(), Path.cwd()))["instance"]

    async def serve() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(serve())


if __name__ == "__main__":
    sys.exit(app())
