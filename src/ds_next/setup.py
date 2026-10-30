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
(`ds-next` or `ds-code`, wherever installed; a `code` or `ds` that runs something else is left alone
and named), a skill link comes off when it points into ds-next's skills or skills-os, even dangling,
and the rules of both servers are dropped. ~/.ds/config.toml stays: canon's uninstall.sh asks about
it, with the repositories.
"""
from __future__ import annotations

import copy
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
_SRC_SKILLS = Path(__file__).resolve().parents[2] / "skills"      # a source checkout's skills folder


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
    return _SRC_SKILLS if (_SRC_SKILLS / SKILLS[0] / "SKILL.md").is_file() else None


def skill_dirs() -> list[Path]:
    """Every skill the agents get: ours, then skills-os's /so-* procedures when that checkout is found.
    Absolute paths, so a relative DS_SKILLS never becomes a relative, broken link."""
    from . import kb
    out = []
    if skills_dir() is not None:
        out += [(_SRC_SKILLS / name).resolve() for name in SKILLS]
    s = kb.skills_path()
    if s is not None:
        out += sorted(p.resolve() for p in s.glob("so-*") if (p / "SKILL.md").is_file())
    return out


def skill_roots() -> set[Path]:
    """Where our skills can live, in every spelling a link may carry: ds-next/skills and skills-os in each
    place kb looks (and DS_SKILLS). A link into any of these is ours, even when the checkout is gone."""
    from . import kb
    roots = [_SRC_SKILLS] + [base / "skills-os" for base in kb.bases()]
    if s := kb.skills_path():
        roots.append(s)
    out = set()
    for r in roots:
        out.add(_norm(r))
        try:
            out.add(_norm(r.resolve()))
        except OSError:
            pass
    return out


# --- the servers ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class Server:
    """One of the system's two servers: what it is called, which command runs it, which tools only read."""
    name: str
    command: str                   # the command's basename: how a registration is recognised as ours
    read_only: tuple[str, ...]

    @property
    def rules(self) -> list[str]:
        return [f"mcp__{self.name}__{t}" for t in self.read_only]

    def argv(self) -> tuple[str, ...] | None:
        """How this machine starts it, or None when it is not installed here."""
        from .codetools import code_command
        if self.command == "ds-next":
            return (str(ds_next_bin()), "mcp")
        c = code_command()
        return (*c, "mcp") if c else None


def servers() -> tuple[Server, Server]:
    from .agent import READ_ONLY, SERVER
    from .codetools import CODE, CODE_TOOLS
    return Server(SERVER, "ds-next", READ_ONLY), Server(CODE, "ds-code", CODE_TOOLS)


def all_rules() -> list[str]:
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
    out = copy.deepcopy(settings)
    allow = _allow_list(out, create=True)
    added = [r for r in rules if r not in allow]
    allow.extend(added)
    return out, added


def drop_allow(settings: dict, rules: list[str]) -> tuple[dict, list[str]]:
    """Take the rules out of permissions.allow. Returns the new settings and what was removed."""
    out = copy.deepcopy(settings)
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
    """How one agent CLI is driven: `<bin> mcp add|remove <scope> <name> <sep> <command...>`. `skills` is
    the folder our symlinks go in, or None for Cortex, which keeps its own list (`cortex skill add/remove`)."""
    name: str
    scope: tuple[str, ...]
    sep: tuple[str, ...]
    settings: Callable[[], Path] | None
    skills: Callable[[], Path] | None


CLIS = {
    "claude": Cli("claude", ("--scope", "user"), ("--",), lambda: claude_home() / "settings.json", lambda: claude_home() / "skills"),
    "cortex": Cli("cortex", (), (), lambda: cortex_home() / "settings.json", None),
    "codex": Cli("codex", (), ("--",), None, lambda: codex_home() / "skills"),
}


def _registered(bin: str, s: Server) -> str:
    """What `mcp get` says about the server: 'ok' (this machine's command), 'ours' (our command from
    somewhere else, say an older install), 'other' (something else entirely) or 'no'."""
    code, text = _run([bin, "mcp", "get", s.name])
    if code != 0:
        return "no"
    argv = s.argv()
    if argv and all(part in text for part in argv):
        return "ok"
    return "ours" if re.search(rf"\b{re.escape(s.command)}(\.cmd|\.exe)?\b", text) else "other"


def _server(cli: Cli, bin: str, s: Server, check: bool, say) -> bool:
    """Register one installed server (its argv is known), replacing a registration that runs anything else."""
    argv = s.argv() or ()
    state = _registered(bin, s)
    cmd = " ".join(argv)
    if state == "ok":
        say(f"mcp server {s.name}: registered ({cmd})")
        return True
    if state != "no":
        say(f"mcp server {s.name}: registered with a different command; " + ("would replace" if check else "replacing"))
        if not check:
            _run([bin, "mcp", "remove", *cli.scope, s.name])
    if check:
        say(f"mcp server {s.name}: would register {cmd}")
        return True
    code, text = _run([bin, "mcp", "add", *cli.scope, s.name, *cli.sep, *argv])
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
    code, text = _run([bin, "mcp", "remove", *cli.scope, s.name])
    say(f"mcp server {s.name}: {'unregistered' if code == 0 else 'FAILED: ' + text.strip()}")
    return code == 0


def _norm(p: Path) -> Path:
    """A path as it compares (case folded on Windows)."""
    return Path(os.path.normcase(str(p)))


def _ours(path: Path, roots: set[Path]) -> bool:
    """Does a skill path (a link's target, or a listed directory) lie under one of our roots? Compared
    as written and resolved, so a dangling link to a deleted checkout still counts."""
    candidates = {_norm(path)}
    try:
        candidates.add(_norm(path.resolve()))
    except OSError:
        pass
    return any(c == r or r in c.parents for c in candidates for r in roots)


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
    if cli.skills is None:
        ok = True
        _, listed = _run([bin, "skill", "list"])
        for line in listed.splitlines():
            p = Path(line.strip().lstrip("-").strip()).expanduser()
            if not p.is_absolute() or not _ours(p, roots):
                continue
            if check:
                say(f"skill /{p.name}: would remove {p}")
            else:
                code, text = _run([bin, "skill", "remove", str(p)])
                say(f"skill /{p.name}: {'removed' if code == 0 else 'FAILED: ' + text.strip()}")
                ok = ok and code == 0
        return ok
    folder = cli.skills()
    if not folder.is_dir():
        return True
    for link in sorted(folder.iterdir()):
        if not link.is_symlink():
            continue
        raw = Path(os.readlink(link).removeprefix("\\\\?\\"))      # Windows readlink carries the \\?\ prefix
        if not _ours(raw if raw.is_absolute() else link.parent / raw, roots):
            continue
        if check:
            say(f"skill /{link.name}: would unlink {link}")
        else:
            link.unlink()
            say(f"skill /{link.name}: unlinked ({link})")
    return True


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
    from .agent import WRITES
    bin = shutil.which(cli.name)
    if not bin:
        say(f"{cli.name}: not on PATH; skipped (install it, then rerun ds-next setup)")
        return False
    if not ds_next_bin().is_file():
        say(f"ds-next: {ds_next_bin()} not found; cannot register the server")
        return False
    installed = [s for s in servers() if s.argv() is not None]
    for s in servers():
        if s not in installed:
            say(f"mcp server {s.name}: {s.command} is not on PATH; it comes when that is installed and this is rerun")
    registered = [s for s in installed if _server(cli, bin, s, check, say)]
    ok = len(registered) == len(installed)
    ok = _links(cli, bin, skill_dirs(), check, say) and ok
    if cli.settings is not None:          # only the servers that are ours and registered get their tools pre-approved
        ok = _allow(cli.settings(), [r for s in registered for r in s.rules], check, say) and ok
    say(f"write tools ({', '.join(WRITES)}) still ask: that is the control point")
    return ok


def _disconnect(cli: Cli, check: bool, say) -> bool:
    bin = shutil.which(cli.name)
    if not bin:
        say(f"{cli.name}: not on PATH; nothing to undo")
        return True
    ok = True
    for s in servers():
        ok = _unserver(cli, bin, s, check, say) and ok
    ok = _unlinks(cli, bin, check, say) and ok
    if cli.settings is not None:
        ok = _disallow(cli.settings(), all_rules(), check, say) and ok
    return ok


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
