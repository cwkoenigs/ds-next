"""`ds-next setup`: connect this machine's agents to the knowledge system, idempotently; `--remove`
disconnects them again.

For Claude Code, Cortex Code and Codex alike: register the `ds` MCP server (and `code`, ds-code's,
when `ds-code` is on PATH), and add the skills: /ds-new and /ds-terminal-design from this checkout,
and every /so-* procedure from skills-os when that checkout is found. Claude Code and Cortex Code
also allow the read-only tools of the servers that registered, so reading the canon or the code never
prompts (Codex has no such list). The five write tools keep prompting: that approval is the control
point. `--agent claude` (or cortex, or codex) also records the choice in ~/.ds/config.toml, which is
what the terminal then runs its turns through. Every step reports what it found and what it changed;
--check changes nothing.

`--remove` is the exact reverse, and only of ours: a server is unregistered when it runs our command
(a `code` or `ds` that runs something else is left alone and named), a skill link comes off when it
points into ds-next's skills or skills-os, even dangling, and the rules of both servers are dropped.
~/.ds/config.toml stays: canon's uninstall.sh asks about it, with the repositories.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

SKILLS = ("ds-new", "ds-terminal-design")
WRITES_NOTE = "write tools (scaffold_project, adopt_repo, block_add, code_add, capture) still ask: that is the control point"


def cortex_home() -> Path:
    return Path.home() / ".snowflake" / "cortex"


def claude_home() -> Path:
    return Path.home() / ".claude"


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def config_path() -> Path:
    return Path.home() / ".ds" / "config.toml"


def set_default_agent(name: str) -> Path:
    """Record which agent the terminal runs its turns through (sdk.py reads it). Only the top-level
    `agent` line changes: every other key, table and comment in the file stays, so the machine's
    `[world]` and `[capture]` (written by canon's install.sh, read by so-capture) survive a setup.
    A file that is not TOML is kept beside it as config.toml.bak and started fresh."""
    import tomllib
    path = config_path()
    text = path.read_text() if path.is_file() else ""
    try:
        tomllib.loads(text)
    except ValueError:
        path.with_name("config.toml.bak").write_text(text)
        text = ""
    line = f"agent = {json.dumps(name)}"
    lines = text.splitlines()
    top = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("[")), len(lines))
    at = next((i for i in range(top) if re.match(r"\s*agent\s*=", lines[i])), None)
    if at is not None:
        lines[at] = line
    else:                                   # after the last top-level key, before the first table
        pos = top
        while pos > 0 and not lines[pos - 1].strip():
            pos -= 1
        lines[pos:pos] = [line] + ([""] if pos == top < len(lines) else [])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def ds_next_bin() -> Path:
    """The ds-next console script next to this interpreter (the venv or uv tool install)."""
    return Path(sys.executable).with_name("ds-next")


def skills_dir() -> Path | None:
    """The skills shipped with a source checkout (ds-next/skills). None when installed from a wheel."""
    d = Path(__file__).resolve().parents[2] / "skills"
    return d if (d / SKILLS[0] / "SKILL.md").is_file() else None


def skill_roots() -> list[Path]:
    """Where our skills live: ds-next/skills and the skills-os checkout, absolute. A link into either is
    ours, which is what remove goes by, even when the checkout itself is gone."""
    from . import kb
    roots = []
    d = skills_dir()
    roots.append(d.resolve() if d else Path(__file__).resolve().parents[2] / "skills")
    s = kb.skills_path()
    roots.append(s.resolve() if s else Path.home() / "Developer" / "skills-os")
    return roots


def skill_dirs() -> list[Path]:
    """Every skill the agents get: ours, then skills-os's /so-* procedures when that checkout is found.
    Absolute paths, so a relative DS_SKILLS never becomes a relative, broken link."""
    from . import kb
    out = []
    d = skills_dir()
    if d is not None:
        out += [(d / name).resolve() for name in SKILLS]
    s = kb.skills_path()
    if s is not None:
        out += sorted(p.resolve() for p in s.glob("so-*") if (p / "SKILL.md").is_file())
    return out


# --- the servers ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class Server:
    name: str
    argv: tuple[str, ...]          # the command and its arguments, as the agent will start it
    read_only: tuple[str, ...]     # the tools that never need to ask

    @property
    def rules(self) -> list[str]:
        return [f"mcp__{self.name}__{t}" for t in self.read_only]


def servers() -> list[Server]:
    """`ds` always; `code` when ds-code is installed (npm puts `ds-code` on PATH)."""
    from .agent import READ_ONLY, SERVER
    from .codetools import CODE, CODE_TOOLS, code_command
    out = [Server(SERVER, (str(ds_next_bin()), "mcp"), READ_ONLY)]
    c = code_command()
    if c is not None:
        out.append(Server(CODE, (*c, "mcp"), CODE_TOOLS))
    return out


def removable() -> list[Server]:
    """What remove looks for: the servers above, plus `code` by its command name when ds-code is no
    longer installed, so a registration left behind still comes off."""
    from .codetools import CODE, CODE_TOOLS
    out = servers()
    if all(s.name != CODE for s in out):
        out.append(Server(CODE, ("ds-code",), CODE_TOOLS))
    return out


def all_rules() -> list[str]:
    """Every allow rule a setup may ever have written, whether or not ds-code is on PATH now."""
    from .agent import READ_ONLY, SERVER
    from .codetools import CODE, CODE_TOOLS
    return [f"mcp__{SERVER}__{t}" for t in READ_ONLY] + [f"mcp__{CODE}__{t}" for t in CODE_TOOLS]


def read_only_rules() -> list[str]:
    return [r for s in servers() for r in s.rules]


def _allow_list(settings: dict, create: bool) -> list | None:
    """permissions.allow when it is a list. With `create`, a missing or malformed one is replaced."""
    perms = settings.get("permissions")
    if not isinstance(perms, dict):
        if not create:
            return None
        perms = settings["permissions"] = {}
    allow = perms.get("allow")
    if not isinstance(allow, list):
        if not create:
            return None
        allow = perms["allow"] = []
    return allow


def merge_allow(settings: dict, rules: list[str]) -> tuple[dict, list[str]]:
    """Add the rules missing from permissions.allow. Returns the new settings and what was added."""
    out = json.loads(json.dumps(settings))
    allow = _allow_list(out, create=True)
    added = [r for r in rules if r not in allow]
    allow.extend(added)
    return out, added


def drop_allow(settings: dict, rules: list[str]) -> tuple[dict, list[str]]:
    """Take the rules out of permissions.allow. Returns the new settings and what was removed."""
    out = json.loads(json.dumps(settings))
    allow = _allow_list(out, create=False)
    if allow is None:
        return out, []
    removed = [r for r in allow if r in rules]
    allow[:] = [r for r in allow if r not in rules]
    return out, removed


def _run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(args, check=False, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)


# --- the agents ----------------------------------------------------------------------------------

@dataclass(frozen=True)
class Cli:
    """How one agent CLI is driven. `skills` is the folder our symlinks go in, or None for Cortex,
    which keeps its own list (`cortex skill add/remove`)."""
    name: str
    mcp_add: tuple[str, ...]           # after the binary, before the server name
    mcp_sep: tuple[str, ...]           # between the server name and the command
    mcp_remove: tuple[str, ...]
    settings: Callable[[], Path] | None
    skills: Callable[[], Path] | None


CLIS = {
    "claude": Cli("claude", ("mcp", "add", "--scope", "user"), ("--",), ("mcp", "remove", "--scope", "user"),
                  lambda: claude_home() / "settings.json", lambda: claude_home() / "skills"),
    "cortex": Cli("cortex", ("mcp", "add"), (), ("mcp", "remove"),
                  lambda: cortex_home() / "settings.json", None),
    "codex": Cli("codex", ("mcp", "add"), ("--",), ("mcp", "remove"),
                 None, lambda: codex_home() / "skills"),
}


def _registered(bin: str, s: Server) -> str:
    """'ok' (this command), 'other' (some other command) or 'no'."""
    code, text = _run([bin, "mcp", "get", s.name])
    if code != 0:
        return "no"
    return "ok" if all(part in text for part in s.argv) else "other"


def _server(cli: Cli, bin: str, s: Server, check: bool, say) -> bool:
    state = _registered(bin, s)
    cmd = " ".join(s.argv)
    if state == "ok":
        say(f"mcp server {s.name}: registered ({cmd})")
        return True
    if state == "other":
        say(f"mcp server {s.name}: registered with a different command; " + ("would replace" if check else "replacing"))
        if not check:
            _run([bin, *cli.mcp_remove, s.name])
    if check:
        say(f"mcp server {s.name}: would register {cmd}")
        return True
    code, text = _run([bin, *cli.mcp_add, s.name, *cli.mcp_sep, *s.argv])
    say(f"mcp server {s.name}: {'registered' if code == 0 else 'FAILED: ' + text.strip()}")
    return code == 0


def _unserver(cli: Cli, bin: str, s: Server, check: bool, say) -> bool:
    state = _registered(bin, s)
    if state == "no":
        say(f"mcp server {s.name}: not registered")
        return True
    if state == "other":
        say(f"mcp server {s.name}: registered, but it runs something else; not ours, left alone")
        return True
    if check:
        say(f"mcp server {s.name}: would unregister")
        return True
    code, text = _run([bin, *cli.mcp_remove, s.name])
    say(f"mcp server {s.name}: {'unregistered' if code == 0 else 'FAILED: ' + text.strip()}")
    return code == 0


def _norm(p: Path) -> Path:
    """A path as it compares: Windows' `\\\\?\\` prefix (what readlink returns there) dropped, case folded."""
    s = str(p)
    s = s.removeprefix("\\\\?\\")
    return Path(os.path.normcase(s))


def _ours(path: Path, roots: list[Path]) -> bool:
    """Does a skill path (a link's raw target, or a listed directory) lie under one of our roots?
    Compared as written and resolved, so a dangling link to a deleted checkout still counts."""
    candidates = {_norm(path)}
    try:
        candidates.add(_norm(path.resolve()))
    except OSError:
        pass
    for root in roots:
        forms = {_norm(root)}
        try:
            forms.add(_norm(root.resolve()))
        except OSError:
            pass
        for c in candidates:
            for r in forms:
                if c == r or r in c.parents:
                    return True
    return False


def _links(cli: Cli, bin: str, dirs: list[Path], check: bool, say) -> bool:
    """The skills reach the agent: symlinks in its skills folder, or Cortex's own list."""
    if not dirs:
        say("skills: none found (a source checkout of ds-next, and skills-os beside it, ship them); skipped")
        return True
    ok = True
    if cli.skills is None:                      # cortex keeps its own list of skill directories
        _, listed = _run([bin, "skill", "list"])
        for path in dirs:
            if str(path) in listed:
                say(f"skill /{path.name}: added ({path})")
            elif check:
                say(f"skill /{path.name}: would add {path}")
            else:
                code, text = _run([bin, "skill", "add", str(path)])
                say(f"skill /{path.name}: {'added' if code == 0 else 'FAILED: ' + text.strip()}")
                ok = ok and code == 0
        return ok
    folder = cli.skills()
    for target in dirs:
        link = folder / target.name
        if link.is_symlink() and link.resolve() == target.resolve():
            say(f"skill /{target.name}: linked ({link})")
        elif link.exists() or link.is_symlink():
            say(f"skill /{target.name}: {link} exists and is not ours; left alone")
            ok = False
        elif check:
            say(f"skill /{target.name}: would link {link} -> {target}")
        else:
            folder.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target)
            say(f"skill /{target.name}: linked ({link})")
    return ok


def _unlinks(cli: Cli, bin: str, check: bool, say) -> bool:
    """Every skill of ours comes off: whatever points into our roots, present or dangling."""
    roots = skill_roots()
    ok = True
    if cli.skills is None:
        _, listed = _run([bin, "skill", "list"])
        for line in listed.splitlines():
            path = line.strip().lstrip("-").strip()
            if not path or not Path(path).expanduser().is_absolute() or not _ours(Path(path).expanduser(), roots):
                continue
            if check:
                say(f"skill /{Path(path).name}: would remove {path}")
            else:
                code, text = _run([bin, "skill", "remove", path])
                say(f"skill /{Path(path).name}: {'removed' if code == 0 else 'FAILED: ' + text.strip()}")
                ok = ok and code == 0
        return ok
    folder = cli.skills()
    if not folder.is_dir():
        return ok
    for link in sorted(folder.iterdir()):
        if not link.is_symlink():
            continue
        raw = Path(os.readlink(link))
        target = raw if raw.is_absolute() else link.parent / raw
        if not _ours(target, roots):
            continue
        if check:
            say(f"skill /{link.name}: would unlink {link}")
        else:
            link.unlink()
            say(f"skill /{link.name}: unlinked ({link})")
    return ok


def _settings(path: Path, say) -> dict | None:
    try:
        settings = json.loads(path.read_text()) if path.is_file() else {}
    except ValueError as e:
        say(f"permissions: {path} is not valid JSON ({e}); not touched")
        return None
    if not isinstance(settings, dict):
        say(f"permissions: {path} is not a JSON object; not touched")
        return None
    return settings


def _write_settings(path: Path, settings: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        shutil.copy2(path, path.with_suffix(".json.bak"))
    path.write_text(json.dumps(settings, indent=2) + "\n")


def _allow(settings_path: Path, rules: list[str], check: bool, say) -> bool:
    """permissions.allow in an agent's settings.json gains the read-only tools."""
    settings = _settings(settings_path, say)
    if settings is None:
        return False
    new, added = merge_allow(settings, rules)
    if not added:
        say(f"permissions: {len(rules)} read-only tools already allowed")
    elif check:
        say(f"permissions: would allow {len(added)} read-only tools in {settings_path}")
    else:
        _write_settings(settings_path, new)
        say(f"permissions: allowed {len(added)} read-only tools in {settings_path} (backup .json.bak)")
    return True


def _disallow(settings_path: Path, rules: list[str], check: bool, say) -> bool:
    settings = _settings(settings_path, say)
    if settings is None:
        return False
    new, removed = drop_allow(settings, rules)
    if not removed:
        say("permissions: no read-only rules of ours to drop")
    elif check:
        say(f"permissions: would drop {len(removed)} read-only rules from {settings_path}")
    else:
        _write_settings(settings_path, new)
        say(f"permissions: dropped {len(removed)} read-only rules from {settings_path} (backup .json.bak)")
    return True


def _connect(cli: Cli, check: bool, say) -> bool:
    bin = shutil.which(cli.name)
    if not bin:
        say(f"{cli.name}: not on PATH; skipped (install it, then rerun ds-next setup)")
        return False
    if not ds_next_bin().is_file():
        say(f"ds-next: {ds_next_bin()} not found; cannot register the server")
        return False
    ok = True
    registered: list[Server] = []
    for s in servers():
        if _server(cli, bin, s, check, say):
            registered.append(s)
        else:
            ok = False
    if shutil.which("ds-code") is None:
        say("mcp server code: ds-code is not on PATH; the code tools come when it is installed and this is rerun")
    ok = _links(cli, bin, skill_dirs(), check, say) and ok
    if cli.settings is not None:          # only the servers that are ours and registered get their tools pre-approved
        ok = _allow(cli.settings(), [r for s in registered for r in s.rules], check, say) and ok
    say(WRITES_NOTE)
    return ok


def _disconnect(cli: Cli, check: bool, say) -> bool:
    bin = shutil.which(cli.name)
    if not bin:
        say(f"{cli.name}: not on PATH; nothing to undo")
        return True
    ok = True
    for s in removable():
        ok = _unserver(cli, bin, s, check, say) and ok
    ok = _unlinks(cli, bin, check, say) and ok
    if cli.settings is not None:
        ok = _disallow(cli.settings(), all_rules(), check, say) and ok
    return ok


def setup_claude(check: bool, say) -> bool:
    """Claude Code: the servers at user scope, the skills linked into ~/.claude/skills, the read-only
    tools allowed in ~/.claude/settings.json. Returns True when fully set up."""
    return _connect(CLIS["claude"], check, say)


def setup_cortex(check: bool, say) -> bool:
    """Cortex Code: the servers, the skills in its own list, the read-only tools allowed."""
    return _connect(CLIS["cortex"], check, say)


def setup_codex(check: bool, say) -> bool:
    """Codex: the servers in its config, the skills linked into its skills folder. It has no list of
    tools that never ask; in ds-next's terminal, ds-next answers Codex's approvals itself."""
    return _connect(CLIS["codex"], check, say)


def _each(agent: str, step: Callable[[Cli, bool, Callable], bool], check: bool, say, none: str) -> bool:
    if agent != "auto":
        return step(CLIS[agent], check, say)
    found = [a for a in CLIS if shutil.which(a)]
    if not found:
        say(none)
        return False
    ok = True
    for a in found:
        say(f"{a}:")
        ok = step(CLIS[a], check, say) and ok
    return ok


def setup(agent: str, check: bool, say) -> bool:
    """`auto`: every agent CLI on PATH. A named agent is set up and, unless --check, recorded as
    the terminal's."""
    if agent != "auto" and not check:
        say(f"terminal agent: {agent} (recorded in {set_default_agent(agent)})")
    return _each(agent, _connect, check, say,
                 "no agent on PATH: install Claude Code, Cortex Code or Codex, then rerun ds-next setup")


def remove(agent: str, check: bool, say) -> bool:
    """Undo setup for `auto` (every agent CLI on PATH) or one agent. The config file stays."""
    ok = _each(agent, _disconnect, check, say, "no agent on PATH: nothing to undo")
    say(f"{config_path()}: kept (canon's uninstall.sh asks about it)")
    return ok
