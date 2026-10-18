"""The deterministic core: knowledge base, scaffold, reconcile."""
import datetime as dt
import tomllib

import pytest
from conftest import make_canon

from ds_next import reconcile, scaffold

ANSWERS = {"name": "claims-features", "purpose": "Feature store for claims models", "owner": "ck"}


def test_canon_applicable_by_tags(canon):
    assert [s.id for s in canon.applicable(["python", "cli"])] == ["adr-000", "testing"]
    assert "error-handling" in [s.id for s in canon.applicable(["package"])]


def test_pointers_skip_code_and_check_pins(canon):
    assert canon.pointer_problems("see [[testing]] and [[nope]] but not `[[also-nope]]`") == [
        "[[nope]] is not in the canon"]
    assert canon.pointer_problems("[[testing@1]] is fine; [[testing@999]] is not") == [
        "[[testing@999]] pins a version the canon never had (current v1)"]


def test_skills_front_matter(skills):
    assert skills.all["so-capture"].description.startswith("Capture gotchas")
    assert skills.all["so-capture"].read().startswith("# so-capture")


def test_scaffold_decides_tags_and_defaults(canon):
    a = scaffold.Answers(**ANSWERS).resolve(canon)
    assert a.tags == ["python", "package", "cli"] and a.test_cmd == "uv run pytest -q"
    assert scaffold.Answers(**ANSWERS, snowflake="DB.S").resolve(canon).tags[-1] == "snowflake"
    # what the live agent sent once: only some tags. The scaffold's own come back, extras stay.
    assert scaffold.Answers(**ANSWERS, tags=["python", "cli", "dbt"]).resolve(canon).tags == [
        "python", "package", "cli", "dbt"]


def test_only_accepted_scaffolds(canon):
    with pytest.raises(ValueError, match="proposed, not accepted"):
        scaffold.Answers(**ANSWERS, scaffold="python-draft").resolve(canon)
    with pytest.raises(ValueError, match="the canon has python-cli, python-draft"):
        scaffold.Answers(**ANSWERS, scaffold="nope").resolve(canon)


def test_code_comes_from_the_canon_scaffold(canon, skills):
    files = scaffold.render(scaffold.Answers(**ANSWERS), canon, skills)
    assert files["src/claims_features/__init__.py"] == '"""Feature store for claims models"""\n'
    assert files["pyproject.toml"].startswith('[project]\nname = "claims-features"\n'
                                              'description = "Feature store for claims models"\n')
    assert ".gitignore" in files and "dot-gitignore" not in files
    m = tomllib.loads(files[".ds/manifest.toml"])
    assert (m["repo"]["scaffold"], m["repo"]["scaffold_version"]) == ("python-cli", 3)


@pytest.mark.parametrize("bad", [{"name": "Bad Name"}, {"purpose": " "}])
def test_answers_validate(bad):
    with pytest.raises(ValueError):
        scaffold.Answers(**{**ANSWERS, **bad})


def test_render_uses_pointers_not_text(canon, skills):
    files = scaffold.render(scaffold.Answers(**ANSWERS), canon, skills)
    agents = files["AGENTS.md"]
    assert "[[adr-000]]" in agents and "[[error-handling]]" in agents
    assert "Body of" not in agents                       # never the standard's prose
    assert "/so-capture" in agents and len(agents.splitlines()) < 40
    m = tomllib.loads(files[".ds/manifest.toml"])
    assert {k: v["status"] for k, v in m["standards"].items()} == {
        "adr-000": "adopted", "testing": "adopted", "error-handling": "adopted"}


def test_decline_needs_an_applicable_standard(canon, skills):
    with pytest.raises(ValueError, match="idempotency"):
        scaffold.render(scaffold.Answers(**ANSWERS, declines={"idempotency": "n/a"}), canon, skills)


def test_new_repo_reconciles_clean(tmp_path, canon, skills):
    a = scaffold.Answers(**ANSWERS, declines={"testing": "covered by the parent repo"})
    files = scaffold.write(a, tmp_path / "out" / a.name, canon, skills)
    repo = tmp_path / "out" / a.name
    assert "src/claims_features/__init__.py" in files
    assert (repo / ".git" / "hooks" / "pre-push").stat().st_mode & 0o111
    r = reconcile.check(repo, canon)
    assert r.ok and not r.pending, r
    assert r.adopted == ["adr-000", "error-handling"] and "testing" in r.declined


def test_write_refuses_nonempty(tmp_path, canon, skills):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "keep.txt").write_text("mine")
    with pytest.raises(FileExistsError):
        scaffold.write(scaffold.Answers(**{**ANSWERS, "name": "xx"}), tmp_path / "x", canon, skills)


def test_drift_is_pending_not_an_error(tmp_path, canon, skills):
    a = scaffold.Answers(**ANSWERS)
    scaffold.write(a, tmp_path / a.name, canon, skills, git=False)
    newer = make_canon(tmp_path / "canon2", bump={"testing": 2})
    r = reconcile.check(tmp_path / a.name, newer)
    assert r.ok and r.pending == ["testing v2"]


def test_broken_pointer_and_bad_decline_are_errors(tmp_path, canon, skills):
    a = scaffold.Answers(**ANSWERS)
    repo = tmp_path / a.name
    scaffold.write(a, repo, canon, skills, git=False)
    (repo / "README.md").write_text("# x\n\nSee [[gone]].\n")
    m = (repo / ".ds" / "manifest.toml").read_text()
    (repo / ".ds" / "manifest.toml").write_text(m.replace(
        '[standards.testing]\nstatus = "adopted"', '[standards.testing]\nstatus = "declined"'))
    r = reconcile.check(repo, canon)
    assert not r.ok
    assert any("[[gone]] is not in the canon" in e for e in r.errors) and any("testing: a decline needs" in e for e in r.errors)


def test_overdue_decline_is_reported(tmp_path, canon, skills):
    a = scaffold.Answers(**ANSWERS, declines={"testing": "later"})
    scaffold.write(a, tmp_path / a.name, canon, skills, git=False)
    r = reconcile.check(tmp_path / a.name, canon, today=dt.date.today() + dt.timedelta(days=91))
    assert r.ok and r.overdue == ["testing"]


def test_stale_block_is_reported_even_when_the_manifest_is_broken(tmp_path, canon):
    repo = tmp_path / "r"
    (repo / ".ds").mkdir(parents=True)
    (repo / ".ds" / "manifest.toml").write_text('[repo]\nname = "r"\n\n[blocks.block-demo]\nversion = 1\n')
    newer = make_canon(tmp_path / "canon2", bump={"block-demo": 2})
    r = reconcile.check(repo, newer)
    assert any("tags" in e for e in r.errors)
    assert r.pending == ["block-demo v2 (block; this repo has v1)"]
