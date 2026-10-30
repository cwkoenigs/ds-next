import json
from pathlib import Path

from ds_next import setup


def test_merge_allow_adds_only_missing_and_keeps_the_rest():
    base = {"theme": "dark", "permissions": {"allow": ["Bash(git status)", "mcp__ds__canon_list"]}}
    new, added = setup.merge_allow(base, ["mcp__ds__canon_list", "mcp__ds__canon_read"])
    assert added == ["mcp__ds__canon_read"]
    assert new["permissions"]["allow"] == ["Bash(git status)", "mcp__ds__canon_list", "mcp__ds__canon_read"]
    assert new["theme"] == "dark" and base["permissions"]["allow"] == ["Bash(git status)", "mcp__ds__canon_list"]


def test_merge_allow_from_empty_settings_is_idempotent():
    rules = setup.read_only_rules()
    assert "mcp__ds__scaffold_get" in rules and "mcp__ds__scaffold_project" not in rules
    once, added = setup.merge_allow({}, rules)
    assert added == rules
    twice, added_again = setup.merge_allow(once, rules)
    assert added_again == [] and twice == once


def test_skills_ship_with_the_checkout():
    d = setup.skills_dir()
    assert d is not None and (d / "ds-new" / "SKILL.md").is_file()


def test_backend_choice_env_then_config_then_path(tmp_path, monkeypatch):
    import shutil

    from ds_next import sdk
    monkeypatch.setattr(sdk, "CONFIG", tmp_path / "config.toml")
    monkeypatch.delenv("DS_AGENT", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert sdk.backend() == "cortex"                          # nothing anywhere: the original default
    monkeypatch.setattr(shutil, "which", lambda name: "/bin/claude" if name == "claude" else None)
    assert sdk.backend() == "claude"                          # the only CLI there
    monkeypatch.setattr(shutil, "which", lambda name: f"/bin/{name}")
    assert sdk.backend() == "cortex"                          # both: Cortex first, as before
    (tmp_path / "config.toml").write_text('agent = "claude"\n')
    assert sdk.configured() == "claude" and sdk.backend() == "claude"   # setup --agent decides
    monkeypatch.setenv("DS_AGENT", "cortex")
    assert sdk.backend() == "cortex"                          # the environment wins for one run
    (tmp_path / "config.toml").write_text('agent = "nope"\n')
    monkeypatch.delenv("DS_AGENT")
    assert sdk.configured() is None


def test_tool_id_reads_both_sdks_shapes():
    from ds_next import sdk
    assert sdk.tool_id("MCP", {"resource": "mcp__ds__canon_read\nInput: {}"}) == "mcp__ds__canon_read"
    assert sdk.tool_id("mcp__ds__canon_read", {"id": "testing"}) == "mcp__ds__canon_read"
    assert sdk.tool_id("Bash", {"command": "ls"}) == "Bash"


def test_set_default_agent_keeps_other_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(setup.Path, "home", lambda: tmp_path)
    (tmp_path / ".ds").mkdir()
    (tmp_path / ".ds" / "config.toml").write_text('theme = "light"\n')
    path = setup.set_default_agent("claude")
    assert path.read_text() == 'theme = "light"\nagent = "claude"\n'


def test_set_default_agent_keeps_the_world_tables(tmp_path, monkeypatch):
    import tomllib
    monkeypatch.setattr(setup.Path, "home", lambda: tmp_path)
    (tmp_path / ".ds").mkdir()
    cfg = tmp_path / ".ds" / "config.toml"
    world = ('# this machine\n\n[world]\nhost = "gitlab"\ngroup = "https://gitlab.example/ds"\n'
             'token_env = "GITLAB_TOKEN"\n\n[capture]\nrepo = "canon"\n')
    cfg.write_text(world)
    setup.set_default_agent("cortex")                  # no agent yet: it goes above the first table
    data = tomllib.loads(cfg.read_text())
    assert data["agent"] == "cortex" and data["world"]["host"] == "gitlab" and data["capture"]["repo"] == "canon"
    assert cfg.read_text().startswith("# this machine\nagent = \"cortex\"\n\n[world]")
    setup.set_default_agent("codex")                   # an agent already: only that line changes
    assert cfg.read_text().count("agent =") == 1 and tomllib.loads(cfg.read_text())["agent"] == "codex"
    assert cfg.read_text().endswith('[capture]\nrepo = "canon"\n')


def test_set_default_agent_keeps_a_broken_file_aside(tmp_path, monkeypatch):
    monkeypatch.setattr(setup.Path, "home", lambda: tmp_path)
    (tmp_path / ".ds").mkdir()
    (tmp_path / ".ds" / "config.toml").write_text("not = [toml\n")
    path = setup.set_default_agent("claude")
    assert path.read_text() == 'agent = "claude"\n'
    assert (tmp_path / ".ds" / "config.toml.bak").read_text() == "not = [toml\n"


def test_setup_claude_registers_links_and_allows(tmp_path, monkeypatch):
    import shutil
    calls: list[list[str]] = []

    def run(args):
        calls.append(args)
        return (1, "") if args[1:3] == ["mcp", "get"] else (0, "")
    monkeypatch.setattr(setup, "_run", run)
    monkeypatch.setattr(shutil, "which", lambda name: "/bin/claude" if name == "claude" else None)
    monkeypatch.setattr(setup.Path, "home", lambda: tmp_path)
    binary = tmp_path / "venv" / "bin" / "ds-next"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")
    monkeypatch.setattr(setup, "ds_next_bin", lambda: binary)
    said: list[str] = []
    assert setup.setup_claude(False, said.append)
    assert ["/bin/claude", "mcp", "add", "--scope", "user", "ds", "--", str(binary), "mcp"] in calls
    link = tmp_path / ".claude" / "skills" / "ds-new"
    assert link.is_symlink() and (link / "SKILL.md").is_file()
    allowed = __import__("json").loads((tmp_path / ".claude" / "settings.json").read_text())["permissions"]["allow"]
    assert "mcp__ds__canon_list" in allowed and "mcp__ds__scaffold_project" not in allowed
    # a second run changes nothing and says so
    monkeypatch.setattr(setup, "_run", lambda args: (0, f"Command: {binary}\nArgs: mcp") if args[1:3] == ["mcp", "get"] else (0, ""))
    again: list[str] = []
    assert setup.setup_claude(False, again.append)
    assert any("already allowed" in line for line in again) and any("linked (" in line for line in again)


def test_setup_codex_registers_and_links(tmp_path, monkeypatch):
    import shutil
    calls: list[list[str]] = []

    def run(args):
        calls.append(args)
        return (1, "") if args[1:3] == ["mcp", "get"] else (0, "")
    monkeypatch.setattr(setup, "_run", run)
    monkeypatch.setattr(shutil, "which", lambda name: "/bin/codex" if name == "codex" else None)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    binary = tmp_path / "venv" / "bin" / "ds-next"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")
    monkeypatch.setattr(setup, "ds_next_bin", lambda: binary)
    said: list[str] = []
    assert setup.setup_codex(False, said.append)
    assert ["/bin/codex", "mcp", "add", "ds", "--", str(binary), "mcp"] in calls
    link = tmp_path / "codex-home" / "skills" / "ds-new"
    assert link.is_symlink() and (link / "SKILL.md").is_file()
    assert setup.setup("auto", True, said.append)          # auto finds Codex on PATH too


def test_drop_allow_takes_only_ours():
    settings = {"permissions": {"allow": ["Bash(ls)", "mcp__ds__canon_list", "mcp__code__callers"]}}
    out, removed = setup.drop_allow(settings, setup.all_rules())
    assert out["permissions"]["allow"] == ["Bash(ls)"] and sorted(removed) == ["mcp__code__callers", "mcp__ds__canon_list"]
    assert setup.drop_allow({}, setup.all_rules()) == ({}, [])


def _fake_skills_os(root):
    for name in ("so-capture", "so-changes"):
        (root / name).mkdir(parents=True)
        (root / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
    (root / "so-empty").mkdir()                      # no SKILL.md: not a skill
    return root


def test_setup_claude_adds_code_and_skills_os_and_remove_undoes_it(tmp_path, monkeypatch):
    import shutil
    calls: list[list[str]] = []
    state: dict[str, str] = {}                      # the agent's registry of servers, by name

    def run(args):
        calls.append(args)
        if args[1:3] == ["mcp", "get"]:
            return (0, state[args[3]]) if args[3] in state else (1, "")
        if args[1:3] == ["mcp", "add"]:
            state[args[5]] = " ".join(args[7:])
        if args[1:3] == ["mcp", "remove"]:
            state.pop(args[5], None)
        return (0, "")
    monkeypatch.setattr(setup, "_run", run)
    monkeypatch.setattr(shutil, "which", lambda name: {"claude": "/bin/claude", "ds-code": "/npm/bin/ds-code"}.get(name))
    monkeypatch.setattr(setup.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("DS_SKILLS", str(_fake_skills_os(tmp_path / "skills-os")))
    binary = tmp_path / "venv" / "bin" / "ds-next"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")
    monkeypatch.setattr(setup, "ds_next_bin", lambda: binary)
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text('{"permissions": {"allow": ["Bash(ls)"]}}\n')
    theirs = tmp_path / ".claude" / "skills" / "so-capture"      # a link of their own, not ours
    theirs.parent.mkdir(parents=True)
    theirs.symlink_to(tmp_path / "elsewhere")

    said: list[str] = []
    assert not setup.setup_claude(False, said.append)            # their so-capture link is reported, not replaced
    assert state == {"ds": f"{binary} mcp", "code": "/npm/bin/ds-code mcp"}
    assert ["/bin/claude", "mcp", "add", "--scope", "user", "code", "--", "/npm/bin/ds-code", "mcp"] in calls
    skills = tmp_path / ".claude" / "skills"
    assert (skills / "ds-new").is_symlink() and (skills / "so-changes").resolve() == (tmp_path / "skills-os" / "so-changes")
    assert not (skills / "so-empty").exists() and (skills / "so-capture").resolve() == tmp_path / "elsewhere"
    assert any("so-capture" in line and "not ours" in line for line in said)
    allowed = json.loads(settings.read_text())["permissions"]["allow"]
    assert "mcp__code__callers" in allowed and "mcp__ds__canon_read" in allowed and "Bash(ls)" in allowed

    # --check reports and changes nothing
    before = len(calls)
    assert setup.remove("claude", True, said.append)
    assert state and calls[before:] == [c for c in calls[before:] if c[1:3] in (["mcp", "get"], ["skill", "list"])]

    undone: list[str] = []
    assert setup.remove("claude", False, undone.append)
    assert state == {}
    assert not (skills / "ds-new").exists() and not (skills / "so-changes").is_symlink()
    assert (skills / "so-capture").is_symlink()                  # theirs stays
    assert json.loads(settings.read_text())["permissions"]["allow"] == ["Bash(ls)"]
    assert any("config.toml: kept" in line for line in undone)
    # a second remove finds nothing and still succeeds
    again: list[str] = []
    assert setup.remove("claude", False, again.append)
    assert any("not registered" in line for line in again) and any("no read-only rules" in line for line in again)


def test_setup_cortex_adds_and_removes_skills_by_path(tmp_path, monkeypatch):
    import shutil
    calls: list[list[str]] = []
    listed: list[str] = []

    def run(args):
        calls.append(args)
        if args[1:3] == ["skill", "list"]:
            return 0, "\n".join(listed)
        if args[1:3] == ["skill", "add"]:
            listed.append(args[3])
        if args[1:3] == ["skill", "remove"]:
            listed.remove(args[3])
        return (1, "") if args[1:3] == ["mcp", "get"] else (0, "")
    monkeypatch.setattr(setup, "_run", run)
    monkeypatch.setattr(shutil, "which", lambda name: "/bin/cortex" if name == "cortex" else None)
    monkeypatch.setattr(setup.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("DS_SKILLS", str(_fake_skills_os(tmp_path / "skills-os")))
    binary = tmp_path / "venv" / "bin" / "ds-next"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")
    monkeypatch.setattr(setup, "ds_next_bin", lambda: binary)
    said: list[str] = []
    assert setup.setup_cortex(False, said.append)
    assert ["/bin/cortex", "mcp", "add", "ds", str(binary), "mcp"] in calls
    assert sorted(Path(p).name for p in listed) == ["ds-new", "ds-terminal-design", "so-capture", "so-changes"]
    assert "mcp__code__callers" not in json.loads((tmp_path / ".snowflake" / "cortex" / "settings.json").read_text())["permissions"]["allow"]
    assert setup.remove("cortex", False, said.append)
    assert listed == [] and ["/bin/cortex", "skill", "remove", str(tmp_path / "skills-os" / "so-capture")] in calls


def _claude_env(tmp_path, monkeypatch, registry, which):
    """A fake claude whose mcp registry is the dict; returns the call log."""
    import shutil
    calls: list[list[str]] = []

    def run(args):
        calls.append(args)
        if args[1:3] == ["mcp", "get"]:
            return (0, f"Command: {registry[args[3]]}") if args[3] in registry else (1, "")
        if args[1:3] == ["mcp", "add"]:
            registry[args[5]] = " ".join(args[7:])
        if args[1:3] == ["mcp", "remove"]:
            registry.pop(args[5], None)
        return (0, "")
    monkeypatch.setattr(setup, "_run", run)
    monkeypatch.setattr(shutil, "which", lambda name: which.get(name))
    monkeypatch.setattr(setup.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("DS_SKILLS", raising=False)
    binary = tmp_path / "venv" / "bin" / "ds-next"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")
    monkeypatch.setattr(setup, "ds_next_bin", lambda: binary)
    return calls, binary


def test_remove_leaves_a_code_server_that_runs_something_else(tmp_path, monkeypatch):
    registry = {"ds": f"{tmp_path}/venv/bin/ds-next mcp", "code": "/opt/other/code-server serve"}
    _claude_env(tmp_path, monkeypatch, registry, {"claude": "/bin/claude", "ds-code": "/npm/bin/ds-code"})
    said: list[str] = []
    assert setup.remove("claude", False, said.append)
    assert "ds" not in registry and registry["code"] == "/opt/other/code-server serve"
    assert any("code" in line and "not ours" in line for line in said)


def test_remove_takes_a_code_registration_after_ds_code_is_gone(tmp_path, monkeypatch):
    registry = {"code": "/npm/bin/ds-code mcp"}
    _claude_env(tmp_path, monkeypatch, registry, {"claude": "/bin/claude"})      # no ds-code on PATH any more
    assert setup.remove("claude", False, lambda line: None)
    assert registry == {}


def test_failed_registration_gets_no_allow_rules(tmp_path, monkeypatch):
    registry = {"code": "/opt/other/code-server serve"}
    _claude_env(tmp_path, monkeypatch, registry, {"claude": "/bin/claude", "ds-code": "/npm/bin/ds-code"})
    real_run = setup._run

    def run(args):                           # the other code server cannot be replaced
        if args[1:3] in (["mcp", "remove"], ["mcp", "add"]) and args[5] == "code":
            return (1, "registry is read only")
        return real_run(args)
    monkeypatch.setattr(setup, "_run", run)
    said: list[str] = []
    assert not setup.setup_claude(False, said.append)
    allowed = json.loads((tmp_path / ".claude" / "settings.json").read_text())["permissions"]["allow"]
    assert "mcp__ds__canon_list" in allowed and not any(r.startswith("mcp__code__") for r in allowed)


def test_remove_unlinks_a_dangling_link_of_ours_and_keeps_others(tmp_path, monkeypatch):
    _claude_env(tmp_path, monkeypatch, {}, {"claude": "/bin/claude"})
    skills_os = _fake_skills_os(tmp_path / "Developer" / "skills-os")   # found beside ~/Developer, like kb does
    folder = tmp_path / ".claude" / "skills"
    folder.mkdir(parents=True)
    (folder / "so-capture").symlink_to(skills_os / "so-capture")
    (folder / "so-old").symlink_to(skills_os / "so-old")                   # the checkout no longer has it: dangling
    (folder / "ds-new").symlink_to(setup.skills_dir() / "ds-new")
    (folder / "theirs").symlink_to(tmp_path / "elsewhere")                 # dangling too, but not ours
    (folder / "plain").mkdir()
    assert setup.remove("claude", False, lambda line: None)
    assert sorted(p.name for p in folder.iterdir()) == ["plain", "theirs"]


def test_allow_lists_survive_odd_settings_shapes():
    assert setup.merge_allow({"permissions": None}, ["a"]) == ({"permissions": {"allow": ["a"]}}, ["a"])
    assert setup.merge_allow({"permissions": {"allow": "x"}}, ["a"])[0]["permissions"]["allow"] == ["a"]
    assert setup.drop_allow({"permissions": None}, ["a"]) == ({"permissions": None}, [])
    assert setup.drop_allow({"permissions": []}, ["a"]) == ({"permissions": []}, [])


def test_skill_dirs_are_absolute_even_from_a_relative_ds_skills(tmp_path, monkeypatch):
    _fake_skills_os(tmp_path / "skills-os")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DS_SKILLS", "skills-os")
    dirs = setup.skill_dirs()
    assert all(p.is_absolute() for p in dirs) and (tmp_path / "skills-os" / "so-capture").resolve() in dirs
