"""Which agent runs the turns, and the SDK names for it.

Claude Code (claude-agent-sdk) or Cortex Code (snowflake-cortex-agent-sdk, Snowflake's fork of
the same SDK: the same message types and tool helpers, options that differ in a few names).
Chosen by DS_AGENT, then `agent = "..."` in ~/.ds/config.toml (`ds-next setup --agent` writes
it), then whichever CLI is on PATH, Cortex first when both are. Everything else imports from
here, so nothing but this module knows which one is running.
"""
from __future__ import annotations

import os
import shutil
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
    "backend",
    "configured",
    "create_sdk_mcp_server",
    "options",
    "tool",
    "tool_id",
]


def options(*, cwd: str, mcp_servers: dict[str, Any], append_system_prompt: str, can_use_tool: Any,
            model: str | None, connection: str | None, effort: str | None, resume: str | None) -> Any:
    """The options object for the running backend, from the one set of values the terminal has."""
    if BACKEND == "claude":
        return _Options(
            cwd=cwd,
            mcp_servers=mcp_servers,
            strict_mcp_config=True,           # the terminal's own servers only: `ds` is also registered for plain sessions
            system_prompt={"type": "preset", "preset": "claude_code", "append": append_system_prompt},
            setting_sources=["user", "project"],   # the repo's CLAUDE.md and the user's settings, as a normal session has
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
