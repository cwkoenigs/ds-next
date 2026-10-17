"""`ds-next` with no arguments opens the terminal. The subcommands are the same verbs without a
model, for scripts, hooks and CI."""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown

from . import docs as docs_mod
from . import reconcile as reconcile_mod
from . import scaffold
from .kb import Canon, Skills

app = typer.Typer(add_completion=False, invoke_without_command=True,
                  help="ds, rebuilt small: the team's knowledge system in a Claude-Code-style terminal.")
canon_app = typer.Typer(help="Read the canon.", no_args_is_help=True)
app.add_typer(canon_app, name="canon")
out = Console(highlight=False, markup=False, soft_wrap=True)


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
        out.print(f"not created: {e}", style="red")
        raise typer.Exit(2)
    rep = reconcile_mod.check(directory / name)
    out.print(f"created {(directory / name).resolve()} ({len(files)} files)\n{rep.summary()}")


@app.command()
def reconcile(path: Path = typer.Argument(Path("."), help="repo, or a directory inside one"),
              quiet: bool = typer.Option(False, "--quiet", help="one line; for the pre-push hook")):
    """Offline check against the canon. Exit 1 only on a broken pointer or a bad manifest."""
    repo = reconcile_mod.find_repo(path.resolve())
    if repo is None:
        out.print(f"{path.resolve()} is not a ds repo")
        raise typer.Exit(1)
    rep = reconcile_mod.check(repo)
    if quiet:
        if rep.pending:
            out.print(f"ds: {len(rep.pending)} standard(s) pending ({', '.join(rep.pending)}). "
                      "Open ds-next and run /status.")
    else:
        out.print(rep.summary())
        for p in rep.pending:
            out.print(f"  pending  {p}")
        for sid, why in rep.declined.items():
            out.print(f"  declined {sid}: {why}")
    for e in rep.errors:
        out.print(f"  error    {e}", style="red")
    raise typer.Exit(0 if rep.ok else 1)


@canon_app.command("list")
def canon_list(tags: str = typer.Option("", help="comma-separated repo tags")):
    """Standards, optionally only those that apply to the tags."""
    c = Canon()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    for s in (c.applicable(tag_list) if tag_list else sorted(c.standards.values(), key=lambda s: s.id)):
        out.print(f"{s.id:22} v{s.version}  {s.title}")


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
        out.print(f"{b.id:28} v{b.version} {b.status:9} {b.title}")


@app.command()
def add(block: str, path: Path = typer.Argument(Path("."), help="repo, or a directory inside one")):
    """Add an accepted canon block to this repo, without the agent."""
    repo = reconcile_mod.find_repo(path.resolve())
    if repo is None:
        out.print(f"{path.resolve()} is not a ds repo", style="red")
        raise typer.Exit(1)
    try:
        done = scaffold.add_block(repo, block, Canon())
    except (ValueError, FileExistsError) as e:
        out.print(f"not added: {e}", style="red")
        raise typer.Exit(2) from None
    out.print(f"{done['note']}: {done['block']} v{done['version']} -> {', '.join(done['files']) or 'no files'}")
    if done["requires"]:
        out.print(f"requirements added: {', '.join(done['requires'])}. Run uv sync.")
    if done["manual"]:
        out.print(f"add these by hand, pyproject.toml has no one-line list for them: {', '.join(done['manual'])}")


@app.command()
def skills():
    """skills-os procedures."""
    for s in Skills().all.values():
        out.print(f"/{s.name:28} {_first_sentence(s.description)}")


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
        out.print(str(e), style="red")
        raise typer.Exit(1) from None
    if r.returncode != 0:
        out.print((r.stdout + r.stderr)[-2000:], style="red")
        raise typer.Exit(1)
    out.print(f"built {title} at {target.resolve()}")


@app.command()
def ask(prompt: str = typer.Argument(..., help="the request; @file reads it from a file"),
        yes: bool = typer.Option(False, "--yes", help="allow ds write tools (scaffold, block_add, capture)"),
        yes_all: bool = typer.Option(False, "--yes-all", help="allow every tool, Bash and file edits included: "
                                     "only for a scratch repo you will inspect afterwards"),
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
        if yes_all or (yes and title in ("scaffold_project", "block_add", "capture")):
            if yes_all:
                out.print(f"  ⎿  approved by --yes-all: {title} {detail.splitlines()[0][:100] if detail else ''}",
                          style="yellow")
            return PermissionResultAllow()
        return PermissionResultDeny(message=f"{title} is not allowed in a one-shot run; rerun with --yes "
                                    "for ds write tools, --yes-all for everything, or use the terminal.")

    async def go():
        agent = Agent(Path.cwd(), ask_permission=permit, model=model, effort=effort)
        state: dict = {}
        try:
            async for msg in agent.turn(prompt):
                render(out, msg, state)
        except TurnStalled as e:
            out.print(f"  ⎿  {e}", style="yellow")
            raise typer.Exit(3) from None
        finally:
            await agent.close()

    asyncio.run(go())


if __name__ == "__main__":
    sys.exit(app())


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
