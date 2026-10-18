"""Hidden acceptance tests for the `publish` console script."""

import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path

import pytest

BIN = os.environ.get("TARGET_BIN", "publish")

DEFAULT_INDEX = {
    "standards": [
        {"id": "alpha", "version": 2},
        {"id": "beta", "version": 1},
    ]
}

ADOPTED_ALPHA = {"version": "2", "date": "2024-01-15"}
DECLINED_BETA = {"version": "1", "reason": '"not relevant"', "revisit": "2025-06-01"}


# ---------------------------------------------------------------- helpers


def toml_manifest(adopted=None, declined=None):
    """Render a manifest from {id: {field: raw_toml_value}} dicts."""
    out = []
    for section, tables in (("adopted", adopted or {}), ("declined", declined or {})):
        for sid, fields in tables.items():
            out.append(f"[{section}.{sid}]")
            for key, value in fields.items():
                out.append(f"{key} = {value}")
            out.append("")
    return "\n".join(out)


CLEAN_MANIFEST = toml_manifest({"alpha": ADOPTED_ALPHA}, {"beta": DECLINED_BETA})


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def setup(tmp_path, files=None, manifest=CLEAN_MANIFEST, index=DEFAULT_INDEX, name="myrepo"):
    repo = tmp_path / name
    repo.mkdir()
    if manifest is not None:
        write(repo / ".ds" / "manifest.toml", manifest)
    for rel, content in (files or {}).items():
        write(repo / rel, content)
    idx = tmp_path / "index.json"
    if index is not None:
        write(idx, index if isinstance(index, str) else json.dumps(index))
    return repo, idx, tmp_path / "out"


def run(repo, index, out, cwd=None):
    return subprocess.run(
        [BIN, str(repo), "--index", str(index), "--out", str(out)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        timeout=60,
    )


def report(res):
    return [
        line
        for line in res.stdout.splitlines()
        if line.startswith("ERROR ") or line.startswith("PENDING ")
    ]


def has_line(res, prefix):
    return any(line.startswith(prefix) for line in report(res))


def snapshot(out):
    if not out.exists():
        return {}
    return {
        p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()
    }


def assert_nothing_written(out):
    assert not out.exists() or not any(out.rglob("*"))


def no_traceback(res):
    assert "Traceback" not in res.stderr
    assert "Traceback" not in res.stdout


def publish_json(out):
    return json.loads((out / "publish.json").read_text(encoding="utf-8"))


def read(out, rel):
    return (out / rel).read_text(encoding="utf-8")


def link_target(text, label):
    m = re.search(r"\[" + re.escape(label) + r"\]\(<?([^)\s>]+)>?\)", text)
    assert m, f"no link labelled {label!r} in:\n{text}"
    return m.group(1)


def resolve(out, page_rel, target):
    """Resolve a relative link target from an output page; return (path, anchor)."""
    path, _, anchor = target.partition("#")
    resolved = Path(os.path.normpath(out / Path(page_rel).parent / path))
    return resolved, anchor


# ---------------------------------------------------------------- happy path


def test_clean_run_exits_zero_and_writes_publish_json(tmp_path):
    repo, idx, out = setup(
        tmp_path,
        {"README.md": "# Home\n", "docs/guide.md": "# Guide\n"},
    )
    res = run(repo, idx, out)
    no_traceback(res)
    assert res.returncode == 0, res.stdout + res.stderr
    assert report(res) == []
    data = publish_json(out)
    assert data["repo"] == "myrepo"
    assert data["adopted"] == ["alpha"]
    assert data["pages"] == ["docs/guide.md", "index.md"]
    assert not any(data["pointers"].values())


def test_page_renaming_rules(tmp_path):
    repo, idx, out = setup(
        tmp_path,
        {
            "README.md": "readme top\n",
            "index.md": "index top\n",
            "docs/README.md": "readme docs\n",
            "sub/index.md": "index sub\n",
            "sub/deep/page.md": "deep\n",
        },
    )
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "readme top" in read(out, "index.md")
    assert "index top" in read(out, "repo-index.md")
    assert "readme docs" in read(out, "docs/index.md")
    assert "index sub" in read(out, "sub/index.md")
    assert "deep" in read(out, "sub/deep/page.md")
    assert not (out / "README.md").exists()
    assert not (out / "docs" / "README.md").exists()
    assert publish_json(out)["pages"] == sorted(
        ["index.md", "repo-index.md", "docs/index.md", "sub/index.md", "sub/deep/page.md"]
    )


def test_non_ascii_content_and_filename(tmp_path):
    name = unicodedata.normalize("NFC", "docs/naïve.md")
    repo, idx, out = setup(
        tmp_path,
        {
            "README.md": "# Café — 日本語 ✓\n\nSee [[alpha]].\n",
            name: "Ünïcödé body\n",
        },
    )
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    text = read(out, "index.md")
    assert "Café — 日本語 ✓" in text
    assert "[alpha](/standards/alpha/)" in text
    pages = [unicodedata.normalize("NFC", p) for p in publish_json(out)["pages"]]
    assert name in pages
    written = [unicodedata.normalize("NFC", p.relative_to(out).as_posix()) for p in out.rglob("*.md")]
    assert name in written


@pytest.mark.parametrize("skipped", [".git", "node_modules", ".venv"])
def test_skipped_directories(tmp_path, skipped):
    repo, idx, out = setup(
        tmp_path,
        {
            "README.md": "home\n",
            f"{skipped}/notes.md": "bad pointer [[ghost]]\n",
            f"{skipped}/pkg/README.md": "pkg [[ghost@7]]\n",
        },
    )
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    assert not (out / skipped).exists()
    assert publish_json(out)["pages"] == ["index.md"]


def test_empty_repo_has_no_pages(tmp_path):
    repo, idx, out = setup(tmp_path, {})
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    data = publish_json(out)
    assert data["pages"] == []
    assert data["adopted"] == ["alpha"]


def test_adopted_list_sorted(tmp_path):
    index = {
        "standards": [
            {"id": "zulu", "version": 1},
            {"id": "alpha", "version": 1},
            {"id": "mike", "version": 1},
        ]
    }
    manifest = toml_manifest(
        {
            "zulu": {"version": "1", "date": "2024-01-01"},
            "alpha": {"version": "1", "date": "2024-02-01"},
        },
        {"mike": {"version": "1", "reason": '"no"', "revisit": "2025-01-01"}},
    )
    repo, idx, out = setup(tmp_path, {"README.md": "x\n"}, manifest=manifest, index=index)
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    assert publish_json(out)["adopted"] == ["alpha", "zulu"]


# ---------------------------------------------------------------- pointers


def test_pointer_conversion_and_counts(tmp_path):
    repo, idx, out = setup(
        tmp_path,
        {"docs/guide.md": "See [[alpha]] and [[alpha@1]], also [[beta]] and [[alpha@2]].\n"},
    )
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    text = read(out, "docs/guide.md")
    assert "[alpha](/standards/alpha/)" in text
    assert "[alpha v1](/standards/alpha/v1/)" in text
    assert "[alpha v2](/standards/alpha/v2/)" in text
    assert "[beta](/standards/beta/)" in text
    assert "[[" not in text
    pointers = publish_json(out)["pointers"]
    assert pointers["alpha"] == 3
    assert pointers["beta"] == 1


def test_pointer_counts_across_pages(tmp_path):
    repo, idx, out = setup(
        tmp_path,
        {
            "README.md": "[[alpha]]\n",
            "a.md": "[[alpha]] [[beta]]\n",
            "x/y/z.md": "[[beta@1]] [[beta]] [[alpha]]\n",
        },
    )
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    pointers = publish_json(out)["pointers"]
    assert pointers["alpha"] == 3
    assert pointers["beta"] == 3


@pytest.mark.parametrize(
    "code",
    [
        "Inline `[[alpha]]` and `[[ghost]]` and `[[alpha@9]]`.\n",
        "```\n[[alpha]] [[ghost]] [[alpha@9]]\n```\n",
        "```text\n[[alpha]] [[ghost]] [[alpha@9]]\n```\n",
        "~~~\n[[alpha]] [[ghost]] [[alpha@9]]\n~~~\n",
    ],
)
def test_pointers_in_code_are_not_pointers(tmp_path, code):
    page = "Real [[beta]].\n\n" + code + "\nAfter.\n"
    repo, idx, out = setup(tmp_path, {"page.md": page})
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    text = read(out, "page.md")
    assert "[beta](/standards/beta/)" in text
    assert "[[alpha]]" in text
    assert "[[ghost]]" in text
    assert "/standards/alpha/" not in text
    pointers = publish_json(out)["pointers"]
    assert pointers["beta"] == 1
    assert pointers.get("alpha", 0) == 0
    assert pointers.get("ghost", 0) == 0


def test_pointer_to_declined_standard_is_fine(tmp_path):
    repo, idx, out = setup(tmp_path, {"README.md": "[[beta@1]]\n"})
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "[beta v1](/standards/beta/v1/)" in read(out, "index.md")


@pytest.mark.parametrize(
    "page_path, pointer",
    [
        ("docs/guide.md", "[[ghost]]"),
        ("docs/guide.md", "[[ghost@1]]"),
        ("README.md", "[[alpha@3]]"),
        ("a/b/c.md", "[[beta@99]]"),
    ],
)
def test_bad_pointer_is_error_on_page_path(tmp_path, page_path, pointer):
    repo, idx, out = setup(
        tmp_path,
        {"README.md": "fine [[alpha]]\n", page_path: f"text {pointer} more\n"},
    )
    res = run(repo, idx, out)
    no_traceback(res)
    assert res.returncode == 2, res.stdout + res.stderr
    lines = [line for line in report(res) if line.startswith(f"ERROR {page_path}: ")]
    assert lines, res.stdout
    assert any(pointer in line for line in lines)
    assert_nothing_written(out)


# ---------------------------------------------------------------- links and assets


def test_relative_links_between_pages_are_rewritten(tmp_path):
    repo, idx, out = setup(
        tmp_path,
        {
            "README.md": "[guidelink](docs/guide.md) [toplink](index.md)\n",
            "index.md": "[readmelink](README.md#intro)\n",
            "docs/guide.md": "[homelink](../README.md#setup) [deeplink](a/b.md)\n",
            "docs/a/b.md": "[uplink](../../README.md) [toplink2](../../index.md#x)"
            " [siblinglink](../README.md)\n",
            "docs/README.md": "docs home\n",
        },
    )
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr

    cases = [
        ("index.md", "guidelink", "docs/guide.md", ""),
        ("index.md", "toplink", "repo-index.md", ""),
        ("repo-index.md", "readmelink", "index.md", "intro"),
        ("docs/guide.md", "homelink", "index.md", "setup"),
        ("docs/guide.md", "deeplink", "docs/a/b.md", ""),
        ("docs/a/b.md", "uplink", "index.md", ""),
        ("docs/a/b.md", "toplink2", "repo-index.md", "x"),
        ("docs/a/b.md", "siblinglink", "docs/index.md", ""),
    ]
    for page, label, expected, anchor in cases:
        target = link_target(read(out, page), label)
        resolved, got_anchor = resolve(out, page, target)
        assert resolved == Path(os.path.normpath(out / expected)), (page, label, target)
        assert resolved.is_file(), (page, label, target)
        assert got_anchor == anchor, (page, label, target)


def test_external_and_anchor_only_links_untouched(tmp_path):
    repo, idx, out = setup(
        tmp_path,
        {
            "docs/guide.md": "[ext](https://example.com/README.md#a) "
            "[sec](#section-two) [mail](mailto:team@example.com)\n",
        },
    )
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    text = read(out, "docs/guide.md")
    assert "[ext](https://example.com/README.md#a)" in text
    assert "[sec](#section-two)" in text
    assert "[mail](mailto:team@example.com)" in text


def test_linked_images_and_files_are_copied(tmp_path):
    png = b"\x89PNG\r\n\x1a\n" + bytes(range(256))
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
    pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    pic = b"\xff\xd8\xff\xe0JPEGDATA"
    repo, idx, out = setup(
        tmp_path,
        {
            "README.md": "![toppic](pics/p.jpg)\n",
            "docs/guide.md": "![diagram](img/d.png)\n\n![logo](../assets/logo.svg)\n\n"
            "[spec](files/spec.pdf)\n",
            "docs/img/d.png": png,
            "assets/logo.svg": svg,
            "docs/files/spec.pdf": pdf,
            "pics/p.jpg": pic,
        },
    )
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    cases = [
        ("docs/guide.md", "diagram", png),
        ("docs/guide.md", "logo", svg),
        ("docs/guide.md", "spec", pdf),
        ("index.md", "toppic", pic),
    ]
    for page, label, content in cases:
        target = link_target(read(out, page), label)
        resolved, _ = resolve(out, page, target)
        assert resolved.is_file(), (page, label, target)
        assert resolved.read_bytes() == content
        assert out in resolved.parents


# ---------------------------------------------------------------- manifest / index errors


def test_unknown_manifest_id_is_error(tmp_path):
    manifest = CLEAN_MANIFEST + "\n" + toml_manifest({"ghost": {"version": "1", "date": "2024-01-01"}})
    repo, idx, out = setup(tmp_path, {"README.md": "x\n"}, manifest=manifest)
    res = run(repo, idx, out)
    no_traceback(res)
    assert res.returncode == 2, res.stdout + res.stderr
    assert has_line(res, "ERROR ghost: ")
    assert_nothing_written(out)


@pytest.mark.parametrize("value", ['"2"', "2.5", "true", '"two"'])
def test_bad_version_type_is_error(tmp_path, value):
    manifest = toml_manifest(
        {"alpha": {"version": value, "date": "2024-01-15"}}, {"beta": DECLINED_BETA}
    )
    repo, idx, out = setup(tmp_path, {"README.md": "x\n"}, manifest=manifest)
    res = run(repo, idx, out)
    no_traceback(res)
    assert res.returncode == 2, res.stdout + res.stderr
    assert has_line(res, "ERROR alpha: ")
    assert_nothing_written(out)


@pytest.mark.parametrize(
    "section, sid, field",
    [
        ("adopted", "alpha", "version"),
        ("adopted", "alpha", "date"),
        ("declined", "beta", "version"),
        ("declined", "beta", "reason"),
        ("declined", "beta", "revisit"),
    ],
)
def test_missing_field_is_error(tmp_path, section, sid, field):
    adopted = {"alpha": dict(ADOPTED_ALPHA)}
    declined = {"beta": dict(DECLINED_BETA)}
    (adopted if section == "adopted" else declined)[sid].pop(field)
    repo, idx, out = setup(tmp_path, {"README.md": "x\n"}, manifest=toml_manifest(adopted, declined))
    res = run(repo, idx, out)
    no_traceback(res)
    assert res.returncode == 2, res.stdout + res.stderr
    assert has_line(res, f"ERROR {sid}: ")
    assert_nothing_written(out)


@pytest.mark.parametrize("section", ["adopted", "declined"])
def test_version_that_never_existed_is_error(tmp_path, section):
    if section == "adopted":
        manifest = toml_manifest({"alpha": {"version": "3", "date": "2024-01-15"}}, {"beta": DECLINED_BETA})
        sid = "alpha"
    else:
        bad = dict(DECLINED_BETA, version="5")
        manifest = toml_manifest({"alpha": ADOPTED_ALPHA}, {"beta": bad})
        sid = "beta"
    repo, idx, out = setup(tmp_path, {"README.md": "x\n"}, manifest=manifest)
    res = run(repo, idx, out)
    assert res.returncode == 2, res.stdout + res.stderr
    assert has_line(res, f"ERROR {sid}: ")
    assert_nothing_written(out)


@pytest.mark.parametrize(
    "manifest",
    [None, "[adopted.alpha\nversion = 2\n", "this is = = not toml\n", "[adopted.alpha]\nversion = 2\nversion = 3\n"],
)
def test_unreadable_manifest_is_manifest_error(tmp_path, manifest):
    repo, idx, out = setup(tmp_path, {"README.md": "x\n"}, manifest=manifest)
    res = run(repo, idx, out)
    no_traceback(res)
    assert res.returncode == 2, res.stdout + res.stderr
    assert has_line(res, "ERROR manifest: ")
    assert_nothing_written(out)


@pytest.mark.parametrize("index", [None, "{not json", ""])
def test_unreadable_index_is_index_error(tmp_path, index):
    repo, idx, out = setup(tmp_path, {"README.md": "x\n"}, index=index)
    res = run(repo, idx, out)
    no_traceback(res)
    assert res.returncode == 2, res.stdout + res.stderr
    assert has_line(res, "ERROR index: ")
    assert_nothing_written(out)


def test_report_lines_are_sorted(tmp_path):
    index = {
        "standards": [
            {"id": "alpha", "version": 2},
            {"id": "beta", "version": 1},
            {"id": "gamma", "version": 1},
            {"id": "delta", "version": 3},
        ]
    }
    manifest = toml_manifest(
        {
            "zeta": {"version": "1", "date": "2024-01-01"},
            "alpha": {"version": "2"},
            "delta": {"version": "1", "date": "2024-01-01"},
            "aardvark": {"version": "1", "date": "2024-01-01"},
        },
        {"beta": DECLINED_BETA},
    )
    repo, idx, out = setup(
        tmp_path, {"README.md": "[[nope]]\n"}, manifest=manifest, index=index
    )
    res = run(repo, idx, out)
    assert res.returncode == 2, res.stdout + res.stderr
    lines = report(res)
    assert lines == sorted(lines)
    for prefix in ("ERROR aardvark: ", "ERROR alpha: ", "ERROR zeta: ", "ERROR README.md: "):
        assert any(line.startswith(prefix) for line in lines), (prefix, lines)
    assert_nothing_written(out)


# ---------------------------------------------------------------- pending


def test_adopted_older_version_is_pending_and_publishes(tmp_path):
    manifest = toml_manifest({"alpha": {"version": "1", "date": "2023-01-01"}}, {"beta": DECLINED_BETA})
    repo, idx, out = setup(tmp_path, {"README.md": "[[alpha]]\n"}, manifest=manifest)
    res = run(repo, idx, out)
    no_traceback(res)
    assert res.returncode == 1, res.stdout + res.stderr
    assert report(res) == [line for line in report(res) if line.startswith("PENDING ")]
    assert has_line(res, "PENDING alpha: ")
    assert "[alpha](/standards/alpha/)" in read(out, "index.md")
    assert publish_json(out)["adopted"] == ["alpha"]


def test_declined_older_version_is_pending(tmp_path):
    index = {"standards": [{"id": "alpha", "version": 2}, {"id": "beta", "version": 2}]}
    repo, idx, out = setup(tmp_path, {"README.md": "x\n"}, index=index)
    res = run(repo, idx, out)
    assert res.returncode == 1, res.stdout + res.stderr
    assert has_line(res, "PENDING beta: ")
    assert not has_line(res, "PENDING alpha")
    assert (out / "publish.json").is_file()


def test_unmentioned_standard_is_pending(tmp_path):
    index = {"standards": DEFAULT_INDEX["standards"] + [{"id": "gamma", "version": 4}]}
    repo, idx, out = setup(tmp_path, {"README.md": "[[gamma@2]]\n"}, index=index)
    res = run(repo, idx, out)
    assert res.returncode == 1, res.stdout + res.stderr
    assert [line.split(":")[0] for line in report(res)] == ["PENDING gamma"]
    assert "[gamma v2](/standards/gamma/v2/)" in read(out, "index.md")


def test_empty_manifest_everything_pending(tmp_path):
    repo, idx, out = setup(tmp_path, {"README.md": "x\n"}, manifest="")
    res = run(repo, idx, out)
    assert res.returncode == 1, res.stdout + res.stderr
    lines = report(res)
    assert lines == sorted(lines)
    assert [line.split(":")[0] for line in lines] == ["PENDING alpha", "PENDING beta"]
    assert publish_json(out)["adopted"] == []


# ---------------------------------------------------------------- re-runs


def test_rerun_is_idempotent(tmp_path):
    repo, idx, out = setup(
        tmp_path,
        {
            "README.md": "[g](docs/guide.md) [[alpha]] ![p](img/p.png)\n",
            "docs/guide.md": "[h](../README.md#a) [[beta@1]]\n",
            "img/p.png": b"\x89PNG data",
        },
    )
    first = run(repo, idx, out)
    assert first.returncode == 0, first.stdout + first.stderr
    snap = snapshot(out)
    second = run(repo, idx, out)
    assert second.returncode == 0, second.stdout + second.stderr
    assert snapshot(out) == snap


def test_rerun_removes_stale_pages(tmp_path):
    repo, idx, out = setup(
        tmp_path,
        {"README.md": "home\n", "docs/old.md": "old\n", "docs/keep.md": "keep\n"},
    )
    assert run(repo, idx, out).returncode == 0
    assert (out / "docs" / "old.md").is_file()
    (repo / "docs" / "old.md").unlink()
    write(repo / "docs" / "new.md", "new\n")
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    assert not (out / "docs" / "old.md").exists()
    assert (out / "docs" / "new.md").is_file()
    assert publish_json(out)["pages"] == ["docs/keep.md", "docs/new.md", "index.md"]


def test_rerun_after_readme_removed_drops_index(tmp_path):
    repo, idx, out = setup(tmp_path, {"README.md": "home\n", "a.md": "a\n"})
    assert run(repo, idx, out).returncode == 0
    (repo / "README.md").unlink()
    res = run(repo, idx, out)
    assert res.returncode == 0, res.stdout + res.stderr
    assert not (out / "index.md").exists()
    assert publish_json(out)["pages"] == ["a.md"]


def test_error_run_leaves_previous_output_untouched(tmp_path):
    repo, idx, out = setup(tmp_path, {"README.md": "home [[alpha]]\n", "a.md": "a\n"})
    assert run(repo, idx, out).returncode == 0
    snap = snapshot(out)
    assert snap
    write(repo / "b.md", "broken [[ghost]]\n")
    (repo / "a.md").unlink()
    res = run(repo, idx, out)
    assert res.returncode == 2, res.stdout + res.stderr
    assert has_line(res, "ERROR b.md: ")
    assert snapshot(out) == snap


# ---------------------------------------------------------------- paths & CLI


def test_relative_arguments_and_nested_out(tmp_path):
    repo, idx, _ = setup(tmp_path, {"README.md": "[d](docs/x.md)\n", "docs/x.md": "x\n"})
    res = run("myrepo", "index.json", "build/site/out", cwd=tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr
    out = tmp_path / "build" / "site" / "out"
    assert (out / "index.md").is_file()
    assert (out / "docs" / "x.md").is_file()
    assert publish_json(out)["repo"] == "myrepo"


@pytest.mark.parametrize("form", ["dot", "trailing-slash", "dotdot"])
def test_repo_name_from_folder(tmp_path, form):
    repo, idx, out = setup(tmp_path, {"README.md": "x\n"}, name="team-docs.v2")
    (tmp_path / "elsewhere").mkdir()
    if form == "dot":
        res = run(".", idx, out, cwd=repo)
    elif form == "trailing-slash":
        res = run("team-docs.v2/", idx, out, cwd=tmp_path)
    else:
        res = run("../team-docs.v2", idx, out, cwd=tmp_path / "elsewhere")
    assert res.returncode == 0, res.stdout + res.stderr
    assert publish_json(out)["repo"] == "team-docs.v2"


def test_out_is_a_file_fails_cleanly(tmp_path):
    repo, idx, out = setup(tmp_path, {"README.md": "x\n"})
    out.write_text("I am a file\n", encoding="utf-8")
    res = run(repo, idx, out)
    no_traceback(res)
    assert res.returncode != 0
    assert len(res.stderr.strip().splitlines()) == 1


def test_missing_repo_fails_cleanly(tmp_path):
    idx = tmp_path / "index.json"
    write(idx, json.dumps(DEFAULT_INDEX))
    res = run(tmp_path / "does-not-exist", idx, tmp_path / "out")
    no_traceback(res)
    assert res.returncode != 0
    assert_nothing_written(tmp_path / "out")


def test_missing_arguments_fail_cleanly(tmp_path):
    repo, idx, _ = setup(tmp_path, {"README.md": "x\n"})
    res = subprocess.run(
        [BIN, str(repo), "--index", str(idx)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    no_traceback(res)
    assert res.returncode != 0
