"""The cross-repo graph (canon adr-002) as ds-next reads it: the repo_graph tool, the graph in
project_status, [uses] checked by reconcile, and the canon fast-forward before `mcp` serves."""
import asyncio
import json
import os
import subprocess
from pathlib import Path

from ds_next import agent, cli, reconcile


def call(tools, name, args):
    t = next(t for t in tools if t.name == name)
    out = asyncio.run(t.handler(args))
    return out["content"][0]["text"], out.get("is_error", False)

SECTION = {
    "generated": "2026-10-30", "built_by": "local",
    "repos": [
        {"name": "demo-cli", "path": "team/demo-cli", "commit": "abc1234", "manifest": True, "tags": ["python"],
         "provides": {"commands": ["demo serve [--port N]"]}, "uses": {"lib": ["lib build"]}},
        {"name": "lib", "path": "team/lib", "commit": "def5678", "manifest": True, "tags": ["python"],
         "provides": {"commands": ["lib build", "lib fly"]}, "uses": {}},
        {"name": "quiet", "path": "team/quiet", "commit": "0000000", "manifest": False, "tags": [],
         "provides": {}, "uses": {}},
    ],
    "edges": [
        {"from": "demo-cli", "to": "lib", "what": "lib build", "declared": True, "mentioned": True, "count": 2,
         "where": ["Makefile:3", "README.md:9"]},
        {"from": "quiet", "to": "demo-cli", "what": "demo serve [--port N]", "declared": False, "mentioned": True,
         "count": 1, "where": ["run.sh:1"]},
    ],
    "report": {"unused": [{"repo": "lib", "what": "lib fly"}],
               "undeclared": [{"from": "quiet", "to": "demo-cli", "what": "demo serve [--port N]", "count": 1,
                               "where": ["run.sh:1"]}],
               "unresolved": [], "unscanned": [], "unreadable": [], "silent": ["quiet"]},
}


def with_graph(canon, section=SECTION):
    p = canon.root / "index.json"
    d = json.loads(p.read_text())
    d["repos"] = section
    p.write_text(json.dumps(d))
    return canon


def manifest(root: Path, name: str, extra: str = "") -> Path:
    (root / ".ds").mkdir(parents=True, exist_ok=True)
    (root / ".ds" / "manifest.toml").write_text(f'[repo]\nname = "{name}"\ntags = ["python"]\n{extra}')
    return root


def test_canon_reads_the_section(canon):
    assert canon.repos == {} and canon.repo_graph("lib") is None
    with_graph(canon)
    g = canon.repo_graph("lib")
    assert g["commit"] == "def5678" and g["unused"] == ["lib fly"]
    assert [e["from"] for e in g["used_by"]] == ["demo-cli"]
    assert canon.repo_graph("demo-cli")["undeclared"] == [] and canon.repo_graph("quiet")["undeclared"][0]["to"] == "demo-cli"
    assert canon.repo_graph("nope") is None


def test_repo_graph_tool(tmp_path, canon, skills):
    tools = agent.tools(canon, skills, tmp_path)
    text, _ = call(tools, "repo_graph", {"repo": "lib"})
    assert "no repos section yet" in text                             # before the pipeline has run
    with_graph(canon)
    text, _ = call(tools, "repo_graph", {"repo": "lib"})
    assert text.splitlines()[0] == "lib @ def5678 (graph compiled 2026-10-30)"
    assert "provides: commands: lib build, lib fly" in text
    assert "  demo-cli: lib build  [declared, mentioned 2x]  Makefile:3, README.md:9" in text
    assert "unused: provides lib fly, used by nobody" in text
    text, _ = call(tools, "repo_graph", {"repo": "quiet"})
    assert "provides: nothing declared" in text
    assert "undeclared: mentions demo-cli: demo serve [--port N]  [undeclared, mentioned 1x]  run.sh:1" in text
    text, _ = call(tools, "repo_graph", {"what": "serve"})
    assert text.splitlines() == ["provided by: demo-cli (demo serve [--port N])",
                                 "  quiet -> demo-cli: demo serve [--port N]  [undeclared, mentioned 1x]  run.sh:1"]
    text, _ = call(tools, "repo_graph", {"what": "nothing-like-this"})
    assert text.startswith("nothing in the graph provides or uses")
    text, _ = call(tools, "repo_graph", {})                           # cwd is not a ds repo
    assert "not a ds repo" in text and "demo-cli, lib, quiet" in text
    text, _ = call(tools, "repo_graph", {"repo": "nope"})
    assert "not in the canon's registry" in text and "registered: demo-cli, lib, quiet" in text
    assert "mcp__ds__repo_graph" in agent.READ_ONLY_IDS


def test_project_status_carries_the_graph_and_uses(tmp_path, canon, skills):
    repo = manifest(tmp_path / "demo-cli", "demo-cli", '\n[uses]\nlib = ["lib build"]\n')
    tools = agent.tools(canon, skills, repo)
    status = json.loads(call(tools, "project_status", {})[0])
    assert "no repos section yet" in status["graph"]
    with_graph(canon)
    status = json.loads(call(tools, "project_status", {})[0])
    assert status["graph"]["used_by"][0]["from"] == "quiet" and status["notes"] == [] and status["errors"] == []
    text, _ = call(tools, "repo_graph", {})                           # no args: the repo at cwd
    assert text.startswith("demo-cli @ abc1234")


def test_reconcile_checks_uses(tmp_path, canon):
    with_graph(canon)
    rep = reconcile.check(manifest(tmp_path / "a", "a", '\n[uses]\nlib = ["lib build", "lib fly [--fast]"]\n'), canon)
    assert rep.ok and rep.notes == []                                # text match, and match by scan literal
    rep = reconcile.check(manifest(tmp_path / "b", "b", '\n[uses]\nlib = ["lib swim"]\n'), canon)
    assert rep.errors == ["[uses] lib: lib swim is not among what lib provides (lib build, lib fly)"]
    rep = reconcile.check(manifest(tmp_path / "c", "c", '\n[uses]\nnolib = ["x"]\n'), canon)
    assert rep.errors == ["[uses] names nolib, which the canon's registry does not have"]
    rep = reconcile.check(manifest(tmp_path / "d", "d", '\n[uses]\nquiet = ["quiet run"]\n'), canon)
    assert rep.ok and rep.notes == ["uses quiet: quiet run (quiet declares nothing yet)"]
    rep = reconcile.check(manifest(tmp_path / "e", "e", '\n[uses]\nlib = "lib build"\n'), canon)
    assert rep.errors == ['[uses] must hold lists of strings, like commands = ["ds-next mcp"]']
    rep = reconcile.check(manifest(tmp_path / "f", "f", '\n[provides]\ncommands = []\n'), canon)
    assert rep.errors == ['[provides] must hold lists of strings, like commands = ["ds-next mcp"]']


def test_reconcile_without_the_section_checks_shapes_only(tmp_path, canon):
    rep = reconcile.check(manifest(tmp_path / "a", "a", '\n[uses]\nnolib = ["x"]\n'), canon)
    assert rep.ok and rep.notes == []


def test_repo_name(tmp_path):
    assert reconcile.repo_name(manifest(tmp_path / "dir", "named")) == "named"
    (tmp_path / "bare").mkdir()
    assert reconcile.repo_name(tmp_path / "bare") == "bare"


GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_CONFIG_GLOBAL": "/dev/null"}


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**GIT_ENV, "PATH": os.environ["PATH"]}).stdout.strip()


def test_refresh_canon_fast_forwards(tmp_path, monkeypatch):
    monkeypatch.delenv("DS_CANON_PULL", raising=False)
    origin = tmp_path / "origin.git"
    git("init", "-q", "--bare", str(origin), cwd=tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        git("clone", "-q", str(origin), str(d), cwd=tmp_path)
    (a / "index.json").write_text("{}")
    git("add", "index.json", cwd=a)
    git("commit", "-qm", "one", cwd=a)
    git("push", "-q", "-u", "origin", "HEAD", cwd=a)
    git("pull", "-q", cwd=b)
    (a / "index.json").write_text('{"repos": {}}')
    git("commit", "-qam", "two", cwd=a)
    git("push", "-q", cwd=a)
    assert cli.refresh_canon(b) == ""
    assert git("rev-parse", "HEAD", cwd=b) == git("rev-parse", "HEAD", cwd=a)
    assert (b / "index.json").read_text() == '{"repos": {}}'


def test_refresh_canon_says_why_not(tmp_path, monkeypatch):
    monkeypatch.delenv("DS_CANON_PULL", raising=False)
    plain = tmp_path / "plain"
    plain.mkdir()
    assert "not a git clone" in cli.refresh_canon(plain)
    lone = tmp_path / "lone"
    git("init", "-q", str(lone), cwd=tmp_path)
    note = cli.refresh_canon(lone)
    assert note.startswith("canon: not fast-forwarded (") and note.endswith("the index is as on disk")
    git("remote", "add", "origin", str(tmp_path / "gone.git"), cwd=lone)
    assert "not fast-forwarded" in cli.refresh_canon(lone)              # unreachable remote: a sentence, not a hang
    monkeypatch.setenv("DS_CANON_PULL", "0")
    assert cli.refresh_canon(lone) == ""
