"""Accepted code blocks: added deterministically, tracked in the manifest, updated through reconcile."""
import asyncio
import os
import subprocess
import sys
import tomllib

import pytest
from conftest import make_canon

from ds_next import agent, reconcile, scaffold
from ds_next.kb import CanonError

ANSWERS = {"name": "demo-cli", "purpose": "A demo", "owner": "ck"}


@pytest.fixture
def repo(tmp_path, canon, skills):
    scaffold.write(scaffold.Answers(**ANSWERS), tmp_path / "demo-cli", canon, skills, git=False)
    return tmp_path / "demo-cli"


def test_add_block_copies_code_tests_requirements_and_records_it(repo, canon):
    done = scaffold.add_block(repo, "block-demo", canon, by="ck")
    assert done["note"] == "added" and done["requires"] == ["rich>=13", "pyyaml>=6"]
    assert (repo / "src/demo_cli/demo_mod.py").read_text().startswith("VERSION = 1")
    assert "from demo_cli.demo_mod import shout" in (repo / "tests/test_demo_mod.py").read_text()
    py = tomllib.loads((repo / "pyproject.toml").read_text())
    assert "rich>=13" in py["project"]["dependencies"] and "pyyaml>=6" in py["dependency-groups"]["dev"]
    m = tomllib.loads((repo / ".ds/manifest.toml").read_text())
    assert m["blocks"]["block-demo"]["version"] == 1
    r = reconcile.check(repo, canon)
    assert r.ok and r.blocks == ["block-demo v1"] and not r.pending
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_demo_mod.py"],
                         cwd=repo, env={**os.environ, "PYTHONPATH": str(repo / "src")}, capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stdout                      # the block's own test passes in the repo


def test_adding_twice_is_a_no_op_and_foreign_files_are_never_overwritten(repo, canon):
    scaffold.add_block(repo, "block-demo", canon)
    assert scaffold.add_block(repo, "block-demo", canon)["note"] == "already at this version"
    fresh = repo.parent / "other"
    scaffold.write(scaffold.Answers(**{**ANSWERS, "name": "other"}), fresh, canon, scaffold.Skills(), git=False)
    (fresh / "src/other/demo_mod.py").write_text("mine = True\n")
    with pytest.raises(FileExistsError, match="not written by block-demo"):
        scaffold.add_block(fresh, "block-demo", canon)
    assert (fresh / "src/other/demo_mod.py").read_text() == "mine = True\n"


def test_a_newer_block_is_pending_until_updated(repo, tmp_path):
    old = make_canon(tmp_path / "c1")
    scaffold.add_block(repo, "block-demo", old)
    newer = make_canon(tmp_path / "c2", bump={"block-demo": 2})
    r = reconcile.check(repo, newer)
    assert r.pending == ["block-demo v2 (block; this repo has v1)"]
    assert scaffold.add_block(repo, "block-demo", newer)["note"] == "updated"
    assert (repo / "src/demo_cli/demo_mod.py").read_text().startswith("VERSION = 2")
    m = (repo / ".ds/manifest.toml").read_text()
    assert m.count("[blocks.block-demo]") == 1 and not reconcile.check(repo, newer).pending


def test_only_accepted_unchanged_blocks(repo, canon):
    with pytest.raises(ValueError, match="proposed, not accepted"):
        scaffold.add_block(repo, "block-draft", canon)
    (canon.root / "blocks/block-demo/code/demo_mod.py").write_text("edited without a version bump\n")
    with pytest.raises(CanonError, match="changed since index.json"):
        scaffold.add_block(repo, "block-demo", canon)


def test_bad_block_entries_are_errors(repo, canon):
    m = repo / ".ds/manifest.toml"
    m.write_text(m.read_text() + '\n[blocks.block-nope]\nversion = 1\n\n[blocks.block-demo]\nversion = 9\n')
    errors = reconcile.check(repo, canon).errors
    assert any("block-nope" in e for e in errors) and any("from 1 to v1" in e for e in errors)


def test_block_tools(repo, canon, skills):
    tools = {t.name: t for t in agent.tools(canon, skills, repo)}
    text = asyncio.run(tools["block_list"].handler({"tags": ""}))["content"][0]["text"]
    assert "block-demo v1" in text and "block-draft" not in text
    got = asyncio.run(tools["block_get"].handler({"id": "block-demo"}))["content"][0]["text"]
    assert "About block-demo" in got and "def shout" in got
    added = asyncio.run(tools["block_add"].handler({"id": "block-demo"}))["content"][0]["text"]
    assert added.startswith("added: block-demo v1")
    assert {"mcp__ds__block_list", "mcp__ds__block_get"} <= agent.READ_ONLY_IDS
    assert "mcp__ds__block_add" not in agent.READ_ONLY_IDS      # writes always ask


def test_requirements_that_cannot_be_added_are_reported(repo, canon):
    (repo / "pyproject.toml").write_text('[project]\nname = "demo-cli"\ndependencies = [\n  "typer",\n]\n')
    done = scaffold.add_block(repo, "block-demo", canon)
    assert done["requires"] == [] and done["manual"] == ["rich>=13 (dependencies)", "pyyaml>=6 (dev)"]


# -- an update replaces only what the block wrote; nothing goes through a link (rule-cli's review)

def test_an_update_never_replaces_a_file_the_block_did_not_write(repo, tmp_path):
    old = make_canon(tmp_path / "c1")
    scaffold.add_block(repo, "block-demo", old)
    manifest = repo / ".ds/manifest.toml"
    text = manifest.read_text()
    assert 'files = ["src/demo_cli/demo_mod.py", "tests/test_demo_mod.py"]' in text
    # as if v1 had written only its module, and the tests file were the person's own
    manifest.write_text(text.replace('files = ["src/demo_cli/demo_mod.py", "tests/test_demo_mod.py"]', 'files = ["src/demo_cli/demo_mod.py"]'))
    (repo / "tests/test_demo_mod.py").write_text("mine = True\n")
    newer = make_canon(tmp_path / "c2", bump={"block-demo": 2})
    with pytest.raises(FileExistsError, match=r"not updated: tests/test_demo_mod.py already exist and were not written by block-demo"):
        scaffold.add_block(repo, "block-demo", newer)
    assert (repo / "tests/test_demo_mod.py").read_text() == "mine = True\n"
    assert (repo / "src/demo_cli/demo_mod.py").read_text().startswith("VERSION = 1")     # refused before anything was written


@pytest.mark.parametrize(("tests_file", "updates"), [(None, True), ("mine = True\n", False)])
def test_a_table_from_before_files_were_listed_trusts_its_module_and_the_tests_that_import_it(repo, tmp_path, tests_file, updates):
    scaffold.add_block(repo, "block-demo", make_canon(tmp_path / "c1"))
    manifest = repo / ".ds/manifest.toml"
    manifest.write_text("\n".join(line for line in manifest.read_text().split("\n") if not line.startswith("files = ")))
    if tests_file:
        (repo / "tests/test_demo_mod.py").write_text(tests_file)
    newer = make_canon(tmp_path / "c2", bump={"block-demo": 2})
    if updates:
        assert scaffold.add_block(repo, "block-demo", newer)["note"] == "updated"
    else:
        with pytest.raises(FileExistsError, match="not updated: tests/test_demo_mod.py"):
            scaffold.add_block(repo, "block-demo", newer)


@pytest.mark.skipif(sys.platform == "win32", reason="symbolic links need privileges on Windows")
@pytest.mark.parametrize("rel", ["pyproject.toml", ".ds/manifest.toml"])
def test_no_metadata_is_written_through_a_link(repo, canon, tmp_path, rel):
    from ds_next import code
    outside = tmp_path / "outside.toml"
    outside.write_text((repo / rel).read_text())
    (repo / rel).unlink()
    (repo / rel).symlink_to(outside)
    before = outside.read_text()
    with pytest.raises(ValueError, match=r"refusing to write .* is a symbolic link"):
        scaffold.add_block(repo, "block-demo", canon)
    with pytest.raises(ValueError, match=r"refusing to write .* is a symbolic link"):
        code.add(repo, ["block-demo:shout"], canon)
    assert outside.read_text() == before
    assert not (repo / "tests/test_demo_mod.py").exists()
