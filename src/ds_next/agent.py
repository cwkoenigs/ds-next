"""The agent (Claude Code or Cortex Code, see sdk.py), driven through its SDK with the knowledge base as tools.

The tools run in this process (an SDK MCP server named "ds"), so the agent reads the same
canon and skills the deterministic commands read, and the only thing that writes a project is
scaffold.write. Read-only tools are pre-approved; writes go through the UI's permission prompt.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from . import code as code_mod
from . import codetools, reconcile, scaffold, sdk
from .kb import Canon, Skills
from .sdk import Message, PermissionResultAllow, PermissionResultDeny, create_sdk_mcp_server, tool

SERVER = "ds"
READ_ONLY = ("canon_list", "canon_read", "skills_list", "skill_read", "project_status",
             "scaffold_list", "scaffold_get", "block_list", "block_get", "snowflake_search",
             "code_search", "code_get")
WRITES = ("scaffold_project", "capture")
READ_ONLY_IDS = {f"mcp__{SERVER}__{t}" for t in READ_ONLY}


ERROR_PREFIX = "ERROR: "


def _text(s: str, error: bool = False) -> dict[str, Any]:
    """A tool result. Cortex Code 1.2.14 drops the is_error flag of in-process tools (checked
    live, with both is_error and isError), so errors also say so in their first word, which
    the model reads and the terminal colours."""
    out: dict[str, Any] = {"content": [{"type": "text", "text": (ERROR_PREFIX + s) if error else s}]}
    if error:
        out["is_error"] = True
    return out


def _arg(args: dict, *names: str) -> str:
    """The first argument present under any of these names. Models mix up `id`, `name`, `ids` and
    `query` across tools; taking the aliases costs nothing and saves a failed turn."""
    for n in names:
        v = args.get(n)
        if v not in (None, "", [], {}):
            return v if isinstance(v, (str, list)) else str(v)
    return ""


def _schema(**props: str) -> dict:
    """A JSON schema with optional string properties: {name: description}."""
    return {"type": "object", "properties": {k: {"type": "string", "description": d} for k, d in props.items()},
            "required": []}


def parse_ids(raw: object) -> list[str]:
    """Symbol ids from a tool argument: a comma-separated string, a JSON list, or a list."""
    if isinstance(raw, list):
        return [str(i).strip() for i in raw if str(i).strip()]
    text = str(raw or "").strip()
    if text.startswith("["):
        try:
            return parse_ids(json.loads(text))
        except ValueError:
            text = text.strip("[]")
    return [i.strip().strip("\"'") for i in text.split(",") if i.strip().strip("\"'")]


def tools(canon: Canon, skills: Skills, cwd: Path, connection: str | None = None) -> list:
    # (scaffold id, version, template hash) the model has fetched this session; scaffold_project
    # accepts only one of these, so the code always comes from a scaffold the model looked at
    fetched: set[tuple[str, int, str]] = set()

    @tool("canon_list", "List the canon standards and gotchas. Optional tags (comma-separated, e.g. "
          "'python,cli') keep only those that apply; no tags lists everything.",
          _schema(tags="comma-separated repo tags; omit to list every standard"))
    async def canon_list(args):
        tags = [t.strip() for t in str(_arg(args, "tags")).split(",") if t.strip()]
        stds = canon.applicable(tags) if tags else sorted(canon.standards.values(), key=lambda s: s.id)
        return _text("\n".join(f"{s.id} v{s.version} {s.status or 'proposed'}{' (gotcha)' if s.kind == 'gotcha' else ''} "
                               f"[{', '.join(s.applies_to)}] {s.title}" for s in stds))

    @tool("canon_read", "Read one standard or gotcha in full, by id (as canon_list prints it).",
          _schema(id="the standard's id, e.g. gotcha-validation", name="alias of id", standard="alias of id"))
    async def canon_read(args):
        sid = str(_arg(args, "id", "name", "standard", "tags")).strip().strip("[]\"'")
        if not sid:
            return _text("pass id: the standard's id, as canon_list prints it", error=True)
        try:
            return _text(canon.read(sid))
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
        return _text(json.dumps({"summary": r.summary(), "type": r.type, "outputs": r.outputs,
                                 "tags": r.tags, "adopted": r.adopted,
                                 "declined": r.declined, "pending": r.pending,
                                 "overdue_declines": r.overdue, "errors": r.errors}, indent=1))

    @tool("scaffold_list", "List the canon's project types (scaffolds): id, version, status, type, the "
          "outputs a repo of that type produces, menu path, tags.", {})
    async def scaffold_list(args):
        return _text("\n".join(f"{sc.id} v{sc.version} {sc.status} type={sc.type or '-'} "
                                f"outputs={','.join(sc.outputs) or 'none'} [{' > '.join(sc.path)}] "
                                f"tags={','.join(sc.tags)} {sc.title}" for sc in canon.scaffolds.values())
                     or "the canon has no scaffolds")

    @tool("scaffold_get", "Fetch one accepted scaffold from the canon: what it is, its version, the "
          "tags it gives a repo, its default commands and the files it creates. Required before "
          "scaffold_project, which takes the version this returns.", {"id": str})
    async def scaffold_get(args):
        sc = canon.scaffolds.get(args["id"])
        if sc is None:
            return _text(f"no scaffold {args['id']!r}; scaffold_list shows them", error=True)
        fetched.add((sc.id, sc.version, sc.hash))
        return _text(json.dumps({"id": sc.id, "version": sc.version, "status": sc.status,
                                 "accepted": sc.accepted, "title": sc.title, "type": sc.type,
                                 "outputs": list(sc.outputs), "tags": sc.tags,
                                 "defaults": sc.defaults, "files": sc.files,
                                 "about": canon.scaffold_about(sc.id)}, indent=1))

    @tool("scaffold_project", "Create a new repository from an accepted canon scaffold and the "
          "answers. The only way to create a project: never write project files yourself.", {
              "type": "object",
              "properties": {
                  "scaffold": {"type": "string", "description": "scaffold id from scaffold_get"},
                  "scaffold_version": {"type": "integer", "description": "the version scaffold_get returned"},
                  "name": {"type": "string", "description": "lowercase-with-dashes"},
                  "purpose": {"type": "string", "description": "one line"},
                  "owner": {"type": "string"},
                  "tags": {"type": "array", "items": {"type": "string"},
                           "description": "extra tags beyond the scaffold's own"},
                  "test_cmd": {"type": "string"}, "lint_cmd": {"type": "string"},
                  "snowflake": {"type": "string", "description": "DATABASE.SCHEMA or empty"},
                  "notes": {"type": "string", "description": "what future-you should know"},
                  "declines": {"type": "object", "additionalProperties": {"type": "string"},
                               "description": "standard id -> reason, for standards declined now"},
                  "directory": {"type": "string", "description": "parent directory; default cwd"},
              },
              "required": ["scaffold", "scaffold_version", "name", "purpose"],
          })
    async def scaffold_project(args):
        args = dict(args)
        parent = Path(args.pop("directory", "") or cwd).expanduser()
        version = args.pop("scaffold_version", None)
        sc = canon.scaffolds.get(args.get("scaffold", ""))
        if sc is None or (sc.id, version, sc.hash) not in fetched:
            current = f"v{sc.version}" if sc else "not in the canon"
            return _text(f"not created: scaffold {args.get('scaffold')!r} ({current}) has not been fetched "
                         f"at v{version} in this session. Call scaffold_get first and pass the version it returns.",
                         error=True)
        try:
            a = scaffold.Answers(**{k: v for k, v in args.items() if v not in (None, "")})
            files = scaffold.write(a, parent / a.name, canon, skills)
            r = reconcile.check(parent / a.name, canon)
        except scaffold.ScaffoldError as e:
            return _text(f"partly created: {e}", error=True)
        except (ValueError, TypeError, FileExistsError) as e:
            return _text(f"not created: {e}", error=True)
        return _text(f"created {parent / a.name} from {sc.id} v{sc.version}\n{r.summary()}\nfiles:\n"
                     + "\n".join(files))

    @tool("adopt_repo", "Bring an existing repository into the knowledge system: writes its "
          ".ds/manifest.toml, an AGENTS.md (or adds the standards section to the one it has), a "
          "DECISIONS.md if it has none, and the pre-push hook. Nothing else changes. Standards stay "
          "pending until the owner adopts them. Call with no overrides first: the reply shows what was "
          "detected (purpose, owner, tags, test and lint), and the user corrects it.", {
              "type": "object",
              "properties": {
                  "directory": {"type": "string", "description": "the repository; default cwd"},
                  "purpose": {"type": "string", "description": "one line; default the README's first sentence"},
                  "owner": {"type": "string", "description": "default the git user"},
                  "tags": {"type": "array", "items": {"type": "string"}, "description": "default detected"},
                  "adopt_all": {"type": "boolean", "description": "adopt every applicable standard now"},
              },
          })
    async def adopt_repo(args):
        args = dict(args)
        repo = Path(args.get("directory") or cwd).expanduser()
        try:
            a = scaffold.detect(repo)
            if args.get("purpose"):
                a.purpose = args["purpose"]
            if args.get("owner"):
                a.owner = args["owner"]
            if args.get("tags"):
                a.tags = list(args["tags"])
            written = scaffold.adopt(repo, a, canon, skills, adopt_all=bool(args.get("adopt_all")))
            r = reconcile.check(repo.resolve(), canon)
        except scaffold.ScaffoldError as e:
            return _text(f"partly adopted: {e}", error=True)
        except (ValueError, TypeError, FileExistsError) as e:
            return _text(f"not adopted: {e}", error=True)
        return _text(f"{repo.resolve()} joined the system\npurpose: {a.purpose}\nowner: {a.owner}\n"
                     f"tags: {', '.join(a.tags)}\ntest: {a.test_cmd or 'none found'}\nlint: {a.lint_cmd or 'none found'}\n"
                     f"wrote: {', '.join(written)}\n{r.summary()}")

    @tool("block_list", "List the canon's accepted code blocks: tested modules to add to a repo instead "
          "of writing that code yourself. Optional comma-separated tags filter them.", {"tags": str})
    async def block_list(args):
        tags = {t.strip() for t in args.get("tags", "").split(",") if t.strip()}
        rows = [b for b in canon.blocks.values() if b.accepted and (not tags or tags & set(b.tags))]
        return _text("\n".join(f"{b.id} v{b.version} module={b.module} tags={','.join(b.tags)} "
                               f"requires={','.join(b.requires) or '-'} :: {b.title}" for b in rows)
                     or "no accepted blocks match")

    @tool("block_get", "Read one block: what it is for, its API, and its full source and tests.", {"id": str})
    async def block_get(args):
        b = canon.blocks.get(args["id"])
        if b is None:
            return _text(f"no block {args['id']!r}; block_list shows them", error=True)
        files = canon.block_files(b.id, "<package>")
        return _text(canon.block_about(b.id) + "\n\n" + "\n\n".join(
            f"--- {path}\n{text}" for path, text in files.items()))

    @tool("block_add", "Add an accepted block to the repo at the working directory: copies its module "
          "into src/<package>/ and its tests into tests/, adds its requirements, records its version. "
          "Import it from your code; never edit the copied file in place.", {"id": str})
    async def block_add(args):
        repo = reconcile.find_repo(cwd)
        if repo is None:
            return _text(f"{cwd} is not a ds repo; create one with /new first", error=True)
        try:
            done = scaffold.add_block(repo, args["id"], canon)
        except (ValueError, FileExistsError) as e:
            return _text(f"not added: {e}", error=True)
        return _text(f"{done['note']}: {done['block']} v{done['version']}\nfiles: {', '.join(done['files']) or '-'}\n"
                     f"requirements added: {', '.join(done['requires']) or '-'} (run uv sync)"
                     + (f"\nadd by hand, no one-line list found: {', '.join(done['manual'])}" if done["manual"] else ""))

    @tool("code_search", "Search the canon's accepted code, one function, class or constant at a time, by "
          "what it does (e.g. 'user text into TOML', 'empty an output folder safely'). Returns ids, "
          "signatures and the lessons each carries. Search before writing code.", {"query": str})
    async def code_search(args):
        hits = code_mod.search(canon, args.get("query", ""))
        code_mod.usage_log("code_search", [h["id"] for h in hits])
        return _text("\n".join(f"{h['id']}{code_mod.label(h['status'])}  {h['signature']}\n    {h['summary'] or '-'}  "
                               f"[lessons: {', '.join(h['lessons']) or '-'}; {h['lines']} lines]" for h in hits)
                     or "nothing matches; try other words, or block_list")

    @tool("code_get", "Read one code symbol by id (block:name, as code_search prints it): its source with "
          "only what it needs, and the tests that cover it.",
          _schema(id="block:name", name="alias of id", query="words to search instead, if you have no id"))
    async def code_get(args):
        sid = str(_arg(args, "id", "name")).strip()
        if not sid:
            query = str(_arg(args, "query"))
            if not query:
                return _text("pass id (block:name), or query to search", error=True)
            hits = code_mod.search(canon, query)
            return _text("no id given; code_search found:\n" + "\n".join(f"{h['id']}  {h['signature']}" for h in hits)
                         if hits else "no id given and nothing matches the query", error=not hits)
        try:
            text = code_mod.get(canon, sid)
        except (ValueError, KeyError) as e:
            return _text(f"{e}; code_search finds ids", error=True)
        code_mod.usage_log("code_get", [sid])
        return _text(text)

    @tool("code_add", "Add code symbols to the repo at the working directory: ids is a comma-separated "
          "list of block:name. Copies each block's module cut down to them (and what they need) into "
          "src/<package>/, with the tests that cover them, and records them in the manifest. Import "
          "them from your code; never edit the copy.",
          _schema(ids="comma-separated block:name ids", id="alias of ids", name="alias of ids", symbols="alias of ids"))
    async def code_add(args):
        repo = reconcile.find_repo(cwd)
        if repo is None:
            return _text(f"{cwd} is not a ds repo; create one with /new first", error=True)
        ids = parse_ids(_arg(args, "ids", "id", "name", "symbols"))
        if not ids:
            return _text("pass ids: comma-separated block:name, as code_search prints them", error=True)
        try:
            done = code_mod.add(repo, ids, canon)
        except (ValueError, FileExistsError, KeyError) as e:
            return _text(f"not added: {e}", error=True)
        return _text("\n".join(
            f"{d['note']}: {d['block']} {d['symbols'] if d['symbols'] == 'all' else ', '.join(d['symbols'])}\n"
            f"  files: {', '.join(d['files']) or '-'}; requirements added: {', '.join(d.get('requires', [])) or '-'}"
            + (f"\n  add by hand: {', '.join(d['manual'])}" if d.get("manual") else "") for d in done))

    @tool("snowflake_search", "Search Snowflake: kind 'docs' (product documentation), 'object' (tables, "
          "views, schemas... in this account's catalog) or 'table-details' (columns, joins, usage for "
          "named tables). Read-only.", {"kind": str, "query": str})
    async def snowflake_search(args):
        text, err = await asyncio.to_thread(codetools.snowflake_search, args.get("kind", ""),
                                            args.get("query", ""), connection)
        return _text(text, error=err)

    @tool("capture", "Draft a proposed canon standard from something learned in this session "
          "(a gotcha, a decision, a pattern). Writes a draft for review; never edits the canon.", {
              "type": "object",
              "properties": {"title": {"type": "string"}, "body": {"type": "string"},
                             "applies_to": {"type": "array", "items": {"type": "string"}}},
              "required": ["title", "body"]})
    async def capture(args):
        title = " ".join(str(args["title"]).split())          # front matter is one line per key
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50].strip("-") or "capture"
        base = (reconcile.find_repo(cwd) or cwd).resolve()
        folder = base / ".ds" / "captures"
        if (base / ".ds").is_symlink() or folder.is_symlink():
            return _text(f"not written: {base / '.ds'} or its captures folder is a symbolic link", error=True)
        folder.mkdir(parents=True, exist_ok=True)
        if base not in folder.resolve().parents:
            return _text(f"not written: {folder} resolves outside {base}", error=True)
        applies = json.dumps(args.get("applies_to") or ["*"])
        for n in range(1, 100):                # never overwrite an earlier draft, or follow a link
            sid = slug if n == 1 else f"{slug}-{n}"     # the canon id matches the file, so both can publish
            path = folder / f"{sid}.md"
            text = (f"---\nid: {sid}\nversion: 1\ntitle: {title}\napplies_to: {applies}\n"
                    f"owner: {scaffold._git_user()}\nstatus: proposed\ndate: {dt.date.today()}\n---\n\n"
                    f"# {title}\n\n{str(args['body']).strip()}\n")
            try:
                with open(path, "x") as f:  # noqa: ASYNC230 - one small file; "x" refuses to overwrite
                    f.write(text)
                break
            except FileExistsError:
                continue
        else:
            return _text(f"not written: 99 drafts already named {slug}", error=True)
        return _text(f"draft at {path}. To publish: open a canon merge request with this file "
                     f"(the so-capture skill does it), then run scripts/build_index.py.")

    return [canon_list, canon_read, skills_list, skill_read, project_status, scaffold_list, scaffold_get,
            scaffold_project, adopt_repo, block_list, block_get, block_add, code_search, code_get, code_add,
            snowflake_search, capture]


def code_tools(cwd: Path) -> str:
    """The prompt lines for the code tools, when ds-code is installed, and Snowflake search."""
    lines = []
    if codetools.code_bin():
        lines.append("- Use the `code` tools before text search: repo_overview to learn a repo, file_symbols before "
                     "reading a file, find_symbol and definition for where something is defined, references and "
                     "callers before changing or removing anything, change_impact before finishing a change. "
                     "Reuse what they find instead of rewriting it.")
    lines.append("- For Snowflake questions (docs, tables, columns), use snowflake_search before guessing.")
    return "\n".join(lines)


def system_prompt(cwd: Path, canon: Canon, skills: Skills) -> str:
    repo = reconcile.find_repo(cwd)
    where = (f"The working directory is inside the ds repo {repo.name}." if repo
             else "The working directory is not a ds repo yet.")
    return f"""You are ds, the front door to the team's knowledge system, running in a terminal.

The knowledge system has three parts, all readable through your `ds` tools:
- the canon: {len(canon.standards)} versioned standards, the only place team rules are written,
  and {len(canon.scaffolds)} project scaffolds ({", ".join(canon.scaffolds)}), the only accepted project shapes,
  and {len(canon.blocks)} blocks of accepted, tested code;
- skills-os: {len(skills.all)} procedures (SKILL.md files) for how the team works;
- docs-ds: the site that renders both (the user runs /docs; you do not).

Rules:
- Cite standards as [[id]] pointers and read them with canon_read before relying on them.
  Never paste a standard's text into a repo file.
- New projects come from accepted canon scaffolds. The /new form sends you a complete draft:
  check it against the canon (canon_list with its tags; canon_read only a standard the answers
  actually touch). If something is wrong or too vague to be useful, say so in at most three
  short bullets and ask once. Never replace an answer with one you made up: a purpose, name or
  schema you invent is not a suggestion. Offer a concrete value only when it follows from what
  the user gave (a name fixed to lowercase-with-dashes, a decline that names a real standard).
  Otherwise, or once the user answers, call scaffold_get for the draft's scaffold and then
  scaffold_project with its version, passing the user's values unchanged unless they agreed to
  a change. Do not re-ask what the draft already answers.
- An existing repository joins the system with adopt_repo, never by writing its manifest or
  AGENTS.md yourself. Call it with no overrides, show what it detected, and let the user correct it.
- If the user asks for a project in chat instead, propose a complete draft in one message
  (scaffold, name, purpose, and suggested values for the rest), ask for one confirmation, and
  create it the same way. Never ask one question at a time. Never write project files yourself.
- Before writing code, code_search for accepted code that already does it (one function at a
  time), code_get to read it, and code_add it rather than writing your own; import it from the
  package. block_add takes a whole block when you need most of it. Before building anything, read the gotchas
  (canon_list marks them) whose tags match the work: they are mistakes already made here once.
- When a skill fits the request, skill_read it and follow it.
{code_tools(cwd)}
- When the session uncovers something the team should remember, offer to capture it.
- Be brief. This is a terminal.

{where} Today is {dt.date.today()}."""


class TurnStalled(TimeoutError):
    """Cortex sent nothing for longer than the idle timeout; the turn was interrupted."""


PermissionAsk = Callable[[str, dict[str, Any], Any], Awaitable[Any]]
_HOOKS_ALLOWED: set[str] = set()   # repo hooks the person let Cortex run, for as long as ds-next runs


class Agent:
    """One Cortex Code session. Connects on the first turn; `reset` starts a new session."""

    def __init__(self, cwd: Path, ask_permission: PermissionAsk | None = None,
                 model: str | None = None, connection: str | None = None, effort: str | None = "low",
                 canon: Canon | None = None, skills: Skills | None = None):
        self.cwd = Path(cwd).resolve()
        self.canon = canon or Canon()
        self.skills = skills or Skills()
        self.ask_permission = ask_permission
        self.model = model
        self.connection = connection
        self.effort = effort      # low keeps the interview quick; /effort or --effort raises it
        self.session_id: str | None = None
        self._resume: str | None = None
        self.idle_timeout: float | None = 600      # long tool runs are silent too; approvals pause it
        self._asking = False
        self._last = 0.0
        self._client: sdk.SDKClient | None = None

    def options(self):
        server = create_sdk_mcp_server(SERVER, tools=tools(self.canon, self.skills, self.cwd, self.connection))
        code = codetools.mcp_servers(self.cwd)
        self._read_only = READ_ONLY_IDS | codetools.read_only_ids(code)
        return sdk.options(cwd=str(self.cwd), mcp_servers={SERVER: server, **code},
                           append_system_prompt=system_prompt(self.cwd, self.canon, self.skills),
                           can_use_tool=self._permit, model=self.model, connection=self.connection,
                           effort=self.effort, resume=self._resume, read_only=self._read_only)

    async def _permit(self, tool_name: str, inp: dict[str, Any], ctx: Any):
        """Reading the knowledge base never needs a human; everything else asks. Cortex names the
        tool inside a resource string, Claude Code by its id (sdk.tool_id reads both)."""
        if sdk.tool_id(tool_name, inp) in getattr(self, "_read_only", READ_ONLY_IDS):
            return PermissionResultAllow()
        if self.ask_permission is None:
            return PermissionResultDeny(message="No one is here to approve this call.")
        self._asking = True                         # the stall watchdog waits while a person decides
        try:
            return await self.ask_permission(tool_name, inp, ctx)
        finally:
            self._asking = False

    @property
    def connected(self) -> bool:
        return self._client is not None

    async def _ask_about_hooks(self) -> None:
        """Cortex Code runs a repo's own hooks (its .cortex or .claude settings), and its SDK has no way
        to switch them off, so the person sees each command and decides before a session starts in
        that repo. A no starts nothing; a yes lasts while ds-next runs, until the hooks change."""
        found = sdk.project_hooks(self.cwd)
        key = json.dumps(found)    # the files' whole text: any change to them asks again
        if not found or key in _HOOKS_ALLOWED:
            return
        command = "\n".join(line for file, runs, _ in found for line in (f"# {file}", *runs))
        detail = {"command": command, "description": "Cortex Code runs these from this repo's settings as you work, without asking"}
        answer = await self.ask_permission("Hooks", detail, None) if self.ask_permission else None
        if not isinstance(answer, PermissionResultAllow):
            raise sdk.SDKError(f"Cortex Code not started: this repo's settings define hooks it would run "
                               f"({', '.join(f for f, _, _ in found)}). Remove them, or run with DS_AGENT=claude, which runs no hooks.")
        _HOOKS_ALLOWED.add(key)

    async def connect(self) -> None:
        """Start the agent."""
        if self._client is None:
            if sdk.BACKEND == "cortex":
                await self._ask_about_hooks()
            client = sdk.SDKClient(self.options())
            # The SDK's connection lives in an anyio task group that must be entered and exited in
            # the same task, so connect() runs here, never inside gather() or a new task.
            # [[gotcha-cortex-sdk]]
            await client.connect()
            self._client = client

    async def turn(self, prompt: str) -> AsyncIterator[Message]:
        """Messages until the turn's result. A watchdog interrupts a stream silent for longer than
        idle_timeout, except while a person is answering an approval, and raises TurnStalled;
        the next turn resumes the same session. [[gotcha-cortex-sdk]] v3"""
        await self.connect()
        assert self._client is not None
        loop = asyncio.get_running_loop()
        me = asyncio.current_task()
        self._last = loop.time()
        stalled = False
        limit = self.idle_timeout

        async def watchdog() -> None:
            nonlocal stalled
            while True:
                await asyncio.sleep(min(limit / 4, 5))
                if self._asking:
                    self._last = loop.time()
                elif loop.time() - self._last > limit:
                    stalled = True
                    me.cancel()
                    return

        dog = asyncio.ensure_future(watchdog()) if limit else None
        try:
            await self._client.query(prompt)
            async for msg in self._client.receive_response():
                self._last = loop.time()
                sid = getattr(msg, "session_id", None)
                if sid:
                    self.session_id = sid
                yield msg
        except asyncio.CancelledError:
            if not stalled:
                raise
            me.uncancel()
            await self.interrupt()
            resume = self.session_id
            await self.close()
            self._resume = resume
            raise TurnStalled(f"{sdk.LABEL} sent nothing for {limit:.0f}s, so the turn was interrupted. "
                              "Ask again to continue the same session.") from None
        finally:
            if dog is not None:
                dog.cancel()

    async def set_effort(self, effort: str | None) -> None:
        """Effort is fixed when Cortex starts, so reconnect and resume the same conversation."""
        self.effort = effort
        if self._client is not None:
            resume = self.session_id
            await self.close()
            self._resume = resume

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
        self._resume = None            # a fresh session must not resume the old one
