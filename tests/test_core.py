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


def test_new_repo_starts_on_canon_lib_when_the_canon_ships_it(tmp_path, canon, skills):
    a = scaffold.Answers(**ANSWERS)
    files = scaffold.render(a, canon, skills)
    assert "canon_lib" not in files[".ds/manifest.toml"] and "canon-lib" not in files["AGENTS.md"]
    (canon.root / "lib").mkdir()
    (canon.root / "lib" / "pyproject.toml").write_text('[project]\nname = "canon-lib"\n')
    files = scaffold.render(a, canon, skills)
    manifest = files[".ds/manifest.toml"]
    assert f'canon_lib = "{canon.root / "lib"}"' in manifest and f'canon = "{canon.root}"' in manifest
    assert "canon_index = " in manifest
    assert "`canon-lib` is a dependency" in files["AGENTS.md"]


def test_type_and_outputs_are_recorded(tmp_path, canon, skills):
    a = scaffold.Answers(**{**ANSWERS, "scaffold": "ml-pipeline"})
    scaffold.write(a, tmp_path / a.name, canon, skills, git=False)
    m = (tmp_path / a.name / ".ds" / "manifest.toml").read_text()
    assert 'type = "ml-pipeline"' in m and 'outputs = ["model", "features"]' in m
    assert "Outputs: model, features." in (tmp_path / a.name / "README.md").read_text()
    r = reconcile.check(tmp_path / a.name, canon)
    assert r.ok and r.type == "ml-pipeline" and r.outputs == ["model", "features"]


def test_no_outputs_is_recorded_as_empty(tmp_path, canon, skills):
    a = scaffold.Answers(**ANSWERS)
    scaffold.write(a, tmp_path / a.name, canon, skills, git=False)
    m = (tmp_path / a.name / ".ds" / "manifest.toml").read_text()
    assert 'type = "cli"' in m and "outputs = []" in m
    assert "Outputs:" not in (tmp_path / a.name / "README.md").read_text()
    assert reconcile.check(tmp_path / a.name, canon).outputs == []


# ── an existing repository joins the system ──────────────────────────────────
def _node_repo(root, readme="# shop\n\nDaily orders for the shop floor. More detail follows.\n\nSecond paragraph.\n"):
    import json
    import subprocess
    root.mkdir(parents=True)
    subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "main"], check=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"next": "15", "react": "19", "snowflake-sdk": "2"},
                                                   "scripts": {"test": "node --test", "typecheck": "tsc --noEmit"}}))
    (root / "tsconfig.json").write_text("{}")
    (root / "README.md").write_text(readme)
    (root / "CLAUDE.md").write_text("# shop\n\nproject instructions\n")
    (root / "docs" / "adr").mkdir(parents=True)
    return root


def test_detect_reads_the_stack_and_the_readme(tmp_path):
    d = scaffold.detect(_node_repo(tmp_path / "Shop Floor"))
    assert d.name == "shop-floor"
    assert d.tags == ["nextjs", "node", "service", "snowflake", "typescript", "web"]
    assert d.purpose == "Daily orders for the shop floor."
    assert (d.test_cmd, d.lint_cmd) == ("npm test", "npm run typecheck")


def test_adopt_writes_only_the_system_files_and_leaves_standards_pending(tmp_path, canon, skills):
    repo = _node_repo(tmp_path / "shop")
    before = {p.name: p.read_text() for p in (repo / "README.md", repo / "CLAUDE.md")}
    a = scaffold.detect(repo)
    a.tags = ["python", "cli"]                      # the fixture canon's standards apply to these
    written = scaffold.adopt(repo, a, canon, skills, today=dt.date(2026, 10, 20))
    assert written == [".ds/manifest.toml", "AGENTS.md", "DECISIONS.md", ".git/hooks/pre-push"]
    assert {p.name: p.read_text() for p in (repo / "README.md", repo / "CLAUDE.md")} == before
    m = tomllib.loads((repo / ".ds" / "manifest.toml").read_text())
    assert m["repo"]["name"] == "shop" and m["repo"]["tags"] == ["cli", "python"] and "standards" not in m
    agents = (repo / "AGENTS.md").read_text()
    assert "Project instructions: `CLAUDE.md`" in agents and "[[adr-000]]" in agents and "[[testing]]" in agents
    assert "pending until the owner adopts" in agents
    assert "docs/adr/" in (repo / "DECISIONS.md").read_text()
    assert (repo / ".git" / "hooks" / "pre-push").stat().st_mode & 0o111
    r = reconcile.check(repo, canon)
    assert r.ok and r.pending == ["adr-000 v1", "testing v1"] and r.adopted == []
    with pytest.raises(FileExistsError, match="already in the system"):
        scaffold.adopt(repo, a, canon, skills)


def test_adopt_all_adopts_and_an_existing_agents_md_gains_one_section(tmp_path, canon, skills):
    repo = _node_repo(tmp_path / "shop")
    (repo / "AGENTS.md").write_text("# AGENTS.md\n\nkeep this\n")
    a = scaffold.detect(repo)
    a.tags = ["python"]
    written = scaffold.adopt(repo, a, canon, skills, adopt_all=True)
    assert written[1] == "AGENTS.md (standards section added)"
    agents = (repo / "AGENTS.md").read_text()
    assert agents.startswith("# AGENTS.md\n\nkeep this\n") and agents.count("## Standards") == 1
    assert "This repo follows [[adr-000]]" in agents
    r = reconcile.check(repo, canon)
    assert r.ok and r.pending == [] and r.adopted == ["adr-000", "testing"]


def test_adopt_refuses_without_purpose_or_git(tmp_path, canon, skills):
    repo = _node_repo(tmp_path / "shop", readme="# only a heading\n")
    with pytest.raises(ValueError, match="purpose"):
        scaffold.adopt(repo, scaffold.detect(repo), canon, skills)
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "README.md").write_text("Does things.\n")
    with pytest.raises(ValueError, match="git"):
        scaffold.adopt(bare, scaffold.detect(bare), canon, skills)
    assert not (bare / ".ds").exists()
