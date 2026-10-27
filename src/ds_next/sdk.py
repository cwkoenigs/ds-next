"""Which agent runs the turns, and the SDK names for it.

Claude Code (claude-agent-sdk) or Cortex Code (snowflake-cortex-agent-sdk, Snowflake's fork of
the same SDK: the same message types and tool helpers, options that differ in a few names).
Chosen by DS_AGENT, then `agent = "..."` in ~/.ds/config.toml (`ds-next setup --agent` writes
it), then whichever CLI is on PATH, Cortex first when both are. Everything else imports from
here, so nothing but this module knows which one is running.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

BACKENDS = ("claude", "cortex")
CONFIG = Path.home() / ".ds" / "config.toml"
LABELS = {"claude": "Claude Code", "cortex": "Cortex Code"}


def configured() -> str | None:
    """The agent named in ~/.ds/config.toml, or None."""
    try:
        value = tomllib.loads(CONFIG.read_text()).get("agent")
    except (OSError, ValueError):
        return None
    return value if value in BACKENDS else None


def backend() -> str:
    env = os.environ.get("DS_AGENT", "").strip().lower()
    if env in BACKENDS:
        return env
    chosen = configured()
    if chosen:
        return chosen
    if shutil.which("cortex"):
        return "cortex"
    if shutil.which("claude"):
        return "claude"
    return "cortex"


BACKEND = backend()
LABEL = LABELS[BACKEND]
CLI = BACKEND            # the executable has the same name

if BACKEND == "claude":
    from claude_agent_sdk import (
        AssistantMessage,
        CLINotFoundError,
        HookMatcher,
        Message,
        PermissionResultAllow,
        PermissionResultDeny,
        ResultMessage,
        SystemMessage,
        TextBlock,
        ThinkingBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
        create_sdk_mcp_server,
        tool,
    )
    from claude_agent_sdk import (
        ClaudeAgentOptions as _Options,
    )
    from claude_agent_sdk import (
        ClaudeSDKClient as SDKClient,
    )
    from claude_agent_sdk import (
        ClaudeSDKError as SDKError,
    )
else:
    from cortex_agent_sdk.cortexcode import (
        AssistantMessage,
        CLINotFoundError,
        Message,
        PermissionResultAllow,
        PermissionResultDeny,
        ResultMessage,
        SystemMessage,
        TextBlock,
        ThinkingBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
        create_sdk_mcp_server,
        tool,
    )
    from cortex_agent_sdk.cortexcode import (
        CortexCodeAgentOptions as _Options,
    )
    from cortex_agent_sdk.cortexcode import (
        CortexCodeSDKClient as SDKClient,
    )
    from cortex_agent_sdk.cortexcode import (
        CortexCodeSDKError as SDKError,
    )

__all__ = [
    "BACKEND",
    "CLI",
    "LABEL",
    "AssistantMessage",
    "CLINotFoundError",
    "Message",
    "PermissionResultAllow",
    "PermissionResultDeny",
    "ResultMessage",
    "SDKClient",
    "SDKError",
    "SystemMessage",
    "TextBlock",
    "ThinkingBlock",
    "ToolResultBlock",
    "ToolUseBlock",
    "UserMessage",
    "ask_first",
    "backend",
    "configured",
    "create_sdk_mcp_server",
    "options",
    "project_hooks",
    "tool",
    "tool_id",
]


# Claude Code's own tools that only read, plan or hand work on: they go as Claude Code decides, so a
# read in the project passes and one outside it asks. A subagent's tools are checked one by one.
CLAUDE_READS = frozenset({"Read", "Glob", "Grep", "LS", "NotebookRead", "TodoWrite", "Task", "Agent", "Skill",
                          "SlashCommand", "ToolSearch", "BashOutput", "TaskOutput", "ExitPlanMode", "EnterPlanMode",
                          "ListMcpResourcesTool", "ReadMcpResourceTool"})


def ask_first(read_only: set[str] | frozenset[str]) -> Any:
    """A PreToolUse callback that sends every other tool to can_use_tool, and so to the person.
    Without it, an allow rule in the person's settings (Bash, or a "don't ask again" saved in Claude
    Code) runs a command unasked. A tool Claude Code adds later asks too. Not a settings-file hook,
    so disableAllHooks leaves it running."""
    async def hook(inp: Any, tool_use_id: str | None, context: Any) -> dict:
        name = str(inp.get("tool_name", "")) if isinstance(inp, dict) else ""
        if name in CLAUDE_READS or name in read_only:
            return {}
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                       "permissionDecisionReason": "ds-next asks the person before anything that is not a read"}}
    return hook


# Where Cortex Code reads a project's settings, and so its hooks: .cortex and .claude, shared and
# local, in the folder it starts in and at the repo's top.
HOOK_FILES = (".cortex/settings.json", ".cortex/settings.local.json", ".claude/settings.json", ".claude/settings.local.json")


def project_hooks(cwd: Path) -> list[tuple[str, list[str], str]]:
    """The hooks a repo's own settings define: each file, what each event runs, and the file's text.
    A hook is shown as its command only when that is all it has; any other field (args, an env, a
    source) shows it whole, as does a file that names hooks but does not read as JSON."""
    try:
        r = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10, check=False)
        top = r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        top = ""
    out: list[tuple[str, list[str], str]] = []
    for d in dict.fromkeys([Path(cwd).resolve(), *([Path(top).resolve()] if top else [])]):
        for rel in HOOK_FILES:
            f = d / rel
            try:
                text = f.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            try:
                data = json.loads(text)
            except ValueError:
                if "hooks" in text.lower():
                    out.append((str(f), [text.strip()], text))
                continue
            hooks = data.get("hooks") if isinstance(data, dict) else None
            if not isinstance(hooks, dict) or not hooks:
                continue
            runs = []
            for event, matchers in hooks.items():
                for m in matchers if isinstance(matchers, list) else []:
                    if not isinstance(m, dict) or not isinstance(m.get("hooks"), list):
                        continue
                    on = f" ({m['matcher']})" if m.get("matcher") else ""
                    for h in m["hooks"]:
                        plain = (isinstance(h, dict) and isinstance(h.get("command"), str)
                                 and set(h) <= {"type", "command", "timeout"})
                        runs.append(f"{event}{on}: {h['command'] if plain else json.dumps(h, separators=(',', ':'))}")
            out.append((str(f), runs or [json.dumps(hooks)], text))
    return out


def options(*, cwd: str, mcp_servers: dict[str, Any], append_system_prompt: str, can_use_tool: Any,
            model: str | None, connection: str | None, effort: str | None, resume: str | None,
            read_only: set[str] | frozenset[str] = frozenset()) -> Any:
    """The options object for the running backend, from the one set of values the terminal has."""
    if BACKEND == "claude":
        return _Options(
            cwd=cwd,
            mcp_servers=mcp_servers,
            strict_mcp_config=True,           # the terminal's own servers only: `ds` is also registered for plain sessions
            system_prompt={"type": "preset", "preset": "claude_code", "append": append_system_prompt},
            setting_sources=["user", "project"],   # the repo's CLAUDE.md and the user's settings, as a normal session has
            # No hooks: a cloned repo's .claude/settings.json could otherwise run a command as the session
            # starts, with nothing asked. This tier outranks project settings and is not policy, so no
            # IT-managed tier drops it; managed hooks still run.
            settings=json.dumps({"disableAllHooks": True}),
            hooks={"PreToolUse": [HookMatcher(hooks=[ask_first(read_only)])]},   # an allow rule never skips the question
            can_use_tool=can_use_tool,
            model=model,
            effort={"minimal": "low"}.get(effort or "", effort) if effort else None,
            resume=resume,
        )
    return _Options(
        cwd=cwd,
        mcp_servers=mcp_servers,
        # No allowed_tools: Cortex treats that list as exclusive (everything else is blocked
        # before can_use_tool is asked). Read-only ds tools are approved in can_use_tool instead.
        append_system_prompt=append_system_prompt,
        can_use_tool=can_use_tool,
        model=model,
        connection=connection,
        effort=effort,
        resume=resume,
        # The terminal brings its own servers in-process. Skip the user's mcp.json: once `ds` is
        # registered there for plain Cortex sessions, loading it here too makes every tool name a
        # duplicate and the API rejects the request.
        extra_args={"only-explicit-mcp-servers": None},
    )


def tool_id(tool_name: str, inp: Any) -> str:
    """The tool being asked about. Cortex asks with a kind ("MCP", "Bash") and a resource string
    whose first line names the MCP tool; Claude Code asks with the tool's own id."""
    if tool_name == "MCP":
        return str(inp.get("resource", "")).split("\n", 1)[0].strip() if isinstance(inp, dict) else ""
    return tool_name
