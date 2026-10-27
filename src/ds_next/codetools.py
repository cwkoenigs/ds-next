"""Code intelligence for the agent: the code tools and Snowflake search.

- code    ds-code (`ds-code mcp`), the language servers' answers about the repo: where a symbol is
          defined, every use of it, who calls it, what it calls, a file's outline, the repo at a
          glance, and what the uncommitted changes touch. Every tool only reads.
- search  `cortex search`: Snowflake docs, catalog objects and table details, read-only.

Each is optional: missing tools are simply not offered. Nothing here installs anything.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

CODE = "code"
CODE_TOOLS = ("find_symbol", "references", "callers", "callees", "file_symbols", "definition",
              "repo_overview", "change_impact")


def code_bin() -> str | None:
    return shutil.which("ds-code")


def cortex_bin() -> str | None:
    return shutil.which("cortex")


def mcp_servers(cwd: Path) -> dict[str, dict]:
    """Stdio MCP server configs for the agent, for the tools that are installed. On Windows `ds-code`
    is npm's .cmd shim, which an agent can only start through cmd."""
    servers: dict[str, dict] = {}
    if c := code_bin():
        args = ["mcp", str(Path(cwd).resolve())]
        servers[CODE] = ({"type": "stdio", "command": "cmd", "args": ["/c", c, *args]} if os.name == "nt"
                         else {"type": "stdio", "command": c, "args": args})
    return servers


def read_only_ids(servers: dict[str, dict]) -> set[str]:
    return {f"mcp__{CODE}__{t}" for t in CODE_TOOLS} if CODE in servers else set()


def snowflake_search(kind: str, query: str, connection: str | None = None, timeout: int = 60) -> tuple[str, bool]:
    """(text, is_error) from `cortex search <kind> <query>`."""
    if kind not in ("docs", "object", "table-details"):
        return f"kind must be docs, object or table-details, not {kind!r}", True
    c = cortex_bin()
    if c is None:
        return "cortex is not installed", True
    cmd = [c, "search", kind, query] + (["--connection", connection] if connection else [])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return f"cortex search took longer than {timeout}s", True
    if r.returncode != 0:
        return (r.stderr or r.stdout).strip()[:1000], True
    try:
        return str(json.loads(r.stdout).get("results", r.stdout))[:12000], False
    except ValueError:
        return r.stdout[:12000], False
