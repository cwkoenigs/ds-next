"""Hidden acceptance tests for the `stamp` console script.

The implementation is reached only through the executable at $TARGET_BIN.
"""

import ast
import os
import subprocess
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]


TIMEOUT = 120


# --------------------------------------------------------------------------- helpers


@pytest.fixture
def env(tmp_path):
    """Environment with an isolated git identity/config."""
    cfg = tmp_path / "judge-gitconfig"
    cfg.write_text(
        "[user]\n"
        "\tname = Judge Tester\n"
        "\temail = judge@example.com\n"
        "[init]\n"
        "\tdefaultBranch = main\n"
    )
    e = os.environ.copy()
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_CEILING_DIRECTORIES"):
        e.pop(var, None)
    e["GIT_CONFIG_GLOBAL"] = str(cfg)
    e["GIT_CONFIG_NOSYSTEM"] = "1"
    e["GIT_TERMINAL_PROMPT"] = "0"
    return e


def target_bin():
    path = os.environ.get("TARGET_BIN")
    if not path:
        pytest.fail("TARGET_BIN is not set")
    return path


def stamp(env, cwd, target, *, name="demo-tool", purpose="A demo tool.",
          owner="Ada Lovelace", check=None, args=None):
    if args is None:
        args = [str(target), "--name", name, "--purpose", purpose, "--owner", owner]
        if check is not None:
            args += ["--check", check]
    return subprocess.run(
        [target_bin(), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )


def ok(result):
    assert result.returncode == 0, (
        f"stamp failed ({result.returncode})\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


def git(env, cwd, *args, check=True):
    r = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=TIMEOUT
    )
    if check:
        assert r.returncode == 0, f"git {args} failed:\n{r.stdout}\n{r.stderr}"
    return r


def load_pyproject(proj):
    with open(proj / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def load_ci(proj):
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((proj / ".gitlab-ci.yml").read_text(encoding="utf-8"))


def ci_purpose(ci):
    merged = {}
    merged.update(ci.get("variables") or {})
    merged.update((ci.get("test") or {}).get("variables") or {})
    assert "PURPOSE" in merged, f"PURPOSE variable missing from CI config: {ci!r}"
    return merged["PURPOSE"]


def docstring(proj, package):
    init = proj / "src" / package / "__init__.py"
    assert init.is_file(), f"{init} missing"
    tree = ast.parse(init.read_text(encoding="utf-8"))
    doc = ast.get_docstring(tree, clean=False)
    assert doc is not None, "__init__.py has no module docstring"
    return doc


def readme_ok(proj, name, purpose):
    text = (proj / "README.md").read_text(encoding="utf-8")
    assert text.startswith(f"# {name}\n\n{purpose}"), repr(text)


def assert_all_roundtrip(proj, name, package, purpose, owner="Ada Lovelace"):
    meta = load_pyproject(proj)["project"]
    assert meta["name"] == name
    assert meta["description"] == purpose
    assert meta["authors"] == [{"name": owner}]
    assert docstring(proj, package).strip() == purpose.strip()
    readme_ok(proj, name, purpose)
    assert ci_purpose(load_ci(proj)) == purpose


def setup_remote(env, tmp_path, proj):
    remote = tmp_path / "remote.git"
    git(env, tmp_path, "init", "--bare", str(remote))
    git(env, proj, "remote", "add", "origin", str(remote))
    return remote


def remote_has_main(env, remote):
    r = git(env, remote, "rev-parse", "--verify", "refs/heads/main", check=False)
    return r.returncode == 0, r.stdout.strip()


# --------------------------------------------------------------------------- tests


def test_basic_files_and_contents(env, tmp_path):
    proj = tmp_path / "proj"
    ok(stamp(env, tmp_path, proj, name="demo-tool", purpose="Stamps out demo projects.",
             owner="Ada Lovelace"))
    for rel in ("pyproject.toml", "src/demo_tool/__init__.py", ".gitlab-ci.yml", "README.md"):
        assert (proj / rel).is_file(), f"{rel} missing"
    meta = load_pyproject(proj)["project"]
    assert meta["name"] == "demo-tool"
    assert meta["description"] == "Stamps out demo projects."
    assert meta["authors"] == [{"name": "Ada Lovelace"}]
    assert docstring(proj, "demo_tool").strip() == "Stamps out demo projects."
    readme_ok(proj, "demo-tool", "Stamps out demo projects.")


def test_ci_default_check_and_purpose_variable(env, tmp_path):
    proj = tmp_path / "proj"
    ok(stamp(env, tmp_path, proj, purpose="CI purpose text"))
    ci = load_ci(proj)
    assert isinstance(ci, dict) and "test" in ci, ci
    assert ci["test"]["script"] == ["uv run pytest -q"]
    assert ci_purpose(ci) == "CI purpose text"
    hook = proj / ".git" / "hooks" / "pre-push"
    assert hook.is_file()
    assert "uv run pytest -q" in hook.read_text()


def test_git_repo_committed_and_clean(env, tmp_path):
    proj = tmp_path / "proj"
    ok(stamp(env, tmp_path, proj))
    assert (proj / ".git").is_dir()
    top = git(env, proj, "rev-parse", "--show-toplevel").stdout.strip()
    assert Path(top).resolve() == proj.resolve()
    git(env, proj, "rev-parse", "--verify", "HEAD")
    tracked = set(git(env, proj, "ls-files").stdout.split())
    for rel in ("pyproject.toml", "src/demo_tool/__init__.py", ".gitlab-ci.yml", "README.md"):
        assert rel in tracked, f"{rel} not committed; tracked={tracked}"
    status = git(env, proj, "status", "--porcelain", "--untracked-files=all").stdout
    assert status.strip() == "", f"working tree not clean:\n{status}"


def test_package_name_converts_all_dashes(env, tmp_path):
    proj = tmp_path / "proj"
    ok(stamp(env, tmp_path, proj, name="my-cool-tool2-x9"))
    assert (proj / "src" / "my_cool_tool2_x9" / "__init__.py").is_file()
    assert not (proj / "src" / "my-cool-tool2-x9").exists()
    assert load_pyproject(proj)["project"]["name"] == "my-cool-tool2-x9"


def test_purpose_with_quoting_metacharacters_roundtrips(env, tmp_path):
    proj = tmp_path / "proj"
    purpose = "He said \"hi\": it's 100% #1 {braces} [brackets] & <tags> $HOME `tick`"
    ok(stamp(env, tmp_path, proj, purpose=purpose))
    assert_all_roundtrip(proj, "demo-tool", "demo_tool", purpose)


def test_purpose_with_triple_quotes_and_backslashes(env, tmp_path):
    proj = tmp_path / "proj"
    purpose = 'Wraps """docs""" and \'\'\'more\'\'\' at C:\\new\\tool \\x41 \\'
    ok(stamp(env, tmp_path, proj, purpose=purpose))
    # File must be valid Python and the docstring must equal the purpose exactly.
    assert_all_roundtrip(proj, "demo-tool", "demo_tool", purpose)
    r = subprocess.run(
        ["python3", "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); import demo_tool; "
         "sys.stdout.write(demo_tool.__doc__)",
         str(proj / "src")],
        capture_output=True, text=True, timeout=TIMEOUT,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == purpose.strip()


def test_unicode_purpose_and_owner(env, tmp_path):
    proj = tmp_path / "proj"
    purpose = "Café ☕ résumé — naïve 日本語"
    owner = "Zoë Ångström"
    ok(stamp(env, tmp_path, proj, purpose=purpose, owner=owner))
    assert_all_roundtrip(proj, "demo-tool", "demo_tool", purpose, owner=owner)


@pytest.mark.parametrize(
    "purpose",
    ["yes", "1.0", "null", "key: value # not a comment", "*alias", "- dash first", "!tag", "@at"],
)
def test_yaml_ambiguous_purpose_stays_a_string(env, tmp_path, purpose):
    proj = tmp_path / "proj"
    ok(stamp(env, tmp_path, proj, purpose=purpose))
    assert ci_purpose(load_ci(proj)) == purpose
    assert load_pyproject(proj)["project"]["description"] == purpose
    assert docstring(proj, "demo_tool").strip() == purpose


def test_owner_with_quotes_and_backslash(env, tmp_path):
    proj = tmp_path / "proj"
    owner = 'Bob "The Builder" O\'Brien \\ Co'
    ok(stamp(env, tmp_path, proj, owner=owner))
    assert load_pyproject(proj)["project"]["authors"] == [{"name": owner}]


def test_custom_check_in_ci_and_executable_hook(env, tmp_path):
    proj = tmp_path / "proj"
    check = "python3 -c \"import sys; sys.exit(0)\" && echo 'done: #1'"
    ok(stamp(env, tmp_path, proj, check=check))
    ci = load_ci(proj)
    assert ci["test"]["script"] == [check]
    hook = proj / ".git" / "hooks" / "pre-push"
    assert hook.is_file()
    assert os.access(hook, os.X_OK), "pre-push hook is not executable"


def test_hook_passing_check_allows_push_and_runs_in_repo_root(env, tmp_path):
    proj = tmp_path / "proj"
    marker = tmp_path / "hook-ran.txt"
    check = f'test -f pyproject.toml && echo "it\'s ok" > "{marker}"'
    ok(stamp(env, tmp_path, proj, check=check))
    assert not marker.exists(), "check should not have run yet"
    remote = setup_remote(env, tmp_path, proj)
    r = git(env, proj, "push", "origin", "HEAD:refs/heads/main", check=False)
    assert r.returncode == 0, f"push failed:\n{r.stdout}\n{r.stderr}"
    assert marker.is_file(), "pre-push hook did not run the check"
    assert marker.read_text().strip() == "it's ok"
    present, sha = remote_has_main(env, remote)
    assert present
    assert sha == git(env, proj, "rev-parse", "HEAD").stdout.strip()


def test_hook_failing_check_blocks_push(env, tmp_path):
    proj = tmp_path / "proj"
    ok(stamp(env, tmp_path, proj, check="echo checking; exit 3"))
    remote = setup_remote(env, tmp_path, proj)
    r = git(env, proj, "push", "origin", "HEAD:refs/heads/main", check=False)
    assert r.returncode != 0, "push should be rejected when the check fails"
    present, _ = remote_has_main(env, remote)
    assert not present, "failing check must not let the push through"


def test_hook_check_with_compound_failure_blocks_push(env, tmp_path):
    proj = tmp_path / "proj"
    ok(stamp(env, tmp_path, proj, check="true && test -f does-not-exist.txt"))
    remote = setup_remote(env, tmp_path, proj)
    r = git(env, proj, "push", "origin", "HEAD:refs/heads/main", check=False)
    assert r.returncode != 0
    assert not remote_has_main(env, remote)[0]


@pytest.mark.parametrize(
    "bad_name",
    ["Demo", "demo_tool", "demo tool", "", "demo.tool", "../escape", "dëmo", "demo/tool"],
)
def test_invalid_names_rejected_without_side_effects(env, tmp_path, bad_name):
    work = tmp_path / "work"
    work.mkdir()
    proj = work / "proj"
    r = stamp(env, work, proj, name=bad_name)
    assert r.returncode != 0, f"name {bad_name!r} should be rejected"
    assert not proj.exists(), "target must not be created for an invalid name"
    assert sorted(p.name for p in work.iterdir()) == []
    assert not (tmp_path / "escape").exists()


def test_existing_nonempty_target_is_not_clobbered(env, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    precious = proj / "README.md"
    precious.write_text("precious content\n")
    r = stamp(env, tmp_path, proj)
    assert r.returncode != 0, "stamping into a non-empty directory should fail"
    assert precious.read_text() == "precious content\n"
    assert not (proj / "pyproject.toml").exists()
    assert not (proj / ".git").exists()


def test_second_run_on_same_target_fails_and_keeps_first(env, tmp_path):
    proj = tmp_path / "proj"
    ok(stamp(env, tmp_path, proj, purpose="First purpose."))
    head = git(env, proj, "rev-parse", "HEAD").stdout.strip()
    r = stamp(env, tmp_path, proj, purpose="Second purpose.")
    assert r.returncode != 0
    assert load_pyproject(proj)["project"]["description"] == "First purpose."
    assert git(env, proj, "rev-parse", "HEAD").stdout.strip() == head


@pytest.mark.parametrize("missing", ["--name", "--purpose", "--owner"])
def test_missing_required_option_fails(env, tmp_path, missing):
    proj = tmp_path / "proj"
    values = {"--name": "demo-tool", "--purpose": "p", "--owner": "o"}
    args = [str(proj)]
    for flag, value in values.items():
        if flag != missing:
            args += [flag, value]
    r = stamp(env, tmp_path, proj, args=args)
    assert r.returncode != 0
    assert not proj.exists()


def test_relative_target_resolved_against_cwd(env, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    ok(stamp(env, work, "rel-proj"))
    proj = work / "rel-proj"
    assert (proj / "pyproject.toml").is_file()
    assert (proj / ".git").is_dir()
    status = git(env, proj, "status", "--porcelain").stdout
    assert status.strip() == ""


def test_target_inside_existing_repo_gets_its_own_repo(env, tmp_path):
    outer = tmp_path / "outer"
    outer.mkdir()
    git(env, outer, "init")
    (outer / "outer.txt").write_text("outer\n")
    git(env, outer, "add", "outer.txt")
    git(env, outer, "commit", "-m", "outer init")
    outer_head = git(env, outer, "rev-parse", "HEAD").stdout.strip()

    proj = outer / "proj"
    ok(stamp(env, tmp_path, proj))

    top = git(env, proj, "rev-parse", "--show-toplevel").stdout.strip()
    assert Path(top).resolve() == proj.resolve(), "project must be its own git repo"
    assert git(env, outer, "rev-parse", "HEAD").stdout.strip() == outer_head
    assert git(env, outer, "ls-files").stdout.split() == ["outer.txt"]
    staged = git(env, outer, "diff", "--cached", "--name-only").stdout.strip()
    assert staged == "", "outer repo index must not be touched"
    assert (proj / ".git" / "hooks" / "pre-push").is_file()
    assert not (outer / ".git" / "hooks" / "pre-push").exists()
