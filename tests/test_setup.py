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
