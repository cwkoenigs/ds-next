"""Code intelligence for the agent: a code graph, a language server, and Snowflake search.

- graph   codebase-memory-mcp (DeusData), a local index of symbols, calls and files. Served with
          its read-only `analysis` profile; ds-next builds the index itself.
- lsp     Serena (oraios), language-server tools: find a symbol, its references, its declaration.
          Its edit tools (replace, insert, rename, delete, memory writes) always ask.
- search  `cortex search`: Snowflake docs, catalog objects and table details, read-only.

Each is optional: missing tools are simply not offered. Nothing here installs anything.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

GRAPH, LSP = "graph", "lsp"

# codebase-memory-mcp --tool-profile=analysis serves only these, all reads (get_file_outline is
# annotated readOnly=False but only outlines one file's declarations).
GRAPH_READ = ("search_graph", "query_graph", "trace_path", "get_code_snippet", "get_file_outline",
              "get_graph_schema", "compare_graphs", "get_architecture", "search_code", "list_projects",
              "index_status", "check_index_coverage", "detect_changes")
# Serena tools annotated readOnly=True; everything else it offers edits files or memories.
LSP_READ = ("search_for_pattern", "get_symbols_overview", "find_symbol", "find_referencing_symbols",
            "find_implementations", "find_declaration", "get_diagnostics_for_file", "read_memory",
            "list_memories", "initial_instructions")


def graph_bin() -> str | None:
    return shutil.which("codebase-memory-mcp")


def serena_bin() -> str | None:
    return shutil.which("serena")


def cortex_bin() -> str | None:
    return shutil.which("cortex")


def graph_project(repo: Path) -> str:
    """The name codebase-memory-mcp gives a repository: its absolute path with / as -."""
    return str(Path(repo).resolve()).strip("/").replace("/", "-")


def mcp_servers(cwd: Path) -> dict[str, dict]:
    """Stdio MCP server configs for Cortex, for the tools that are installed."""
    servers: dict[str, dict] = {}
    if g := graph_bin():
        servers[GRAPH] = {"type": "stdio", "command": g, "args": ["--tool-profile=analysis"]}
    if s := serena_bin():
        servers[LSP] = {"type": "stdio", "command": s,
                        "args": ["start-mcp-server", "--context", "ide", "--project", str(Path(cwd).resolve()),
                                 "--enable-web-dashboard", "false", "--open-web-dashboard", "false"]}
    return servers


def read_only_ids(servers: dict[str, dict]) -> set[str]:
    ids = set()
    if GRAPH in servers:
        ids |= {f"mcp__{GRAPH}__{t}" for t in GRAPH_READ}
    if LSP in servers:
        ids |= {f"mcp__{LSP}__{t}" for t in LSP_READ}
    return ids


def index(repo: Path, timeout: int = 300) -> str:
    """Build or refresh the graph for repo. Returns a one-line summary; never raises."""
    g = graph_bin()
    if g is None:
        return "graph: codebase-memory-mcp not installed"
    repo = Path(repo).resolve()
    if not (repo / ".git").exists():
        return f"graph: {repo.name} is not a git repository, not indexed"
    try:
        r = subprocess.run([g, "cli", "--quiet", "index_repository", json.dumps({"repo_path": str(repo)})],
                           capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return f"graph: indexing {repo.name} took longer than {timeout}s"
    try:
        data = json.loads(r.stdout)
        return f"graph: {data.get('nodes', '?')} symbols, {data.get('edges', '?')} edges in {data.get('project', repo.name)}"
    except ValueError:
        return f"graph: indexing {repo.name} failed: {(r.stderr or r.stdout).strip()[:200]}"


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
