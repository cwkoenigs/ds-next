"""Cortex Code, driven through cortex-code-agent-sdk, with the knowledge base as tools.

The tools run in this process (an SDK MCP server named "ds"), so the agent reads the same
canon and skills the deterministic commands read, and the only thing that writes a project is
scaffold.write. Read-only tools are pre-approved; writes go through the UI's permission prompt.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from cortex_code_agent_sdk import (
    CortexCodeAgentOptions,
    CortexCodeSDKClient,
    Message,
    PermissionResultAllow,
    PermissionResultDeny,
    create_sdk_mcp_server,
    tool,
)

from . import reconcile, scaffold
from .kb import Canon, Skills

SERVER = "ds"
READ_ONLY = ("canon_list", "canon_read", "skills_list", "skill_read", "project_status")
WRITES = ("scaffold_project", "capture")
READ_ONLY_IDS = {f"mcp__{SERVER}__{t}" for t in READ_ONLY}


def _text(s: str, error: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {"content": [{"type": "text", "text": s}]}
    if error:
        out["is_error"] = True
    return out


def tools(canon: Canon, skills: Skills, cwd: Path) -> list:
    @tool("canon_list", "List the canon standards that apply to a set of repo tags "
          "(comma-separated, e.g. 'python,cli'). Empty tags lists every standard.", {"tags": str})
    async def canon_list(args):
        tags = [t.strip() for t in args.get("tags", "").split(",") if t.strip()]
        stds = canon.applicable(tags) if tags else sorted(canon.standards.values(), key=lambda s: s.id)
        return _text("\n".join(f"{s.id} v{s.version} [{', '.join(s.applies_to)}] {s.title}" for s in stds))

    @tool("canon_read", "Read one standard's full text by id.", {"id": str})
    async def canon_read(args):
        try:
            return _text(canon.read(args["id"]))
        except KeyError as e:
            return _text(str(e), error=True)

    @tool("skills_list", "List the skills-os procedures (name: description).", {})
    async def skills_list(args):
        return _text("\n".join(f"{s.name}: {s.description}" for s in skills.all.values())
                     or "skills-os not found")

    @tool("skill_read", "Read one skills-os SKILL.md by name, to follow its procedure.", {"name": str})
    async def skill_read(args):
        sk = skills.all.get(args["name"])
        return _text(sk.read()) if sk else _text(f"no skill {args['name']!r}", error=True)

    @tool("project_status", "Reconcile the repo at the working directory against the canon: "
          "adopted, declined, pending, errors.", {})
    async def project_status(args):
        repo = reconcile.find_repo(cwd)
        if repo is None:
            return _text(f"{cwd} is not a ds repo (no .ds/manifest.toml up the tree)")
        r = reconcile.check(repo, canon)
        return _text(json.dumps({"summary": r.summary(), "tags": r.tags, "adopted": r.adopted,
                                 "declined": r.declined, "pending": r.pending,
                                 "overdue_declines": r.overdue, "errors": r.errors}, indent=1))

    @tool("scaffold_project", "Create a new repository from interview answers. The only way to "
          "create a project: never write project files yourself.", {
              "type": "object",
              "properties": {
                  "name": {"type": "string", "description": "lowercase-with-dashes"},
                  "purpose": {"type": "string", "description": "one line"},
                  "owner": {"type": "string"},
                  "kind": {"type": "string", "enum": list(scaffold.KINDS)},
                  "tags": {"type": "array", "items": {"type": "string"}},
                  "test_cmd": {"type": "string"}, "lint_cmd": {"type": "string"},
                  "snowflake": {"type": "string", "description": "DATABASE.SCHEMA or empty"},
                  "notes": {"type": "string", "description": "what future-you should know"},
                  "declines": {"type": "object", "additionalProperties": {"type": "string"},
                               "description": "standard id -> reason, for standards declined now"},
                  "directory": {"type": "string", "description": "parent directory; default cwd"},
              },
              "required": ["name", "purpose", "kind"],
          })
    async def scaffold_project(args):
        args = dict(args)
        parent = Path(args.pop("directory", "") or cwd).expanduser()
        try:
            a = scaffold.Answers(**{k: v for k, v in args.items() if v not in (None, "") or k == "snowflake"})
            files = scaffold.write(a, parent / a.name, canon, skills)
            r = reconcile.check(parent / a.name, canon)
        except (ValueError, TypeError, FileExistsError) as e:
            return _text(f"not created: {e}", error=True)
        return _text(f"created {parent / a.name}\n{r.summary()}\nfiles:\n" + "\n".join(files))

    @tool("capture", "Draft a proposed canon standard from something learned in this session "
          "(a gotcha, a decision, a pattern). Writes a draft for review; never edits the canon.", {
              "type": "object",
              "properties": {"title": {"type": "string"}, "body": {"type": "string"},
                             "applies_to": {"type": "array", "items": {"type": "string"}}},
              "required": ["title", "body"]})
    async def capture(args):
        slug = re.sub(r"[^a-z0-9]+", "-", args["title"].lower()).strip("-")[:50]
        base = reconcile.find_repo(cwd) or cwd
        path = base / ".ds" / "captures" / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        applies = json.dumps(args.get("applies_to") or ["*"])
        path.write_text(f"---\nid: {slug}\nversion: 1\ntitle: {args['title']}\napplies_to: {applies}\n"
                        f"owner: {scaffold._git_user()}\nstatus: proposed\ndate: {dt.date.today()}\n---\n\n"
                        f"# {args['title']}\n\n{args['body'].strip()}\n")
        return _text(f"draft at {path}. To publish: open a canon merge request with this file "
                     f"(the so-capture skill does it), then run scripts/build_index.py.")

    return [canon_list, canon_read, skills_list, skill_read, project_status, scaffold_project, capture]


def system_prompt(cwd: Path, canon: Canon, skills: Skills) -> str:
    repo = reconcile.find_repo(cwd)
    where = (f"The working directory is inside the ds repo {repo.name}." if repo
             else "The working directory is not a ds repo yet.")
    return f"""You are ds, the front door to the team's knowledge system, running in a terminal.

The knowledge system has three parts, all readable through your `ds` tools:
- the canon: {len(canon.standards)} versioned standards, the only place team rules are written;
- skills-os: {len(skills.all)} procedures (SKILL.md files) for how the team works;
- docs-ds: the site that renders both (the user runs /docs; you do not).

Rules:
- Cite standards as [[id]] pointers and read them with canon_read before relying on them.
  Never paste a standard's text into a repo file.
- When the user wants a new project, interview them, then call scaffold_project. Ask at most
  two questions per message and offer a default in brackets for each: purpose (one line),
  kind (cli or package; ds-cli itself is a cli), owner [{scaffold._git_user()}], extra tags
  beyond the ones the kind implies (python, package, and cli for a cli) [none], test command [uv run pytest -q], Snowflake DATABASE.SCHEMA [none],
  anything future-you should know, any standard they already know they will decline and why.
  Use canon_list with the full tag list to show what will apply before creating. Summarize the answers
  in one short list and create when the user confirms. Never write project files yourself.
- When a skill fits the request, skill_read it and follow it.
- When the session uncovers something the team should remember, offer to capture it.
- Be brief. This is a terminal.

{where} Today is {dt.date.today()}."""


PermissionAsk = Callable[[str, dict[str, Any], Any], Awaitable[Any]]


class Agent:
    """One Cortex Code session. Connects on the first turn; `reset` starts a new session."""

    def __init__(self, cwd: Path, ask_permission: PermissionAsk | None = None,
                 model: str | None = None, connection: str | None = None,
                 canon: Canon | None = None, skills: Skills | None = None):
        self.cwd = Path(cwd).resolve()
        self.canon = canon or Canon()
        self.skills = skills or Skills()
        self.ask_permission = ask_permission
        self.model = model
        self.connection = connection
        self.session_id: str | None = None
        self._client: CortexCodeSDKClient | None = None

    def options(self) -> CortexCodeAgentOptions:
        server = create_sdk_mcp_server(SERVER, tools=tools(self.canon, self.skills, self.cwd))
        return CortexCodeAgentOptions(
            cwd=str(self.cwd),
            mcp_servers={SERVER: server},
            # No allowed_tools: Cortex treats that list as exclusive (everything else is blocked
            # before can_use_tool is asked). Read-only ds tools are approved in _permit instead.
            append_system_prompt=system_prompt(self.cwd, self.canon, self.skills),
            can_use_tool=self._permit,
            model=self.model,
            connection=self.connection,
        )

    async def _permit(self, tool_name: str, inp: dict[str, Any], ctx: Any):
        """Cortex asks with a kind ("MCP", "Bash", ...) and a resource string whose first line
        names the MCP tool. Reading the knowledge base never needs a human."""
        resource = str(inp.get("resource", "")) if isinstance(inp, dict) else ""
        if tool_name == "MCP" and resource.split("\n", 1)[0].strip() in READ_ONLY_IDS:
            return PermissionResultAllow()
        if self.ask_permission is None:
            return PermissionResultDeny(message="No one is here to approve this call.")
        return await self.ask_permission(tool_name, inp, ctx)

    @property
    def connected(self) -> bool:
        return self._client is not None

    async def connect(self) -> None:
        if self._client is None:
            client = CortexCodeSDKClient(self.options())
            await client.connect()
            self._client = client

    async def turn(self, prompt: str) -> AsyncIterator[Message]:
        await self.connect()
        assert self._client is not None
        await self._client.query(prompt)
        async for msg in self._client.receive_response():
            sid = getattr(msg, "session_id", None)
            if sid:
                self.session_id = sid
            yield msg

    async def interrupt(self) -> None:
        if self._client is not None:
            await self._client.interrupt()

    async def set_model(self, model: str | None) -> None:
        self.model = model
        if self._client is not None:
            await self._client.set_model(model)

    async def close(self) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            await client.disconnect()

    async def reset(self) -> None:
        await self.close()
        self.session_id = None
