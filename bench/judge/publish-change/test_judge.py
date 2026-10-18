"""Hidden acceptance tests for the `publish` change request (drafts warnings, --base-url)."""

import json
import os
import subprocess
import unicodedata
from pathlib import Path

import pytest

BIN = os.environ.get("TARGET_BIN", "publish")

INDEX = {"standards": [{"id": "std", "version": 2}, {"id": "other", "version": 1}]}
INDEX_WITH_NEW = {
    "standards": INDEX["standards"] + [{"id": "newer", "version": 1}],
}

MANIFEST = """\
[adopted.std]
version = 2
date = 2026-01-15

[adopted.other]
version = 1
date = 2026-02-01
"""

REPORT_PREFIXES = ("ERROR ", "PENDING ", "WARN ")


# ---------------------------------------------------------------- helpers


def make_repo(tmp_path, pages, manifest=MANIFEST, name="repo"):
    repo = tmp_path / name
    (repo / ".ds").mkdir(parents=True)
    (repo / ".ds" / "manifest.toml").write_text(manifest, encoding="utf-8")
    for rel, text in pages.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            p.write_bytes(text)
        else:
            p.write_text(text, encoding="utf-8")
    return repo


def setup(tmp_path, pages, index=INDEX, manifest=MANIFEST, name="repo"):
    repo = make_repo(tmp_path, pages, manifest=manifest, name=name)
    idx = tmp_path / "index.json"
    idx.write_text(json.dumps(index), encoding="utf-8")
    return repo, idx, tmp_path / "out"


def run(repo, idx, out, *extra):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [BIN, str(repo), "--index", str(idx), "--out", str(out), *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env=env,
    )


def report(res):
    """Report lines from whichever stream carries them (stdout preferred)."""
    for stream in (res.stdout, res.stderr):
        lines = [ln for ln in stream.splitlines() if ln.startswith(REPORT_PREFIXES)]
        if lines:
            return lines
    return []


def all_lines(res):
    return (res.stdout + "\n" + res.stderr).splitlines()


def warns(res):
    return [ln for ln in all_lines(res) if ln.startswith("WARN ")]


def errors(res):
    return [ln for ln in all_lines(res) if ln.startswith("ERROR ")]


def pendings(res):
    return [ln for ln in all_lines(res) if ln.startswith("PENDING ")]


def out_files(out):
    out = Path(out)
    if not out.exists():
        return []
    return sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())


def pub(out):
    return json.loads((Path(out) / "publish.json").read_text(encoding="utf-8"))


def read(out, rel):
    return (Path(out) / rel).read_text(encoding="utf-8")


def nfc(s):
    return unicodedata.normalize("NFC", s)


# ------------------------------------------------- drafts: warnings, not errors


@pytest.mark.parametrize(
    "path", ["drafts/x.md", "docs/drafts/x.md", "a/b/drafts/c/x.md"]
)
def test_draft_bad_pointer_is_warning_and_exit_zero(tmp_path, path):
    repo, idx, out = setup(tmp_path, {"a.md": "# A\n", path: "See [[nope]].\n"})
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    assert errors(res) == []
    w = warns(res)
    assert len(w) == 1
    assert w[0].startswith(f"WARN {path}: [[nope]]")
    assert (out / path).is_file()
    assert (out / "publish.json").is_file()


@pytest.mark.parametrize("pointer", ["[[nope]]", "[[nope@1]]", "[[std@99]]"])
def test_draft_bad_pointer_left_as_written(tmp_path, pointer):
    repo, idx, out = setup(tmp_path, {"drafts/x.md": f"Before {pointer} after.\n"})
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    text = read(out, "drafts/x.md")
    assert f"Before {pointer} after." in text
    assert "/standards/nope" not in text
    assert "/standards/std/v99" not in text
    w = warns(res)
    assert len(w) == 1 and w[0].startswith(f"WARN drafts/x.md: {pointer}")


def test_draft_bad_pointer_not_counted(tmp_path):
    repo, idx, out = setup(
        tmp_path, {"drafts/x.md": "Good [[std]] and bad [[std@99]] and [[nope]].\n"}
    )
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    pointers = pub(out)["pointers"]
    assert pointers.get("std", 0) == 1
    assert pointers.get("nope", 0) == 0


def test_draft_good_pointers_rewritten_and_counted(tmp_path):
    repo, idx, out = setup(tmp_path, {"docs/drafts/x.md": "A [[std]] B [[std@2]] C\n"})
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    assert warns(res) == []
    text = read(out, "docs/drafts/x.md")
    assert "[std](/standards/std/)" in text
    assert "[std v2](/standards/std/v2/)" in text
    assert pub(out)["pointers"].get("std", 0) == 2


def test_draft_good_and_bad_on_same_line(tmp_path):
    repo, idx, out = setup(tmp_path, {"drafts/x.md": "x [[other]] y [[ghost@3]] z\n"})
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    text = read(out, "drafts/x.md")
    assert "[other](/standards/other/)" in text
    assert "[[ghost@3]]" in text
    assert pub(out)["pointers"].get("other", 0) == 1


def test_pointer_counts_combine_draft_and_regular_pages(tmp_path):
    repo, idx, out = setup(
        tmp_path,
        {"a.md": "[[std]]\n", "drafts/b.md": "[[std]] [[std@99]]\n"},
    )
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    assert pub(out)["pointers"].get("std", 0) == 2


@pytest.mark.parametrize(
    "path",
    [
        "a.md",
        "docs/x.md",
        "mydrafts/x.md",
        "drafts-old/x.md",
        "draft/x.md",
        "drafts.md",
        "docs/drafts.md",
    ],
)
def test_non_draft_bad_pointer_still_error(tmp_path, path):
    pages = {path: "See [[nope]].\n"}
    if path != "a.md":
        pages["a.md"] = "# A\n"
    repo, idx, out = setup(tmp_path, pages)
    res = run(repo, idx, out)
    assert res.returncode == 2, res.stdout + res.stderr
    assert any(ln.startswith(f"ERROR {path}: [[nope]]") for ln in errors(res))
    assert out_files(out) == []


def test_repo_folder_named_drafts_is_not_a_draft_folder(tmp_path):
    repo, idx, out = setup(tmp_path, {"a.md": "See [[nope]].\n"}, name="drafts")
    res = run(repo, idx, out)
    assert res.returncode == 2, res.stdout + res.stderr
    assert any(ln.startswith("ERROR a.md: [[nope]]") for ln in errors(res))
    assert out_files(out) == []


def test_error_elsewhere_still_blocks_despite_draft_warning(tmp_path):
    repo, idx, out = setup(
        tmp_path, {"a.md": "[[ghost]]\n", "drafts/b.md": "[[nope]]\n"}
    )
    res = run(repo, idx, out)
    assert res.returncode == 2, res.stdout + res.stderr
    assert any(ln.startswith("ERROR a.md: [[ghost]]") for ln in errors(res))
    assert out_files(out) == []
    lines = report(res)
    assert lines == sorted(lines)


def test_warnings_with_pending_exit_one(tmp_path):
    repo, idx, out = setup(
        tmp_path, {"drafts/x.md": "[[nope]]\n"}, index=INDEX_WITH_NEW
    )
    res = run(repo, idx, out)
    assert res.returncode == 1, res.stdout + res.stderr
    assert any(ln.startswith("PENDING newer:") for ln in pendings(res))
    assert len(warns(res)) == 1
    assert (out / "drafts/x.md").is_file()
    assert pub(out)["warnings"] == 1


def test_report_lines_sorted_with_warnings(tmp_path):
    repo, idx, out = setup(
        tmp_path,
        {
            "drafts/b.md": "[[nope]]\n",
            "docs/drafts/a.md": "[[zzz]]\n",
            "a/drafts/z.md": "[[std@99]]\n",
        },
        index=INDEX_WITH_NEW,
    )
    res = run(repo, idx, out)
    assert res.returncode == 1, res.stdout + res.stderr
    lines = report(res)
    assert lines == sorted(lines)
    assert sum(ln.startswith("WARN ") for ln in lines) == 3
    assert any(ln.startswith("PENDING ") for ln in lines)


def test_warn_uses_repo_path_for_readme_in_drafts(tmp_path):
    repo, idx, out = setup(tmp_path, {"drafts/README.md": "[[nope]]\n"})
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    w = warns(res)
    assert len(w) == 1 and w[0].startswith("WARN drafts/README.md: [[nope]]")
    assert (out / "drafts/index.md").is_file()
    assert "[[nope]]" in read(out, "drafts/index.md")


def test_draft_pages_listed_in_pages(tmp_path):
    repo, idx, out = setup(
        tmp_path, {"a.md": "# A\n", "drafts/x.md": "[[nope]]\n", "docs/drafts/y.md": "ok\n"}
    )
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    pages = pub(out)["pages"]
    assert "drafts/x.md" in pages
    assert "docs/drafts/y.md" in pages
    assert pages == sorted(pages)


def test_draft_pointers_in_code_are_not_warned(tmp_path):
    body = "Inline `[[nope]]` here.\n\n```\n[[ghost@4]]\n```\n"
    repo, idx, out = setup(tmp_path, {"drafts/x.md": body})
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    assert warns(res) == []
    assert pub(out)["warnings"] == 0
    text = read(out, "drafts/x.md")
    assert "`[[nope]]`" in text
    assert "[[ghost@4]]" in text


def test_clean_drafts_produce_no_warnings(tmp_path):
    repo, idx, out = setup(tmp_path, {"drafts/x.md": "[[std@2]] [[other]]\n"})
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    assert warns(res) == []
    assert pub(out)["warnings"] == 0


def test_non_ascii_draft(tmp_path):
    path = "drafts/über.md"
    repo, idx, out = setup(tmp_path, {path: "Grüße — 日本語 [[nope]] ✓\n"})
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    w = [nfc(ln) for ln in warns(res)]
    assert len(w) == 1 and w[0].startswith(nfc(f"WARN {path}: [[nope]]"))
    published = [p for p in out_files(out) if p.endswith(".md")]
    assert any(nfc(p) == nfc(path) for p in published)
    target = next(p for p in published if nfc(p) == nfc(path))
    assert "Grüße — 日本語 [[nope]] ✓" in read(out, target)


def test_draft_relative_links_and_images_still_work(tmp_path):
    repo, idx, out = setup(
        tmp_path,
        {
            "docs/guide.md": "# Guide\n\n## Sec\n",
            "docs/drafts/x.md": "[g](../guide.md#sec) ![i](img.png) [[nope]]\n",
            "docs/drafts/img.png": b"\x89PNG\r\n\x1a\nfake",
        },
    )
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    text = read(out, "docs/drafts/x.md")
    assert "../guide.md#sec" in text
    assert (out / "docs/guide.md").is_file()
    assert (out / "docs/drafts/img.png").read_bytes() == b"\x89PNG\r\n\x1a\nfake"


# ----------------------------------------------------------- publish.json


def test_publish_json_defaults(tmp_path):
    repo, idx, out = setup(tmp_path, {"a.md": "[[std]]\n"})
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    data = pub(out)
    assert data["base_url"] == ""
    assert data["warnings"] == 0
    assert isinstance(data["warnings"], int) and not isinstance(data["warnings"], bool)
    assert data["repo"] == "repo"
    assert data["adopted"] == ["other", "std"]


def test_publish_json_warnings_matches_warn_lines(tmp_path):
    repo, idx, out = setup(
        tmp_path,
        {
            "drafts/a.md": "[[nope]] and [[std@99]]\n",
            "docs/drafts/b.md": "[[ghost]]\n",
            "c.md": "[[std]]\n",
        },
    )
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    w = warns(res)
    assert len(w) >= 2
    assert pub(out)["warnings"] == len(w)


# ----------------------------------------------------------- --base-url


@pytest.mark.parametrize("prefix", ["/docs", "/docs/"])
def test_base_url_prefixes_links_and_trailing_slash_dropped(tmp_path, prefix):
    repo, idx, out = setup(tmp_path, {"a.md": "A [[std]] B [[std@2]]\n"})
    res = run(repo, idx, out, "--base-url", prefix)
    assert res.returncode == 0, res.stdout + res.stderr
    text = read(out, "a.md")
    assert "[std](/docs/standards/std/)" in text
    assert "[std v2](/docs/standards/std/v2/)" in text
    assert "/docs//" not in text
    assert pub(out)["base_url"] == "/docs"


@pytest.mark.parametrize(
    "prefix,used",
    [
        ("https://example.org/site", "https://example.org/site"),
        ("https://example.org/site/", "https://example.org/site"),
    ],
)
def test_base_url_absolute(tmp_path, prefix, used):
    repo, idx, out = setup(tmp_path, {"a.md": "[[other]] [[std@1]]\n"})
    res = run(repo, idx, out, "--base-url", prefix)
    assert res.returncode == 0, res.stdout + res.stderr
    text = read(out, "a.md")
    assert f"[other]({used}/standards/other/)" in text
    assert f"[std v1]({used}/standards/std/v1/)" in text
    assert pub(out)["base_url"] == used


def test_base_url_slash_only_is_empty(tmp_path):
    repo, idx, out = setup(tmp_path, {"a.md": "[[std]]\n"})
    res = run(repo, idx, out, "--base-url", "/")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "[std](/standards/std/)" in read(out, "a.md")
    assert "//standards" not in read(out, "a.md")
    assert pub(out)["base_url"] == ""


@pytest.mark.parametrize("extra", [(), ("--base-url", "")])
def test_base_url_default_empty(tmp_path, extra):
    repo, idx, out = setup(tmp_path, {"a.md": "[[std]] [[std@2]]\n"})
    res = run(repo, idx, out, *extra)
    assert res.returncode == 0, res.stdout + res.stderr
    text = read(out, "a.md")
    assert "[std](/standards/std/)" in text
    assert "[std v2](/standards/std/v2/)" in text
    assert pub(out)["base_url"] == ""


def test_base_url_does_not_touch_relative_links_or_code(tmp_path):
    repo, idx, out = setup(
        tmp_path,
        {
            "a.md": "[b](sub/b.md#top) `[[std]]` [[std]]\n",
            "sub/b.md": "# B\n",
        },
    )
    res = run(repo, idx, out, "--base-url", "/docs")
    assert res.returncode == 0, res.stdout + res.stderr
    text = read(out, "a.md")
    assert "(sub/b.md#top)" in text
    assert "`[[std]]`" in text
    assert "[std](/docs/standards/std/)" in text
    assert pub(out)["pointers"].get("std", 0) == 1


def test_base_url_in_drafts(tmp_path):
    repo, idx, out = setup(tmp_path, {"drafts/x.md": "[[std]] [[nope]]\n"})
    res = run(repo, idx, out, "--base-url", "/docs/")
    assert res.returncode == 0, res.stdout + res.stderr
    text = read(out, "drafts/x.md")
    assert "[std](/docs/standards/std/)" in text
    assert "[[nope]]" in text
    data = pub(out)
    assert data["base_url"] == "/docs"
    assert data["warnings"] == 1


def test_base_url_with_error_writes_nothing(tmp_path):
    repo, idx, out = setup(tmp_path, {"a.md": "[[ghost]]\n"})
    res = run(repo, idx, out, "--base-url", "/docs")
    assert res.returncode == 2, res.stdout + res.stderr
    assert out_files(out) == []


def test_base_url_with_pending(tmp_path):
    repo, idx, out = setup(tmp_path, {"a.md": "[[std]]\n"}, index=INDEX_WITH_NEW)
    res = run(repo, idx, out, "--base-url", "/docs")
    assert res.returncode == 1, res.stdout + res.stderr
    assert "[std](/docs/standards/std/)" in read(out, "a.md")
    assert pub(out)["base_url"] == "/docs"


def test_base_url_missing_value_fails_cleanly(tmp_path):
    repo, idx, out = setup(tmp_path, {"a.md": "# A\n"})
    res = run(repo, idx, out, "--base-url")
    assert res.returncode != 0
    assert "Traceback" not in res.stderr + res.stdout


# ----------------------------------------------------------- re-runs


def test_rerun_with_different_base_url_updates_links(tmp_path):
    repo, idx, out = setup(tmp_path, {"a.md": "[[std]]\n", "drafts/x.md": "[[std@2]]\n"})
    first = run(repo, idx, out, "--base-url", "/old")
    assert first.returncode == 0, first.stdout + first.stderr
    second = run(repo, idx, out, "--base-url", "/new/")
    assert second.returncode == 0, second.stdout + second.stderr
    assert "[std](/new/standards/std/)" in read(out, "a.md")
    assert "[std v2](/new/standards/std/v2/)" in read(out, "drafts/x.md")
    assert "/old/" not in read(out, "a.md")
    assert pub(out)["base_url"] == "/new"


def test_rerun_removes_stale_draft_and_resets_warnings(tmp_path):
    repo, idx, out = setup(tmp_path, {"a.md": "# A\n", "drafts/x.md": "[[nope]]\n"})
    first = run(repo, idx, out)
    assert first.returncode == 0, first.stdout + first.stderr
    assert pub(out)["warnings"] == 1
    (repo / "drafts" / "x.md").unlink()
    second = run(repo, idx, out)
    assert second.returncode == 0, second.stdout + second.stderr
    assert not (out / "drafts" / "x.md").exists()
    data = pub(out)
    assert data["warnings"] == 0
    assert "drafts/x.md" not in data["pages"]


def test_rerun_is_idempotent(tmp_path):
    repo, idx, out = setup(
        tmp_path,
        {"a.md": "[[std]]\n", "docs/drafts/x.md": "[[std@2]] [[nope]]\n"},
    )
    first = run(repo, idx, out, "--base-url", "/docs")
    assert first.returncode == 0, first.stdout + first.stderr
    snap = {p: (out / p).read_bytes() for p in out_files(out)}
    second = run(repo, idx, out, "--base-url", "/docs")
    assert second.returncode == 0, second.stdout + second.stderr
    assert {p: (out / p).read_bytes() for p in out_files(out)} == snap
    assert warns(first) == warns(second)
