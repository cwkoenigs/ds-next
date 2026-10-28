"""`ds-next setup`: connect this machine's agents to the knowledge system, idempotently.

For Claude Code, Cortex Code and Codex alike: register the `ds` MCP server and add the /ds-new and
/ds-terminal-design skills. Claude Code and Cortex Code also allow the read-only ds tools, so reading
the canon never prompts (Codex has no such list). The five write tools keep prompting: that approval
is the control point. `--agent claude` (or cortex, or codex) also records the choice in
~/.ds/config.toml, which is what the terminal then runs its turns through. Every step reports what it
found and what it changed; --check changes nothing.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILLS = ("ds-new", "ds-terminal-design")


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


def read_only_rules() -> list[str]:
    from .agent import READ_ONLY, SERVER
    return [f"mcp__{SERVER}__{t}" for t in READ_ONLY]


def merge_allow(settings: dict, rules: list[str]) -> tuple[dict, list[str]]:
    """Add the rules missing from permissions.allow. Returns the new settings and what was added."""
    out = json.loads(json.dumps(settings))
    allow = out.setdefault("permissions", {}).setdefault("allow", [])
    added = [r for r in rules if r not in allow]
    allow.extend(added)
    return out, added


def _run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(args, check=False, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)


def _allow(settings_path: Path, check: bool, say) -> bool:
    """permissions.allow in an agent's settings.json gains the read-only ds tools."""
    try:
        settings = json.loads(settings_path.read_text()) if settings_path.is_file() else {}
    except ValueError as e:
        say(f"permissions: {settings_path} is not valid JSON ({e}); not touched")
        return False
    new, added = merge_allow(settings, read_only_rules())
    if not added:
        say(f"permissions: {len(read_only_rules())} read-only ds tools already allowed")
    elif check:
        say(f"permissions: would allow {len(added)} read-only ds tools in {settings_path}")
    else:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        if settings_path.is_file():
            shutil.copy2(settings_path, settings_path.with_suffix(".json.bak"))
        settings_path.write_text(json.dumps(new, indent=2) + "\n")
        say(f"permissions: allowed {len(added)} read-only ds tools in {settings_path} (backup .json.bak)")
    return True


def setup_claude(check: bool, say) -> bool:
    """Claude Code: the server at user scope, the skills linked into ~/.claude/skills, the
    read-only tools allowed in ~/.claude/settings.json. Returns True when fully set up."""
    claude = shutil.which("claude")
    if not claude:
        say("claude: not on PATH; skipped (install Claude Code, then rerun ds-next setup)")
        return False
    binary = ds_next_bin()
    if not binary.is_file():
        say(f"ds-next: {binary} not found; cannot register the server")
        return False
    ok = True
    code, text = _run([claude, "mcp", "get", "ds"])
    if code == 0 and str(binary) in text and "mcp" in text:
        say(f"mcp server ds: registered in Claude Code ({binary} mcp)")
    else:
        if code == 0:
            say("mcp server ds: registered with a different command; " + ("would replace" if check else "replacing"))
            if not check:
                _run([claude, "mcp", "remove", "--scope", "user", "ds"])
        if check:
            say(f"mcp server ds: would register {binary} mcp (user scope)")
        else:
            code, text = _run([claude, "mcp", "add", "--scope", "user", "ds", "--", str(binary), "mcp"])
            say(f"mcp server ds: {'registered in Claude Code' if code == 0 else 'FAILED: ' + text.strip()}")
            ok = ok and code == 0
    sdir = skills_dir()
    if sdir is None:
        say("skills: not shipped with this install (source checkout only); skipped")
    else:
        for name in SKILLS:
            link, target = claude_home() / "skills" / name, sdir / name
            if link.is_symlink() and link.resolve() == target.resolve():
                say(f"skill /{name}: linked ({link})")
            elif link.exists() or link.is_symlink():
                say(f"skill /{name}: {link} exists and is not ours; left alone")
                ok = False
            elif check:
                say(f"skill /{name}: would link {link} -> {target}")
            else:
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(target)
                say(f"skill /{name}: linked ({link})")
    ok = _allow(claude_home() / "settings.json", check, say) and ok
    say("write tools (scaffold_project, adopt_repo, block_add, code_add, capture) still ask: that is the control point")
    return ok


def setup(agent: str, check: bool, say) -> bool:
    """`auto`: every agent CLI on PATH. A named agent is set up and, unless --check, recorded as
    the terminal's."""
    steps = {"claude": setup_claude, "cortex": setup_cortex, "codex": setup_codex}
    if agent == "auto":
        found = [a for a in steps if shutil.which(a)]
        if not found:
            say("no agent on PATH: install Claude Code, Cortex Code or Codex, then rerun ds-next setup")
            return False
        ok = True
        for a in found:
            say(f"{a}:")
            ok = steps[a](check, say) and ok
        return ok
    if not check:
        say(f"terminal agent: {agent} (recorded in {set_default_agent(agent)})")
    return steps[agent](check, say)


def setup_cortex(check: bool, say) -> bool:
    """Returns True when Cortex is now (or already was) fully set up."""
    cortex = shutil.which("cortex")
    if not cortex:
        say("cortex: not on PATH; skipped (install Cortex Code, then rerun ds-next setup)")
        return False
    ok = True
    binary = ds_next_bin()
    if not binary.is_file():
        say(f"ds-next: {binary} not found; cannot register the server")
        return False

    # 1. the MCP server
    code, text = _run([cortex, "mcp", "get", "ds"])
    if code == 0 and str(binary) in text and "mcp" in text:
        say(f"mcp server ds: registered ({binary} mcp)")
    else:
        if code == 0:
            say("mcp server ds: registered with a different command; replacing" if not check else
                "mcp server ds: registered with a different command; would replace")
            if not check:
                _run([cortex, "mcp", "remove", "ds"])
        if check:
            say(f"mcp server ds: would register {binary} mcp")
        else:
            code, text = _run([cortex, "mcp", "add", "ds", str(binary), "mcp"])
            say(f"mcp server ds: {'registered' if code == 0 else 'FAILED: ' + text.strip()}")
            ok = ok and code == 0

    # 2. the skills
    sdir = skills_dir()
    if sdir is None:
        say("skills: not shipped with this install (source checkout only); skipped")
    else:
        _, listed = _run([cortex, "skill", "list"])
        for name in SKILLS:
            path = sdir / name
            if str(path) in listed:
                say(f"skill /{name}: added ({path})")
            elif check:
                say(f"skill /{name}: would add {path}")
            else:
                code, text = _run([cortex, "skill", "add", str(path)])
                say(f"skill /{name}: {'added' if code == 0 else 'FAILED: ' + text.strip()}")
                ok = ok and code == 0

    # 3. read-only tools never prompt
    ok = _allow(cortex_home() / "settings.json", check, say) and ok
    say("write tools (scaffold_project, adopt_repo, block_add, code_add, capture) still ask: that is the control point")
    return ok


def setup_codex(check: bool, say) -> bool:
    """Codex: the server in its config, the skills linked into its skills folder. It has no list of
    tools that never ask; in ds-next's terminal, ds-next answers Codex's approvals itself."""
    codex = shutil.which("codex")
    if not codex:
        say("codex: not on PATH; skipped (install Codex, then rerun ds-next setup)")
        return False
    binary = ds_next_bin()
    if not binary.is_file():
        say(f"ds-next: {binary} not found; cannot register the server")
        return False
    ok = True
    code, text = _run([codex, "mcp", "get", "ds"])
    if code == 0 and str(binary) in text and "mcp" in text:
        say(f"mcp server ds: registered in Codex ({binary} mcp)")
    else:
        if code == 0:
            say("mcp server ds: registered with a different command; " + ("would replace" if check else "replacing"))
            if not check:
                _run([codex, "mcp", "remove", "ds"])
        if check:
            say(f"mcp server ds: would register {binary} mcp")
        else:
            code, text = _run([codex, "mcp", "add", "ds", "--", str(binary), "mcp"])
            say(f"mcp server ds: {'registered in Codex' if code == 0 else 'FAILED: ' + text.strip()}")
            ok = ok and code == 0
    sdir = skills_dir()
    if sdir is None:
        say("skills: not shipped with this install (source checkout only); skipped")
    else:
        for name in SKILLS:
            link, target = codex_home() / "skills" / name, sdir / name
            if link.is_symlink() and link.resolve() == target.resolve():
                say(f"skill /{name}: linked ({link})")
            elif link.exists() or link.is_symlink():
                say(f"skill /{name}: {link} exists and is not ours; left alone")
                ok = False
            elif check:
                say(f"skill /{name}: would link {link} -> {target}")
            else:
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(target)
                say(f"skill /{name}: linked ({link})")
    say("write tools (scaffold_project, adopt_repo, block_add, code_add, capture) still ask: that is the control point")
    return ok

