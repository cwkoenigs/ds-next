"""`ds-next setup`: connect this machine's agents to the knowledge system, idempotently.

Cortex Code today: register the `ds` MCP server, add the /ds-new skill, and allow the read-only
ds tools so reading the canon never prompts. The four write tools keep prompting: that approval
is the control point. Every step reports what it found and what it changed; --check changes
nothing.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

SKILLS = ("ds-new",)


def cortex_home() -> Path:
    return Path.home() / ".snowflake" / "cortex"


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
    p = subprocess.run(args, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)


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
    settings_path = cortex_home() / "settings.json"
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
    say("write tools (scaffold_project, block_add, code_add, capture) still ask: that is the control point")
    return ok
