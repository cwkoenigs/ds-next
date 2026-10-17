"""Hidden acceptance tests for the `mcheck` console command."""

import json
import os
import subprocess

import pytest

TARGET_BIN = os.environ.get("TARGET_BIN")

pytestmark = pytest.mark.skipif(not TARGET_BIN, reason="TARGET_BIN not set")

DEFAULT_INDEX = {
    "standards": [
        {"id": "alpha", "version": 3},
        {"id": "beta", "version": 1},
        {"id": "gamma", "version": 2},
    ]
}

FULL_MANIFEST = """
[adopted.alpha]
version = 3
date = 2026-01-15

[adopted.beta]
version = 1
date = 2025-06-01

[declined.gamma]
version = 2
reason = "Not applicable to our stack"
revisit = 2027-01-01
"""


def write_index(tmp_path, data=None, name="index.json"):
    p = tmp_path / name
    p.write_text(json.dumps(DEFAULT_INDEX if data is None else data))
    return p


def write_manifest(tmp_path, text, name="manifest.toml"):
    p = tmp_path / name
    p.write_text(text)
    return p


def run(tmp_path, manifest, index, docs=None):
    args = [TARGET_BIN, str(manifest), "--index", str(index)]
    if docs is not None:
        args += ["--docs", str(docs)]
    return subprocess.run(
        args,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )


def report_lines(result):
    return [
        line
        for line in result.stdout.splitlines()
        if line.startswith("ERROR ") or line.startswith("PENDING ")
    ]


def lines_for(result, kind, ident):
    prefix = f"{kind} {ident}:"
    return [line for line in report_lines(result) if line.startswith(prefix)]


def assert_no_traceback(result):
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout


# --- clean / exit codes -----------------------------------------------------


def test_clean_manifest_exits_zero_with_no_report(tmp_path):
    m = write_manifest(tmp_path, FULL_MANIFEST)
    i = write_index(tmp_path)
    r = run(tmp_path, m, i)
    assert r.returncode == 0, r.stdout + r.stderr
    assert report_lines(r) == []


def test_adopted_older_version_is_pending_exit_one(tmp_path):
    m = write_manifest(
        tmp_path, FULL_MANIFEST.replace("version = 3\ndate", "version = 2\ndate")
    )
    i = write_index(tmp_path)
    r = run(tmp_path, m, i)
    assert r.returncode == 1, r.stdout + r.stderr
    assert len(lines_for(r, "PENDING", "alpha")) == 1
    assert not any(line.startswith("ERROR ") for line in report_lines(r))


def test_declined_older_version_is_pending(tmp_path):
    m = write_manifest(
        tmp_path,
        FULL_MANIFEST.replace("[declined.gamma]\nversion = 2", "[declined.gamma]\nversion = 1"),
    )
    i = write_index(tmp_path)
    r = run(tmp_path, m, i)
    assert r.returncode == 1, r.stdout + r.stderr
    assert len(lines_for(r, "PENDING", "gamma")) == 1
    assert len(report_lines(r)) == 1


def test_unmentioned_standard_is_pending(tmp_path):
    index = {"standards": DEFAULT_INDEX["standards"] + [{"id": "delta", "version": 1}]}
    m = write_manifest(tmp_path, FULL_MANIFEST)
    i = write_index(tmp_path, index)
    r = run(tmp_path, m, i)
    assert r.returncode == 1, r.stdout + r.stderr
    assert len(lines_for(r, "PENDING", "delta")) == 1
    assert len(report_lines(r)) == 1


# --- manifest errors --------------------------------------------------------


def test_unknown_id_in_manifest_is_error(tmp_path):
    m = write_manifest(
        tmp_path,
        FULL_MANIFEST + '\n[adopted.zeta]\nversion = 1\ndate = 2026-02-02\n',
    )
    i = write_index(tmp_path)
    r = run(tmp_path, m, i)
    assert r.returncode == 2, r.stdout + r.stderr
    assert len(lines_for(r, "ERROR", "zeta")) >= 1


@pytest.mark.parametrize("bad_version", [4, 0, -1])
def test_version_that_never_existed_is_error(tmp_path, bad_version):
    m = write_manifest(
        tmp_path,
        FULL_MANIFEST.replace("version = 3\ndate", f"version = {bad_version}\ndate"),
    )
    i = write_index(tmp_path)
    r = run(tmp_path, m, i)
    assert r.returncode == 2, r.stdout + r.stderr
    assert len(lines_for(r, "ERROR", "alpha")) >= 1


def test_declined_version_that_never_existed_is_error(tmp_path):
    m = write_manifest(
        tmp_path,
        FULL_MANIFEST.replace("[declined.gamma]\nversion = 2", "[declined.gamma]\nversion = 9"),
    )
    i = write_index(tmp_path)
    r = run(tmp_path, m, i)
    assert r.returncode == 2, r.stdout + r.stderr
    assert len(lines_for(r, "ERROR", "gamma")) >= 1


@pytest.mark.parametrize(
    "replacement",
    [
        "[adopted.alpha]\ndate = 2026-01-15",  # missing version
        "[adopted.alpha]\nversion = 3",  # missing date
        '[adopted.alpha]\nversion = "3"\ndate = 2026-01-15',  # version as string
        "[adopted.alpha]\nversion = true\ndate = 2026-01-15",  # bool is not an int
        "[adopted.alpha]\nversion = 3.0\ndate = 2026-01-15",  # float
    ],
)
def test_bad_or_missing_adopted_field_is_error(tmp_path, replacement):
    text = FULL_MANIFEST.replace(
        "[adopted.alpha]\nversion = 3\ndate = 2026-01-15", replacement
    )
    assert text != FULL_MANIFEST
    m = write_manifest(tmp_path, text)
    i = write_index(tmp_path)
    r = run(tmp_path, m, i)
    assert_no_traceback(r)
    assert r.returncode == 2, r.stdout + r.stderr
    assert len(lines_for(r, "ERROR", "alpha")) >= 1


@pytest.mark.parametrize("drop", ["reason", "revisit", "version"])
def test_missing_declined_field_is_error(tmp_path, drop):
    lines = [
        "[declined.gamma]",
        "version = 2",
        'reason = "Not applicable to our stack"',
        "revisit = 2027-01-01",
    ]
    original = "\n".join(lines)
    kept = "\n".join(line for line in lines if not line.startswith(drop + " "))
    text = FULL_MANIFEST.replace(original, kept)
    assert text != FULL_MANIFEST
    m = write_manifest(tmp_path, text)
    i = write_index(tmp_path)
    r = run(tmp_path, m, i)
    assert_no_traceback(r)
    assert r.returncode == 2, r.stdout + r.stderr
    assert len(lines_for(r, "ERROR", "gamma")) >= 1


def test_error_and_pending_together_exit_two_and_sorted(tmp_path):
    index = {
        "standards": DEFAULT_INDEX["standards"]
        + [{"id": "delta", "version": 1}, {"id": "aardvark", "version": 1}]
    }
    text = (
        FULL_MANIFEST.replace("version = 3\ndate", "version = 2\ndate")
        + '\n[adopted.zeta]\nversion = 1\ndate = 2026-02-02\n'
        + '\n[adopted.bogus]\nversion = 1\ndate = 2026-02-02\n'
    )
    m = write_manifest(tmp_path, text)
    i = write_index(tmp_path, index)
    r = run(tmp_path, m, i)
    assert r.returncode == 2, r.stdout + r.stderr
    lines = report_lines(r)
    assert lines == sorted(lines)
    assert lines_for(r, "ERROR", "zeta")
    assert lines_for(r, "ERROR", "bogus")
    assert lines_for(r, "PENDING", "alpha")
    assert lines_for(r, "PENDING", "delta")
    assert lines_for(r, "PENDING", "aardvark")


# --- unreadable inputs ------------------------------------------------------


def test_missing_manifest_file_reports_manifest_error(tmp_path):
    i = write_index(tmp_path)
    r = run(tmp_path, tmp_path / "does-not-exist.toml", i)
    assert_no_traceback(r)
    assert r.returncode == 2, r.stdout + r.stderr
    assert lines_for(r, "ERROR", "manifest")


def test_malformed_toml_reports_manifest_error(tmp_path):
    m = write_manifest(tmp_path, "[adopted.alpha\nversion = = 3\n")
    i = write_index(tmp_path)
    r = run(tmp_path, m, i)
    assert_no_traceback(r)
    assert r.returncode == 2, r.stdout + r.stderr
    assert lines_for(r, "ERROR", "manifest")


@pytest.mark.parametrize("content", ["{not json", None])
def test_unreadable_index_reports_index_error(tmp_path, content):
    m = write_manifest(tmp_path, FULL_MANIFEST)
    i = tmp_path / "index.json"
    if content is not None:
        i.write_text(content)
    r = run(tmp_path, m, i)
    assert_no_traceback(r)
    assert r.returncode == 2, r.stdout + r.stderr
    assert lines_for(r, "ERROR", "index")


# --- docs pointers ----------------------------------------------------------


def test_docs_valid_pointers_are_clean(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text(
        "See [[alpha]] and [[alpha@1]] and [[alpha@3]] and [[gamma@2]].\n"
    )
    m = write_manifest(tmp_path, FULL_MANIFEST)
    i = write_index(tmp_path)
    r = run(tmp_path, m, i, docs=docs)
    assert r.returncode == 0, r.stdout + r.stderr
    assert report_lines(r) == []


def test_docs_unknown_id_and_bad_version_reported(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text(
        "Intro [[alpha]].\nBroken [[nosuch]] here.\nFuture [[alpha@4]] too.\n"
    )
    m = write_manifest(tmp_path, FULL_MANIFEST)
    i = write_index(tmp_path)
    r = run(tmp_path, m, i, docs=docs)
    assert r.returncode == 2, r.stdout + r.stderr
    errors = [line for line in report_lines(r) if line.startswith("ERROR ")]
    assert any("guide.md" in e and "[[nosuch]]" in e for e in errors)
    assert any("guide.md" in e and "[[alpha@4]]" in e for e in errors)
    assert not any("[[alpha]]" in e for e in errors)
    lines = report_lines(r)
    assert lines == sorted(lines)


def test_docs_nested_md_found_and_non_md_ignored(tmp_path):
    docs = tmp_path / "docs"
    (docs / "sub" / "deeper").mkdir(parents=True)
    (docs / "sub" / "deeper" / "nested.md").write_text("Link [[ghost@1]].\n")
    (docs / "notes.txt").write_text("Ignore [[phantom]].\n")
    m = write_manifest(tmp_path, FULL_MANIFEST)
    i = write_index(tmp_path)
    r = run(tmp_path, m, i, docs=docs)
    assert r.returncode == 2, r.stdout + r.stderr
    errors = [line for line in report_lines(r) if line.startswith("ERROR ")]
    assert any("nested.md" in e and "[[ghost@1]]" in e for e in errors)
    assert not any("phantom" in e for e in r.stdout.splitlines())


def test_docs_not_checked_without_flag(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("Broken [[nosuch]].\n")
    m = write_manifest(tmp_path, FULL_MANIFEST)
    i = write_index(tmp_path)
    r = run(tmp_path, m, i)
    assert r.returncode == 0, r.stdout + r.stderr
    assert report_lines(r) == []


def test_docs_pending_combined_with_doc_error_exit_two(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("[[beta@2]]\n")
    m = write_manifest(
        tmp_path, FULL_MANIFEST.replace("version = 3\ndate", "version = 2\ndate")
    )
    i = write_index(tmp_path)
    r = run(tmp_path, m, i, docs=docs)
    assert r.returncode == 2, r.stdout + r.stderr
    assert lines_for(r, "PENDING", "alpha")
    errors = [line for line in report_lines(r) if line.startswith("ERROR ")]
    assert any("a.md" in e and "[[beta@2]]" in e for e in errors)
