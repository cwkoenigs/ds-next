"""Hidden acceptance tests for the `stage` console command.

The implementation is reached only through the executable named by $TARGET_BIN.
"""

import os
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

import pytest

TARGET_BIN = os.environ.get("TARGET_BIN")

pytestmark = pytest.mark.skipif(not TARGET_BIN, reason="TARGET_BIN not set")

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) + b"\x00\xff" * 64
PDF_BYTES = b"%PDF-1.4\n" + bytes(range(255, -1, -1)) + b"\n%%EOF\n"


# --------------------------------------------------------------------------- helpers


def run(*args, cwd=None):
    return subprocess.run(
        [TARGET_BIN, *[str(a) for a in args]],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )


def stage(repo, out, cwd=None):
    return run(repo, "--out", out, cwd=cwd)


def ok(result):
    assert result.returncode == 0, (
        f"exit {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Traceback" not in result.stderr
    return result


def write(path: Path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def files_under(root: Path):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def assert_one_line_error(result):
    assert result.returncode != 0, "expected a non-zero exit"
    combined = (result.stderr + result.stdout).strip()
    assert "Traceback" not in combined, combined
    assert combined, "expected an error message"
    assert len(combined.splitlines()) == 1, f"expected one-line message, got:\n{combined}"


INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?", re.MULTILINE)
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def link_targets(text):
    return INLINE_LINK.findall(text) + REF_DEF.findall(text)


def is_local(target):
    return not (SCHEME.match(target) or target.startswith("#") or target.startswith("/"))


def resolve_link(page: Path, target: str) -> Path:
    bare = target.split("#", 1)[0].split("?", 1)[0]
    return (page.parent / unquote(bare)).resolve()


def links_from(page: Path):
    return [t for t in link_targets(page.read_text(encoding="utf-8")) if is_local(t)]


def assert_links_resolve(out: Path):
    out_r = out.resolve()
    pages = list(out.rglob("*.md"))
    assert pages, "no pages produced"
    for page in pages:
        for target in links_from(page):
            dest = resolve_link(page, target)
            assert dest.is_file(), f"{page.relative_to(out)}: link {target!r} is broken"
            assert out_r in dest.parents, f"{page.relative_to(out)}: {target!r} escapes out"


def find_link(page: Path, marker: str):
    """Return the target of the inline link whose text is `marker`."""
    m = re.search(r"\[" + re.escape(marker) + r"\]\(\s*<?([^)\s>]+)", page.read_text("utf-8"))
    assert m, f"link [{marker}] missing from {page}"
    return m.group(1)


# --------------------------------------------------------------------------- copying


def test_copies_every_markdown_file_at_same_relative_path(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "README.md", "# Home\n")
    write(repo / "CHANGELOG.md", "# Changes\n\nnothing linked here\n")
    write(repo / "docs" / "guide.md", "# Guide\n\nplain text\n")
    write(repo / "docs" / "deep" / "nested" / "page.md", "# Deep page\n")
    write(repo / "src" / "main.py", "print('hi')\n")
    out = tmp_path / "out"

    ok(stage(repo, out))

    assert (out / "CHANGELOG.md").read_text() == "# Changes\n\nnothing linked here\n"
    assert (out / "docs" / "guide.md").read_text() == "# Guide\n\nplain text\n"
    assert (out / "docs" / "deep" / "nested" / "page.md").read_text() == "# Deep page\n"
    # sources are untouched
    assert (repo / "README.md").read_text() == "# Home\n"
    assert (repo / "src" / "main.py").exists()


def test_readme_becomes_index(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "README.md", "# Project Home\n\nWelcome HOME_MARKER.\n")
    out = tmp_path / "out"

    ok(stage(repo, out))

    assert (out / "index.md").is_file()
    assert "HOME_MARKER" in (out / "index.md").read_text()
    assert not (out / "README.md").exists()


def test_top_level_index_renamed_and_cross_links_follow(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "README.md", "# Readme README_MARKER\n\nSee [the-index](index.md).\n")
    write(repo / "index.md", "# Old index INDEX_MARKER\n\nBack to [the-home](README.md).\n")
    out = tmp_path / "out"

    ok(stage(repo, out))

    assert "README_MARKER" in (out / "index.md").read_text()
    assert "INDEX_MARKER" in (out / "repo-index.md").read_text()
    assert "README_MARKER" not in (out / "repo-index.md").read_text()

    to_index = resolve_link(out / "index.md", find_link(out / "index.md", "the-index"))
    assert to_index == (out / "repo-index.md").resolve()
    to_home = resolve_link(out / "repo-index.md", find_link(out / "repo-index.md", "the-home"))
    assert to_home == (out / "index.md").resolve()


def test_skips_git_node_modules_and_venv_anywhere(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "README.md", "# Home\n")
    write(repo / ".git" / "notes.md", "git internal\n")
    write(repo / "node_modules" / "pkg" / "README.md", "vendored\n")
    write(repo / ".venv" / "lib" / "site" / "LICENSE.md", "venv\n")
    write(repo / "web" / "node_modules" / "dep" / "doc.md", "nested vendored\n")
    write(repo / "tools" / ".venv" / "x.md", "nested venv\n")
    write(repo / ".github" / "CONTRIBUTING.md", "# Contributing\n")
    write(repo / "web" / "usage.md", "# Usage\n")
    out = tmp_path / "out"

    ok(stage(repo, out))

    produced = files_under(out)
    for name in produced:
        parts = name.split("/")
        assert ".git" not in parts and "node_modules" not in parts and ".venv" not in parts, name
    assert "web/usage.md" in produced
    assert ".github/CONTRIBUTING.md" in produced


# --------------------------------------------------------------------------- links


def test_links_to_readme_rewritten_from_subdirectories(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "README.md", "# Home\n\n## Install\n")
    write(
        repo / "docs" / "guide.md",
        "# Guide\n\n"
        "Go [home](../README.md).\n"
        "Read [install](../README.md#install).\n"
        'Titled [titled](../README.md "Home page").\n',
    )
    out = tmp_path / "out"

    ok(stage(repo, out))

    guide = out / "docs" / "guide.md"
    home = (out / "index.md").resolve()
    for marker in ("home", "install", "titled"):
        target = find_link(guide, marker)
        assert "README" not in target, target
        assert resolve_link(guide, target) == home
    install = find_link(guide, "install")
    assert install.endswith("#install"), f"anchor lost: {install}"
    assert "Home page" in guide.read_text()


def test_every_relative_link_in_output_resolves(tmp_path):
    repo = tmp_path / "repo"
    write(
        repo / "README.md",
        "# Home\n\n"
        "- [guide](docs/guide.md)\n"
        "- [docs home](docs/README.md)\n"
        "- [api](docs/api/reference.md#endpoints)\n"
        "- [old index](./index.md)\n"
        "![logo](assets/logo.png)\n",
    )
    write(repo / "index.md", "# legacy index\n\n[up](README.md)\n")
    write(
        repo / "docs" / "guide.md",
        "# Guide\n\n[home](../README.md) [api](api/reference.md) "
        "[sib](./faq.md) [docs home](README.md) ![logo](../assets/logo.png)\n",
    )
    write(repo / "docs" / "faq.md", "# FAQ\n\n[guide](guide.md)\n")
    write(repo / "docs" / "README.md", "# Docs section\n\n[top](../README.md)\n")
    write(
        repo / "docs" / "api" / "reference.md",
        "# Ref\n\n## Endpoints\n\n[guide](../guide.md) [root](../../README.md) "
        "[idx](../../index.md)\n",
    )
    write(repo / "assets" / "logo.png", PNG_BYTES)
    out = tmp_path / "out"

    ok(stage(repo, out))

    assert_links_resolve(out)
    # the link to the legacy index must land on the renamed legacy page, not the home page
    readme_out = out / "index.md"
    dest = resolve_link(readme_out, find_link(readme_out, "old index"))
    assert "legacy index" in dest.read_text()
    docs_home = resolve_link(readme_out, find_link(readme_out, "docs home"))
    assert "Docs section" in docs_home.read_text()


def test_reference_style_links_are_rewritten(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "README.md", "# Home\n")
    write(
        repo / "docs" / "page.md",
        "# Page\n\nGo [home][h] and see the [diagram][d].\n\n"
        "[h]: ../README.md\n"
        "[d]: ../img/diagram.svg\n",
    )
    write(repo / "img" / "diagram.svg", "<svg xmlns='http://www.w3.org/2000/svg'/>\n")
    out = tmp_path / "out"

    ok(stage(repo, out))

    page = out / "docs" / "page.md"
    targets = REF_DEF.findall(page.read_text())
    assert len(targets) == 2
    for t in targets:
        assert resolve_link(page, t).is_file(), t
    assert resolve_link(page, targets[0]) == (out / "index.md").resolve()


def test_external_and_anchor_links_left_alone(tmp_path):
    repo = tmp_path / "repo"
    body = (
        "# Home\n\n"
        "[ext](https://example.com/README.md)\n"
        "[ext2](http://example.org/docs/index.md#x)\n"
        "[mail](mailto:someone@example.com)\n"
        "[section](#usage)\n\n"
        "## Usage\n"
    )
    write(repo / "README.md", body)
    out = tmp_path / "out"

    ok(stage(repo, out))

    text = (out / "index.md").read_text()
    assert "](https://example.com/README.md)" in text
    assert "](http://example.org/docs/index.md#x)" in text
    assert "](mailto:someone@example.com)" in text
    assert "](#usage)" in text


# --------------------------------------------------------------------------- assets


def test_linked_images_and_files_are_copied_byte_for_byte(tmp_path):
    repo = tmp_path / "repo"
    write(
        repo / "README.md",
        "# Home\n\n![logo](assets/logo.png)\n[spec](files/spec.pdf)\n",
    )
    write(
        repo / "docs" / "guide.md",
        "# Guide\n\n![shot](images/shot.png)\n![logo again](../assets/logo.png)\n",
    )
    write(repo / "assets" / "logo.png", PNG_BYTES)
    write(repo / "files" / "spec.pdf", PDF_BYTES)
    write(repo / "docs" / "images" / "shot.png", PNG_BYTES[::-1])
    out = tmp_path / "out"

    ok(stage(repo, out))

    home = out / "index.md"
    assert resolve_link(home, find_link(home, "logo")).read_bytes() == PNG_BYTES
    assert resolve_link(home, find_link(home, "spec")).read_bytes() == PDF_BYTES
    guide = out / "docs" / "guide.md"
    assert resolve_link(guide, find_link(guide, "shot")).read_bytes() == PNG_BYTES[::-1]
    assert resolve_link(guide, find_link(guide, "logo again")).read_bytes() == PNG_BYTES
    assert_links_resolve(out)


def test_unlinked_non_markdown_files_are_not_copied(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "README.md", "# Home\n\n![logo](logo.png)\n")
    write(repo / "logo.png", PNG_BYTES)
    write(repo / ".env", "SECRET=hunter2\n")
    write(repo / "src" / "app.py", "print(1)\n")
    write(repo / "assets" / "unused.png", PNG_BYTES)
    out = tmp_path / "out"

    ok(stage(repo, out))

    produced = files_under(out)
    assert not any(name.endswith((".py", ".env")) or name == ".env" for name in produced), produced
    assert "assets/unused.png" not in produced
    assert all("hunter2" not in p.read_text(errors="ignore") for p in out.rglob("*") if p.is_file())


def test_link_escaping_repo_does_not_write_outside_out(tmp_path):
    work = tmp_path / "work"
    repo = work / "repo"
    write(work / "secret.txt", "TOP SECRET\n")
    write(work / "outside.png", PNG_BYTES)
    write(
        repo / "README.md",
        "# Home\n\n[secret](../secret.txt)\n![x](../outside.png)\n[deep](../../../../etc/hosts)\n",
    )
    out = tmp_path / "a" / "b" / "site"

    result = stage(repo, out)
    assert "Traceback" not in result.stderr

    stray = [
        p
        for p in tmp_path.rglob("*")
        if p.is_file() and work not in p.parents and out not in p.parents
    ]
    assert stray == [], f"files written outside out: {stray}"
    if out.exists():
        out_r = out.resolve()
        for p in out.rglob("*"):
            assert out_r in p.resolve().parents


def test_broken_links_do_not_crash(tmp_path):
    repo = tmp_path / "repo"
    write(
        repo / "README.md",
        "# Home\n\n[gone](missing.md) ![nope](img/missing.png) [ok](other.md)\n",
    )
    write(repo / "other.md", "# Other\n")
    out = tmp_path / "out"

    result = stage(repo, out)

    combined = result.stdout + result.stderr
    assert "Traceback" not in combined
    if result.returncode == 0:
        assert (out / "other.md").is_file()
        assert (out / "index.md").is_file()
    else:
        assert_one_line_error(result)


# --------------------------------------------------------------------------- output dir


def test_clears_stale_output(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "README.md", "# Home\n")
    write(repo / "keep.md", "# Keep\n")
    out = tmp_path / "out"
    write(out / "stale.md", "old page\n")
    write(out / "old" / "dir" / "gone.md", "old nested page\n")
    write(out / "old.png", PNG_BYTES)

    ok(stage(repo, out))

    produced = files_under(out)
    assert "stale.md" not in produced
    assert "old/dir/gone.md" not in produced
    assert "old.png" not in produced
    assert "keep.md" in produced and "index.md" in produced


def test_rerun_on_same_out_works_and_reflects_changes(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "README.md", "# Home v1\n\n![logo](logo.png)\n")
    write(repo / "logo.png", PNG_BYTES)
    write(repo / "removed.md", "# Will be removed\n")
    out = tmp_path / "out"

    ok(stage(repo, out))
    first = files_under(out)
    ok(stage(repo, out))
    assert files_under(out) == first

    (repo / "removed.md").unlink()
    write(repo / "README.md", "# Home v2\n")
    ok(stage(repo, out))

    assert not (out / "removed.md").exists()
    assert "Home v2" in (out / "index.md").read_text()


def test_creates_missing_out_with_parents(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "README.md", "# Home\n")
    out = tmp_path / "does" / "not" / "exist" / "site"

    ok(stage(repo, out))

    assert (out / "index.md").is_file()


def test_relative_paths_are_resolved_against_cwd(tmp_path):
    repo = tmp_path / "proj"
    write(repo / "README.md", "# Home\n\n[g](docs/g.md)\n")
    write(repo / "docs" / "g.md", "# G\n")

    ok(stage("proj", "build/site", cwd=tmp_path))

    out = tmp_path / "build" / "site"
    assert (out / "index.md").is_file()
    assert (out / "docs" / "g.md").is_file()
    assert_links_resolve(out)


def test_out_inside_repo_does_not_recurse(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "README.md", "# Home\n")
    write(repo / "docs" / "a.md", "# A\n")
    out = repo / "site"

    first = stage(repo, out)
    second = stage(repo, out)

    assert (repo / "README.md").read_text() == "# Home\n"
    assert (repo / "docs" / "a.md").read_text() == "# A\n"
    for result in (first, second):
        assert "Traceback" not in result.stderr
    if second.returncode == 0:
        produced = files_under(out)
        assert not any(name.startswith("site/") for name in produced), produced
        assert "docs/a.md" in produced
    else:
        assert_one_line_error(second)


# --------------------------------------------------------------------------- errors


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_bad_repo_is_one_line_error(tmp_path, kind):
    if kind == "missing":
        repo = tmp_path / "no-such-repo"
    else:
        repo = write(tmp_path / "file.md", "# not a dir\n")

    result = stage(repo, tmp_path / "out")

    assert_one_line_error(result)
    if kind == "file":
        assert repo.read_text() == "# not a dir\n"


def test_missing_out_option_fails(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "README.md", "# Home\n")
    result = run(repo)
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("which", ["same", "ancestor"])
def test_out_that_would_wipe_repo_is_refused(tmp_path, which):
    parent = tmp_path / "container"
    repo = parent / "repo"
    write(repo / "README.md", "# Precious\n")
    write(repo / "src" / "code.py", "x = 1\n")
    out = repo if which == "same" else parent

    result = stage(repo, out)

    assert (repo / "README.md").read_text() == "# Precious\n"
    assert (repo / "src" / "code.py").read_text() == "x = 1\n"
    assert_one_line_error(result)
