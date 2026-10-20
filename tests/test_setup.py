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
