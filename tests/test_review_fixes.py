"""One regression test per finding from the Codex review of 2026-10-16, named after it."""
import asyncio
import types
import json
import os
import re
import signal
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml
from conftest import make_canon
from cortex_agent_sdk.cortexcode import create_sdk_mcp_server
from mcp.types import CallToolRequest, CallToolRequestParams

from ds_next import agent, reconcile, scaffold
from ds_next.kb import Canon, CanonError, Skills, canon_path
from ds_next.ui import Approver

HOSTILE = 'Print "hello" \\ 🚀 """ end'
COLON_CMD = 'echo "lint: skipped"'
ANSWERS = {"name": "demo-cli", "purpose": "A demo", "owner": "ck"}


def call(tools, name, args):
    t = next(t for t in tools if t.name == name)
    out = asyncio.run(t.handler(args))
    return out["content"][0]["text"], out.get("is_error", False)


# -- generated files are always valid, whatever the user typed (canon templates + ds-next)

REAL = canon_path()


@pytest.mark.skipif(REAL is None or not (REAL / "scaffolds").is_dir(), reason="needs the canon checkout")
@pytest.mark.parametrize("sid", ["python-cli", "python-package"])
def test_real_scaffolds_survive_hostile_text(tmp_path, sid):
    canon = Canon(REAL)
    a = scaffold.Answers(name="demo-x", purpose=HOSTILE, scaffold=sid, owner="ck",
                         test_cmd=COLON_CMD, lint_cmd=COLON_CMD, notes="emoji 🚀 ok")
    scaffold.write(a, tmp_path / "demo-x", canon, Skills(), git=False)
    repo = tmp_path / "demo-x"
    for f in repo.rglob("*.py"):
        compile(f.read_text(), str(f), "exec")                        # no injected statements
    for f in (repo / "pyproject.toml", repo / ".ds" / "manifest.toml"):
        tomllib.loads(f.read_text())                                  # emoji did not break TOML
    script = yaml.safe_load((repo / ".gitlab-ci.yml").read_text())["test"]["script"]
    assert script[-2:] == [COLON_CMD, COLON_CMD]                      # still strings, not mappings
    doc = subprocess.run([sys.executable, "-c", "import demo_x; print(demo_x.__doc__)"], cwd=repo,
                         env={**os.environ, "PYTHONPATH": str(repo / "src")}, capture_output=True,
                         text=True, check=False)
    assert doc.stdout.strip() == HOSTILE, doc.stderr


@pytest.mark.parametrize("bad", ["two\nlines", "tab\there", "nul\x00"])
def test_answers_are_one_line(bad):
    with pytest.raises(ValueError, match="one line"):
        scaffold.Answers(**{**ANSWERS, "purpose": bad})


@pytest.mark.parametrize("name", ["class", "match", "my--cli", "trailing-"])
def test_names_must_make_importable_packages(name):
    with pytest.raises(ValueError):
        scaffold.Answers(**{**ANSWERS, "name": name})


def test_a_decline_needs_a_reason():
    with pytest.raises(ValueError, match="needs a reason"):
        scaffold.Answers(**ANSWERS, declines={"testing": " "})


# -- writes stay inside the new repo

def test_paths_outside_the_repo_are_refused(tmp_path):
    for rel in ("../evil.txt", "/etc/evil.txt", "a/../../evil.txt"):
        with pytest.raises(ValueError, match="plain relative path"):
            scaffold._inside(tmp_path, rel)
    (tmp_path / "out").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "out")
    with pytest.raises(ValueError, match="symbolic link"):
        scaffold._inside(tmp_path, "link/file.txt")


def test_symlinked_destination_is_refused(tmp_path, canon, skills):
    (tmp_path / "real").mkdir()
    (tmp_path / "demo-cli").symlink_to(tmp_path / "real")
    with pytest.raises(ValueError, match="symbolic link"):
        scaffold.write(scaffold.Answers(**ANSWERS), tmp_path / "demo-cli", canon, skills)


def test_hook_symlink_is_replaced_not_followed(tmp_path, canon, skills):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    repo = tmp_path / "demo-cli"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / ".git" / "hooks" / "pre-push").symlink_to(victim)
    scaffold.write(scaffold.Answers(**ANSWERS), repo, canon, skills)
    assert victim.read_text() == "keep me"
    assert not (repo / ".git" / "hooks" / "pre-push").is_symlink()


def test_template_paths_from_the_index_are_checked(tmp_path):
    canon = make_canon(tmp_path / "c")
    data = json.loads((canon.root / "index.json").read_text())
    data["scaffolds"][0]["files"].append("../escape.txt")
    data["scaffolds"][0]["hash"] = ""                 # get past the hash check to the path check
    (canon.root / "index.json").write_text(json.dumps(data))
    with pytest.raises(CanonError, match="plain relative path"):
        Canon(canon.root).render_scaffold("python-cli", {"package": "x"})


# -- git failures surface instead of reporting success

def test_git_failure_raises(tmp_path):
    with pytest.raises(scaffold.ScaffoldError, match="failed"):
        scaffold._git(tmp_path, "not-a-git-command")


def test_never_stages_into_a_parent_repository(tmp_path, canon, skills, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    real = scaffold._git
    monkeypatch.setattr(scaffold, "_git", lambda d, *a: None if a[0] == "init" else real(d, *a))  # init "fails"
    with pytest.raises(scaffold.ScaffoldError, match="git resolves it to"):
        scaffold.write(scaffold.Answers(**ANSWERS), tmp_path / "demo-cli", canon, skills)
    assert subprocess.run(["git", "-C", str(tmp_path), "status", "--porcelain"], capture_output=True,
                          text=True, check=True).stdout.count("demo-cli") == 1      # untracked, not staged


def test_hook_says_so_when_ds_next_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "nowhere" / "ds-next")])
    monkeypatch.setattr(scaffold.shutil, "which", lambda _: None)
    hook = tmp_path / "pre-push"
    hook.write_text(scaffold._hook_text())
    r = subprocess.run(["sh", str(hook)], env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, check=False)
    assert r.returncode == 0 and "reconcile did not run" in r.stderr


# -- reconcile answers instead of crashing

@pytest.mark.parametrize("manifest, expected", [
    ("", "no [repo] table"),
    ('[repo]\nname = "x"\ntags = "python"\n', "tags must be a non-empty list"),
    ('[repo]\nname = "x"\ntags = ["python"]\n[standards.testing]\nstatus = "adopted"\nversion = "two"\n',
     "version must be a whole number"),
    (('[repo]\nname = "x"\ntags = ["python"]\n[standards.testing]\nstatus = "declined"\nversion = 1\n'
      'by = "ck"\nreason = "r"\nrevisit = "soon"\n'), "revisit must be a date"),
    ('standards = 3\n[repo]\nname = "x"\ntags = ["python"]\n', "one table per standard"),
])
def test_bad_manifests_are_errors_not_crashes(tmp_path, canon, manifest, expected):
    (tmp_path / ".ds").mkdir()
    (tmp_path / ".ds" / "manifest.toml").write_text(manifest)
    r = reconcile.check(tmp_path, canon)
    assert not r.ok and any(expected in e for e in r.errors), r.errors


def test_pointers_are_checked_in_every_doc(tmp_path, canon, skills):
    scaffold.write(scaffold.Answers(**ANSWERS), tmp_path / "demo-cli", canon, skills, git=False)
    repo = tmp_path / "demo-cli"
    (repo / "docs").mkdir()
    (repo / "docs" / "guide.md").write_text("See [[nope]] and [[testing@999]].\n")
    (repo / ".venv").mkdir()
    (repo / ".venv" / "vendored.md").write_text("[[ignored-here]]\n")
    errors = reconcile.check(repo, canon).errors
    assert "docs/guide.md: [[nope]] is not in the canon" in errors
    assert any("docs/guide.md: [[testing@999]]" in e for e in errors)
    assert not any("ignored-here" in e for e in errors)


# -- the scaffold the model fetched is the scaffold that is used

def test_scaffold_project_requires_a_fetch_in_this_session(tmp_path, canon, skills):
    tools = agent.tools(canon, skills, tmp_path)
    args = {"scaffold": "python-cli", "scaffold_version": 3, **ANSWERS}
    text, err = call(tools, "scaffold_project", args)      # right version, but never fetched
    assert err and text.startswith("ERROR:") and "scaffold_get" in text
    call(tools, "scaffold_get", {"id": "python-cli"})
    text, err = call(tools, "scaffold_project", args)
    assert not err and "created" in text


def test_canon_changes_are_seen_and_stale_templates_refused(tmp_path, skills):
    canon = make_canon(tmp_path / "c")
    assert canon.scaffolds["python-cli"].version == 3
    newer = make_canon(tmp_path / "c2", bump={})
    data = json.loads((newer.root / "index.json").read_text())
    data["scaffolds"][0]["version"] = 4
    (canon.root / "index.json").write_text(json.dumps(data))
    os.utime(canon.root / "index.json", ns=(1, 1))           # a different mtime, as an edit would make
    assert canon.scaffolds["python-cli"].version == 4         # the same Canon object sees the update
    (canon.root / "scaffolds" / "python-cli" / "files" / "pyproject.toml").write_text("edited without a bump\n")
    with pytest.raises(CanonError, match="changed since index.json was built"):
        canon.render_scaffold("python-cli", {"package": "x"})


# -- approvals: one at a time, the whole request, explicit answers only

def test_approvals_are_serialized_and_show_everything():
    seen, active, peak = [], [0], [0]

    async def ask(title, detail):
        active[0] += 1
        peak[0] = max(peak[0], active[0])
        seen.append(detail)
        await asyncio.sleep(0.05)
        active[0] -= 1
        return "y"

    approve = Approver(ask)
    long_cmd = "echo ok; " * 400 + "rm -rf ~/important"

    async def go():
        return await asyncio.gather(approve("Bash", {"resource": long_cmd}, None),
                                    approve("Bash", {"resource": "ls"}, None))

    results = asyncio.run(go())
    assert all(r.behavior == "allow" for r in results)
    assert peak[0] == 1                                       # never two prompts at once
    assert seen[0].endswith("rm -rf ~/important")             # nothing cut off the end


def test_enter_alone_is_not_an_approval():
    answers = iter(["", "  ", "n"])
    calls = []

    async def ask(title, detail):
        calls.append(title)
        return next(answers)

    result = asyncio.run(Approver(ask)("Bash", {"resource": "rm x"}, None))
    assert result.behavior == "deny" and len(calls) == 3


def test_reset_forgets_approvals_and_the_old_session(tmp_path, canon, skills):
    approve = Approver(lambda t, d: None)
    approve.always.add("Bash")
    approve.draft = {"name": "x"}
    approve.reset()
    assert approve.always == set() and approve.draft is None
    a = agent.Agent(tmp_path, canon=canon, skills=skills)
    a._resume, a.session_id = "old-session", "old-session"
    asyncio.run(a.reset())
    assert a._resume is None and a.options().resume is None


def test_ctrl_c_handler_survives_an_approval_prompt(monkeypatch):
    from ds_next import ui

    class FakeSession:
        def __init__(self, *a, **k):
            self.app = types.SimpleNamespace()        # resize_safe hangs its handler on this

        async def prompt_async(self, *a, **k):
            asyncio.get_running_loop().remove_signal_handler(signal.SIGINT)   # what a prompt may do
            return "y"

    monkeypatch.setattr(ui, "PromptSession", FakeSession)
    repl = object.__new__(ui.Repl)
    repl._status, repl.console = None, ui.Console(file=open(os.devnull, "w"))  # noqa: SIM115

    async def go():
        fired = []
        repl._sigint = lambda: fired.append(1)
        asyncio.get_running_loop().add_signal_handler(signal.SIGINT, repl._sigint)
        await repl._prompt_approval("Bash", "ls")
        os.kill(os.getpid(), signal.SIGINT)
        await asyncio.sleep(0.05)
        asyncio.get_running_loop().remove_signal_handler(signal.SIGINT)
        return fired

    assert asyncio.run(go()) == [1]


# -- captures never overwrite

def test_captures_never_overwrite(tmp_path, canon, skills):
    tools = agent.tools(canon, skills, tmp_path)
    call(tools, "capture", {"title": "Orders land late", "body": "first"})
    call(tools, "capture", {"title": "Orders land late", "body": "second"})
    folder = tmp_path / ".ds" / "captures"
    assert "first" in (folder / "orders-land-late.md").read_text()
    assert "second" in (folder / "orders-land-late-2.md").read_text()


# -- errors through the SDK's real MCP dispatch

def test_errors_survive_mcp_dispatch(tmp_path, canon, skills):
    server = create_sdk_mcp_server("ds", tools=agent.tools(canon, skills, tmp_path))["instance"]
    handler = server.request_handlers[CallToolRequest]
    req = CallToolRequest(method="tools/call", params=CallToolRequestParams(name="canon_read", arguments={"id": "nope"}))
    result = asyncio.run(handler(req))
    assert result.root.content[0].text.startswith("ERROR:")    # readable even though the flag is lost


# -- second Codex review, 2026-10-16

def test_ancestor_symlinks_are_refused(tmp_path, canon, skills):
    other = tmp_path / "other-repo"
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    repo = tmp_path / "demo-cli"
    repo.mkdir()
    (repo / ".git").symlink_to(other / ".git")              # would redirect the hook write
    with pytest.raises(ValueError, match=".git is a symbolic link"):
        scaffold.write(scaffold.Answers(**ANSWERS), repo, canon, skills)
    assert not (other / ".git" / "hooks" / "pre-push").exists()
    outside = tmp_path / "outside"
    outside.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    (work / ".ds").symlink_to(outside)                      # would redirect captures
    text, err = call(agent.tools(canon, skills, work), "capture", {"title": "t", "body": "b"})
    assert err and "symbolic link" in text and not list(outside.rglob("*.md"))


def test_hook_fallback_path_is_never_executed_as_shell(tmp_path, monkeypatch):
    marker = tmp_path / "pwned"
    evil_dir = tmp_path / "$(touch pwned)"         # runs in tmp_path if the hook ever evaluates it
    evil_dir.mkdir()
    exe = evil_dir / "ds-next"
    exe.write_text("#!/bin/sh\necho ran-fallback\n")
    exe.chmod(0o755)
    monkeypatch.setattr(sys, "argv", [str(exe)])
    monkeypatch.setattr(scaffold.shutil, "which", lambda _: None)
    hook = tmp_path / "pre-push"
    hook.write_text(scaffold._hook_text())
    r = subprocess.run(["sh", str(hook)], cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, capture_output=True,
                       text=True, check=False)
    assert not marker.exists() and "ran-fallback" in r.stdout


def test_placeholders_in_user_text_stay_literal(canon, skills):
    files = scaffold.render(scaffold.Answers(**{**ANSWERS, "purpose": "{{test_cmd}} and {{name}}"},
                                             test_cmd='"; injected = True; "'), canon, skills)
    init = files["src/demo_cli/__init__.py"]
    assert init.startswith('"""{{test_cmd}} and {{name}}"""')    # the fixture template uses raw {{purpose}}
    assert "injected" not in init
    tomllib.loads(files["pyproject.toml"])


@pytest.mark.parametrize("entry, expected", [
    ('status = "declined"\nversion = 1\nby = "ck"\nreason = "r"\nrevisit = 2027-01-01T00:00:00Z\n',
     "revisit must be a date"),
    ('status = "declined"\nversion = 1\nby = "ck"\nreason = "   "\nrevisit = 2027-01-01\n', "needs reason"),
    ('status = "adopted"\nversion = 1\nby = 42\non = 2026-10-16\n', "by must name who decided"),
    ('status = "adopted"\nversion = 999\nby = "ck"\non = 2026-10-16\n', "the canon only has v1"),
])
def test_manifest_decisions_are_validated(tmp_path, canon, entry, expected):
    (tmp_path / ".ds").mkdir()
    (tmp_path / ".ds" / "manifest.toml").write_text(
        f'[repo]\nname = "x"\ntags = ["python"]\n[standards.testing]\n{entry}')
    r = reconcile.check(tmp_path, canon)
    assert not r.ok and any(expected in e for e in r.errors), r.errors


def test_hooks_path_outside_the_repo_is_reported(tmp_path, canon, skills):
    repo = tmp_path / "demo-cli"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    elsewhere = tmp_path / "global-hooks"
    elsewhere.mkdir()
    subprocess.run(["git", "-C", str(repo), "config", "core.hooksPath", str(elsewhere)], check=True)
    with pytest.raises(scaffold.ScaffoldError, match="hook is not installed.*core.hooksPath"):
        scaffold.write(scaffold.Answers(**ANSWERS), repo, canon, skills)
    assert not (elsewhere / "pre-push").exists()
    assert subprocess.run(["git", "-C", str(repo), "log", "--oneline"], capture_output=True, text=True,
                          check=True).stdout.strip()                 # the repo itself was still committed


def test_repeated_captures_get_distinct_canon_ids(tmp_path, canon, skills):
    tools = agent.tools(canon, skills, tmp_path)
    call(tools, "capture", {"title": "Same", "body": "one"})
    call(tools, "capture", {"title": "Same", "body": "two"})
    folder = tmp_path / ".ds" / "captures"
    ids = {f.stem: f.read_text().split("\n")[1] for f in folder.glob("*.md")}
    assert ids == {"same": "id: same", "same-2": "id: same-2"}


def test_docs_keep_an_older_pin_visible(tmp_path):
    from ds_next.docs import _link_pointers
    newer = make_canon(tmp_path / "c", bump={"testing": 2})
    out = _link_pointers("We follow [[testing@1]] and [[testing]].", newer, "")
    assert "(pinned v1; the canon is now v2)" in out and out.count("standards/testing.md") == 2


# -- third Codex review, 2026-10-16

def test_nested_hooks_path_inside_git_is_created(tmp_path, canon, skills):
    repo = tmp_path / "demo-cli"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "core.hooksPath", ".git/new/subdir"], check=True)
    scaffold.write(scaffold.Answers(**ANSWERS), repo, canon, skills)
    assert (repo / ".git" / "new" / "subdir" / "pre-push").stat().st_mode & 0o111


def test_toolbar_survives_markup_in_names(tmp_path):
    from prompt_toolkit.formatted_text import to_formatted_text

    from ds_next import ui
    repl = object.__new__(ui.Repl)
    repl.cwd, repl._where, repl.state = tmp_path / "R&D <team>", "x & y", {}
    repl.agent = type("A", (), {"model": None, "effort": "low", "connected": False})()
    text = "".join(t for _, t, *_ in to_formatted_text(repl._toolbar()))
    assert "R&D <team>" in text and "x & y" in text


def test_owner_is_required():
    with pytest.raises(ValueError, match="owner"):
        scaffold.Answers(**{**ANSWERS, "owner": "  "})


@pytest.mark.parametrize("doc", [
    "~~~\n[[not-a-standard]]\n~~~\n",
    "````md\n```\n[[not-a-standard]]\n```\n````\n",
    "``[[not-a-standard]]`` inline\n",
])
def test_pointer_examples_in_code_are_not_claims(canon, doc):
    assert canon.pointer_problems(doc + "Real: [[nope]]\n") == ["[[nope]] is not in the canon"]


def test_a_decline_reason_must_be_text(tmp_path, canon):
    (tmp_path / ".ds").mkdir()
    (tmp_path / ".ds" / "manifest.toml").write_text(
        '[repo]\nname = "x"\ntags = ["python"]\n[standards.testing]\nstatus = "declined"\nversion = 1\n'
        'by = "ck"\nreason = 2026-10-16\nrevisit = 2027-01-01\n')
    r = reconcile.check(tmp_path, canon)
    assert not r.ok and any("needs reason" in e for e in r.errors), r.errors


# -- fourth Codex review, 2026-10-16

def test_an_existing_hook_is_kept_and_runs_first(tmp_path, canon, skills):
    repo = tmp_path / "demo-cli"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    theirs = repo / ".git" / "hooks" / "pre-push"
    theirs.write_text("#!/bin/sh\necho their-check-ran\nexit 3\n")
    theirs.chmod(0o755)
    scaffold.write(scaffold.Answers(**ANSWERS), repo, canon, skills)
    assert "their-check-ran" in (repo / ".git" / "hooks" / "pre-push.local").read_text()
    r = subprocess.run(["sh", str(theirs)], cwd=repo, capture_output=True, text=True, check=False)
    assert "their-check-ran" in r.stdout and r.returncode == 3        # their verdict still stops the push
    assert scaffold.install_hook(repo) is None                         # reinstalling ours is idempotent
    assert "their-check-ran" in (repo / ".git" / "hooks" / "pre-push.local").read_text()


def test_a_newer_version_reopens_a_decline(tmp_path, canon, skills):
    a = scaffold.Answers(**ANSWERS, declines={"testing": "covered upstream"})
    scaffold.write(a, tmp_path / a.name, canon, skills, git=False)
    assert "testing" in reconcile.check(tmp_path / a.name, canon).declined
    newer = make_canon(tmp_path / "c2", bump={"testing": 2})
    r = reconcile.check(tmp_path / a.name, newer)
    assert r.ok and "testing" not in r.declined
    assert r.pending == ["testing v2 (declined at v1)"]


# -- fifth Codex review, 2026-10-16

def test_docs_stage_every_linked_page(tmp_path, canon, skills):
    from ds_next import docs
    scaffold.write(scaffold.Answers(**ANSWERS), tmp_path / "demo-cli", canon, skills, git=False)
    repo = tmp_path / "demo-cli"
    (repo / "README.md").write_text("# demo\n\nSee [the runbook](docs/runbook.md) and [agents](AGENTS.md).\n")
    (repo / "docs").mkdir()
    (repo / "docs" / "runbook.md").write_text("# Runbook\n\nBack to [home](../README.md). Follows [[testing]].\n")
    content, _ = docs.stage(tmp_path / "stage", canon, skills, repo)
    assert (content / "docs" / "runbook.md").is_file() and (content / "AGENTS.md").is_file()
    runbook = (content / "docs" / "runbook.md").read_text()
    assert "](../index.md)" in runbook and "](../standards/testing.md)" in runbook
    for page in content.rglob("*.md"):                      # every relative link lands on a staged page
        for target in re.findall(r"\]\(([^)#:]+\.md)\)", page.read_text()):
            assert (page.parent / target).resolve().is_file(), (page, target)


@pytest.mark.skipif(not (Path.home() / "Developer" / "docs-ds" / "node_modules").is_dir(), reason="needs docs-ds")
def test_docs_build_has_no_broken_links(tmp_path, canon, skills):
    from ds_next import docs
    scaffold.write(scaffold.Answers(**ANSWERS), tmp_path / "demo-cli", canon, skills, git=False)
    repo = tmp_path / "demo-cli"
    (repo / "README.md").write_text("# demo\n\nSee [the runbook](docs/runbook.md).\n")
    (repo / "docs").mkdir()
    (repo / "docs" / "runbook.md").write_text("# Runbook\n\nBack to [home](../README.md).\n")
    content, title = docs.stage(tmp_path / "stage", canon, skills, repo)
    r = docs.build(content, title, tmp_path / "site")
    assert r.returncode == 0, r.stderr[-2000:]
    assert "broken link" not in (r.stdout + r.stderr).lower(), (r.stdout + r.stderr)[-2000:]
    assert (tmp_path / "site" / "docs" / "runbook" / "index.html").is_file()


# -- sixth Codex review, 2026-10-16

def test_only_links_to_the_root_readme_are_redirected(tmp_path, canon, skills):
    from ds_next import docs
    scaffold.write(scaffold.Answers(**ANSWERS), tmp_path / "demo-cli", canon, skills, git=False)
    repo = tmp_path / "demo-cli"
    (repo / "docs").mkdir()
    (repo / "docs" / "README.md").write_text("# Docs index\n\nUp to [home](../README.md).\n")
    (repo / "docs" / "runbook.md").write_text("# Runbook\n\n[Docs index](README.md), [home](../README.md#run).\n")
    content, _ = docs.stage(tmp_path / "stage", canon, skills, repo)
    runbook = (content / "docs" / "runbook.md").read_text()
    assert "[Docs index](README.md)" in runbook and "[home](../index.md#run)" in runbook
    assert "[home](../index.md)" in (content / "docs" / "README.md").read_text()
    for page in content.rglob("*.md"):
        for target in re.findall(r"\]\(([^)#:]+\.md)(?:#[^)]*)?\)", page.read_text()):
            assert (page.parent / target).resolve().is_file(), (page, target)


# -- seventh Codex review, 2026-10-16

@pytest.mark.skipif(not (Path.home() / "Developer" / "docs-ds" / "node_modules").is_dir(), reason="needs docs-ds")
def test_docs_never_build_over_a_repo_or_other_files(tmp_path, canon, skills, monkeypatch):
    from ds_next import docs
    scaffold.write(scaffold.Answers(**ANSWERS), tmp_path / "demo-cli", canon, skills)
    repo = tmp_path / "demo-cli"
    ran = []                                    # stand in for Docusaurus, which empties --out-dir
    monkeypatch.setattr(docs.subprocess, "run", lambda *a, **k: ran.append(a) or subprocess.CompletedProcess(a, 0))
    monkeypatch.chdir(repo)
    content, title = docs.stage(tmp_path / "stage", canon, skills, repo)
    for bad in (repo, tmp_path, repo / "src", Path.home()):      # the repo, a parent of it, a non-site dir
        with pytest.raises(ValueError, match="refusing to build"):
            docs.build(content, title, bad, protect=[repo])
    assert ran == [] and (repo / ".git").is_dir() and (repo / "README.md").is_file()
    fresh = tmp_path / "site"
    docs.build(content, title, fresh, protect=[repo])             # a new directory is fine
    assert ran and (fresh / docs.SITE_MARKER).is_file()
    docs.build(content, title, fresh, protect=[repo])             # and so is rebuilding a ds-next site


# -- eighth Codex review, 2026-10-16

def test_docs_copy_linked_images_and_keep_both_homepages(tmp_path, canon, skills):
    from ds_next import docs
    scaffold.write(scaffold.Answers(**ANSWERS), tmp_path / "demo-cli", canon, skills, git=False)
    repo = tmp_path / "demo-cli"
    (repo / "docs" / "assets").mkdir(parents=True)
    (repo / "docs" / "assets" / "diagram.svg").write_text("<svg/>")
    (repo / "docs" / "guide.md").write_text("# Guide\n\n![diagram](assets/diagram.svg) [index](../index.md)\n")
    (repo / "index.md").write_text("# Repo index page\n\nKeep me. Home is [here](README.md).\n")
    content, _ = docs.stage(tmp_path / "stage", canon, skills, repo)
    assert (content / "docs" / "assets" / "diagram.svg").read_text() == "<svg/>"
    assert "Keep me" in (content / "repo-index.md").read_text()
    assert "Keep me" not in (content / "index.md").read_text()          # the README is still home
    assert "[index](../repo-index.md)" in (content / "docs" / "guide.md").read_text()
    assert "[here](index.md)" in (content / "repo-index.md").read_text()


# -- ninth Codex review, 2026-10-16

def test_a_typed_snowflake_tag_survives_a_blank_schema(tmp_path, canon, skills):
    from ds_next.ui import extra_tags
    tags = extra_tags("snowflake, python, Snowflake", ("python", "package", "cli"))
    assert tags == ["snowflake"]
    a = scaffold.Answers(**ANSWERS, tags=tags).resolve(canon)
    assert "snowflake" in a.tags and a.snowflake == ""
    files = scaffold.render(scaffold.Answers(**ANSWERS, tags=tags), canon, skills)
    assert "snowflake" in tomllib.loads(files[".ds/manifest.toml"])["repo"]["tags"]
