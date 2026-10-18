"""The function-level code library: search, cut a module down to what is asked for, add it."""
import hashlib
import json
import subprocess
import sys
import tomllib

import pytest

from ds_next import code, reconcile, scaffold
from ds_next.kb import Canon

LIB = '''"""Lib."""
from __future__ import annotations

import json
import re
from pathlib import Path

SEP, END = "|", "\\n"
_WORD = re.compile(r"[a-z]+")


def _clean(s):
    return s.strip()


def to_literal(s: str) -> str:
    """Quote text as a JSON string literal. [[testing]]"""
    return json.dumps(_clean(s), ensure_ascii=False)


def words(s: str) -> list[str]:
    """Lowercase words in s, then the separator."""
    return _WORD.findall(s.lower()) + [SEP]


def where(p: str) -> Path:
    """A path."""
    return Path(p)
'''
TESTS = '''import json

from {{package}}.lib import to_literal, where, words


def helper(x):
    return words(x)


def test_literal():
    assert json.loads(to_literal(" a ")) == "a"


def test_words_via_helper():
    assert helper("Hi there") == ["hi", "there", "|"]


def test_where():
    assert where("x").name == "x"
'''


def sym(name, kind, sig, summary, needs, status="accepted", block="block-lib"):
    return {"id": f"{block}:{name}", "name": name, "block": block, "version": 2, "module": "lib", "status": status,
            "kind": kind, "signature": sig, "summary": summary, "needs": needs, "tests": [], "lessons": ["testing"],
            "tags": ["python"], "lines": 3, "hash": "x"}


@pytest.fixture
def lib_canon(canon):
    d = canon.root / "blocks" / "block-lib"
    (d / "code").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "BLOCK.md").write_text("---\nid: block-lib\n---\n\n# Lib\n\nText helpers.\n")
    (d / "code" / "lib.py").write_text(LIB)
    (d / "tests" / "test_lib.py").write_text(TESTS)
    digest = hashlib.sha256((d / "BLOCK.md").read_bytes())
    for rel in ("code/lib.py", "tests/test_lib.py"):
        digest.update(rel.encode() + (d / rel).read_bytes())
    data = json.loads((canon.root / "index.json").read_text())
    data["blocks"].append({"id": "block-lib", "version": 2, "title": "Text helpers", "module": "lib", "requires": [],
                           "test_requires": [], "tags": ["python"], "owner": "o", "status": "accepted",
                           "hash": digest.hexdigest()[:12], "dir": "blocks/block-lib", "tests": ["test_lib.py"]})
    data["code"] = [sym("to_literal", "function", "def to_literal(s: str) -> str", "Quote text as a JSON string literal.",
                        ["_clean"]),
                    sym("words", "function", "def words(s: str) -> list[str]", "Lowercase words in s.", ["SEP", "_WORD"]),
                    sym("where", "function", "def where(p: str) -> Path", "A path.", []),
                    sym("shout", "function", "def shout(s)", "Quote loudly.", [], status="retired", block="block-draft")]
    (canon.root / "index.json").write_text(json.dumps(data))
    return Canon(canon.root)


@pytest.fixture
def repo(tmp_path, lib_canon, skills):
    a = scaffold.Answers(name="demo-cli", purpose="A demo", owner="ck")
    scaffold.write(a, tmp_path / "demo-cli", lib_canon, skills, git=False)
    return tmp_path / "demo-cli"


def test_search_ranks_by_what_code_does_and_skips_unserved(lib_canon):
    hits = code.search(lib_canon, "quote text as a literal")
    assert hits[0]["id"] == "block-lib:to_literal"
    assert all(h["status"] != "retired" for h in hits)  # proposed is served; retired is not
    assert code.search(lib_canon, "the a of") == []


def test_shake_keeps_only_what_the_symbol_needs():
    out = code.shake(LIB, {"to_literal"})
    compile(out, "lib.py", "exec")
    assert "def _clean" in out and "import json" in out
    assert "import re" not in out and "Path" not in out and "def words" not in out


def test_shake_keeps_a_tuple_constant_whole():
    out = code.shake(LIB, {"words"})
    assert 'SEP, END = "|", "\\n"' in out and "_WORD = re.compile" in out and "import re" in out
    assert "json" not in out


def test_tests_follow_their_helpers_and_drop_what_was_not_taken():
    only_literal = code.shake_tests(TESTS.replace("{{package}}", "p"), "p.lib", {"to_literal", "_clean"})
    assert "def test_literal" in only_literal and "test_words" not in only_literal and "test_where" not in only_literal
    assert "from p.lib import to_literal\n" in only_literal
    with_words = code.shake_tests(TESTS.replace("{{package}}", "p"), "p.lib", {"words", "SEP", "_WORD"})
    assert "def helper" in with_words and "def test_words_via_helper" in with_words
    assert code.shake_tests(TESTS.replace("{{package}}", "p"), "p.lib", {"END"}) is None


def test_a_long_partial_import_is_wrapped_like_isort():
    src = ("from x import (alpha_long_name, beta_long_name, gamma_long_name, delta_long_name, epsilon_long_name,\n"
           "    zeta_long_name)\n\n\ndef f():\n    return (alpha_long_name, beta_long_name, gamma_long_name, delta_long_name,\n"
           "            epsilon_long_name)\n")
    out = code.shake(src, {"f"})
    assert max(len(ln) for ln in out.splitlines()) <= 100 and "zeta" not in out
    compile(out, "m.py", "exec")


def test_unusual_line_breaks_inside_strings_do_not_cut_a_function():
    src = 'def f():\n    s = "a b\x1cc"\n    return s\n\n\ndef g():\n    return 1\n'
    out = code.shake(src, {"f"})
    compile(out, "m.py", "exec")
    assert "return s" in out and "def g" not in out


def test_add_cuts_the_module_merges_later_adds_and_records_symbols(repo, lib_canon, tmp_path, monkeypatch):
    monkeypatch.setenv("DS_STATE", str(tmp_path / "state"))
    done = code.add(repo, ["block-lib:to_literal"], lib_canon, by="ck")
    lib = (repo / "src/demo_cli/lib.py").read_text()
    assert done[0]["note"] == "added" and "def to_literal" in lib and "def words" not in lib
    assert "from demo_cli.lib import to_literal\n" in (repo / "tests/test_lib.py").read_text()
    code.add(repo, ["block-lib:words"], lib_canon, by="ck")
    lib = (repo / "src/demo_cli/lib.py").read_text()
    assert "def to_literal" in lib and "def words" in lib and "def where" not in lib
    m = tomllib.loads((repo / ".ds/manifest.toml").read_text())
    assert m["blocks"]["block-lib"]["symbols"] == ["to_literal", "words"] and m["blocks"]["block-lib"]["version"] == 2
    assert reconcile.check(repo, lib_canon).ok
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_lib.py"],
                         cwd=repo, env={"PYTHONPATH": str(repo / "src")}, capture_output=True, text=True, check=False)
    assert run.returncode == 0 and "2 passed" in run.stdout, run.stdout
    log = [json.loads(ln) for ln in (tmp_path / "state" / "usage.jsonl").read_text().splitlines()]
    assert [e["ids"] for e in log] == [["block-lib:to_literal"], ["block-lib:words"]]


def test_add_leaves_a_whole_block_alone_and_refuses_bad_ids(repo, lib_canon):
    scaffold.add_block(repo, "block-lib", lib_canon, by="ck")
    assert code.add(repo, ["block-lib:words"], lib_canon)[0]["note"] == "the repo already has the whole block"
    with pytest.raises(ValueError, match="no code symbol"):
        code.add(repo, ["block-lib:nope"], lib_canon)
    with pytest.raises(ValueError, match="not served"):
        code.add(repo, ["block-draft:shout"], lib_canon)


def test_add_never_overwrites_a_file_it_did_not_write(repo, lib_canon):
    (repo / "src/demo_cli/lib.py").write_text("mine = 1\n")
    with pytest.raises(FileExistsError):
        code.add(repo, ["block-lib:where"], lib_canon)
    assert (repo / "src/demo_cli/lib.py").read_text() == "mine = 1\n"


def test_get_shows_one_symbol_with_its_needs_and_tests(lib_canon):
    text = code.get(lib_canon, "block-lib:to_literal")
    assert "def to_literal" in text and "def _clean" in text and "def words" not in text and "def test_literal" in text


def test_parse_ids_accepts_the_shapes_models_send():
    from ds_next.agent import parse_ids

    want = ["block-a:x", "block-b:y"]
    assert parse_ids("block-a:x, block-b:y") == want
    assert parse_ids('["block-a:x", "block-b:y"]') == want
    assert parse_ids(["block-a:x", "block-b:y"]) == want
    assert parse_ids("[block-a:x, block-b:y]") == want
    assert parse_ids("") == []


def test_proposed_code_is_served_and_labelled():
    from ds_next.code import SERVED, label

    assert SERVED == {"accepted", "proposed"}
    assert label("accepted") == ""
    assert "unreviewed" in label("proposed")
