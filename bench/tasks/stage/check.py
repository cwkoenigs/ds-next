"""Checks for `stage`. Run: python check.py <repo>"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import case, git_env, no_traceback, run, static, summary, tmp  # noqa: E402

PNG = bytes(range(256)) * 4
LINK = re.compile(r"(!?)\[[^\]]*\]\(([^)\s]+)\)")


def fixture() -> Path:
    r = tmp() / "repo"
    pages = {
        "README.md": "# Home\nMARK-README\n[Guide](docs/guide.md#setup) [Own index](index.md)\n"
                     "![diagram](img/diagram.png) [web](https://example.com/x.md)\n",
        "index.md": "# Repo index\nMARK-INDEX\n[home](README.md)\n",
        "docs/guide.md": "# Guide\nMARK-GUIDE\n[back](../README.md) [deep](sub/deep.md) [same](#setup)\n",
        "docs/sub/deep.md": "# Deep\nMARK-DEEP\n[top index](../../index.md) [guide](../guide.md)\n",
        ".git/x.md": "MARK-GIT\n", "node_modules/y.md": "MARK-NODE\n", ".venv/z.md": "MARK-VENV\n",
    }
    for rel, text in pages.items():
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text(text)
    (r / "img").mkdir()
    (r / "img" / "diagram.png").write_bytes(PNG)
    return r


def stage(repo: Path, out: Path, env=None):
    return run("stage", str(repo), "--out", str(out), cwd=repo.parent, env=env)


def snapshot(d: Path) -> dict[str, bytes]:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


MARKS = {"MARK-README": "index.md", "MARK-INDEX": "repo-index.md", "MARK-GUIDE": "docs/guide.md",
         "MARK-DEEP": "docs/sub/deep.md"}

static()


@case("every page lands at its path; README is home; the repo's index.md is kept")
def _():
    r = fixture()
    out = r.parent / "site"
    res = stage(r, out)
    got = {m: (out / p).is_file() and m in (out / p).read_text() for m, p in MARKS.items()}
    return res.returncode == 0 and all(got.values()), f"{got} {res.stderr.strip()[-100:]}"


@case("skips .git, node_modules and .venv")
def _():
    r = fixture()
    out = r.parent / "site"
    stage(r, out)
    text = "".join(p.read_text(errors="replace") for p in out.rglob("*.md"))
    return not any(m in text for m in ("MARK-GIT", "MARK-NODE", "MARK-VENV")), ""


@case("every relative link still reaches the right page")
def _():
    r = fixture()
    out = r.parent / "site"
    stage(r, out)
    expect = {("index.md", "Guide"): "MARK-GUIDE", ("index.md", "Own index"): "MARK-INDEX",
              ("repo-index.md", "home"): "MARK-README", ("docs/guide.md", "back"): "MARK-README",
              ("docs/guide.md", "deep"): "MARK-DEEP", ("docs/sub/deep.md", "top index"): "MARK-INDEX",
              ("docs/sub/deep.md", "guide"): "MARK-GUIDE"}
    wrong = []
    for (page, label), mark in expect.items():
        m = re.search(r"\[" + re.escape(label) + r"\]\(([^)\s]+)\)", (out / page).read_text())
        target = m and m.group(1).split("#")[0]
        dest = (out / page).parent / target if target else None
        if not (dest and dest.is_file() and mark in dest.read_text()):
            wrong.append(f"{page}:{label}->{m.group(1) if m else None}")
    return not wrong, str(wrong)


@case("anchors and URLs are kept")
def _():
    r = fixture()
    out = r.parent / "site"
    stage(r, out)
    home, guide = (out / "index.md").read_text(), (out / "docs/guide.md").read_text()
    return "#setup)" in home and "(https://example.com/x.md)" in home and "(#setup)" in guide, ""


@case("linked assets are copied")
def _():
    r = fixture()
    out = r.parent / "site"
    stage(r, out)
    m = re.search(r"!\[diagram\]\(([^)\s]+)\)", (out / "index.md").read_text())
    p = out / m.group(1) if m else None
    return bool(p and p.is_file() and p.read_bytes() == PNG), str(m and m.group(1))


@case("running again on its own output works and drops stale pages")
def _():
    r = fixture()
    out = r.parent / "site"
    stage(r, out)
    (out / "stale.md").write_text("old")
    res = stage(r, out)
    return res.returncode == 0 and not (out / "stale.md").exists() and (out / "index.md").is_file(), \
        res.stderr.strip()[-120:]


@case("an output folder inside the repo is not staged into itself")
def _():
    r = fixture()
    out = r / "site"
    stage(r, out)
    res = stage(r, out)
    return res.returncode == 0 and not (out / "site").exists(), res.stderr.strip()[-120:]


@case("an existing empty output folder is fine")
def _():
    r = fixture()
    out = r.parent / "site"
    out.mkdir()
    res = stage(r, out)
    return res.returncode == 0 and (out / "index.md").is_file(), res.stderr.strip()[-120:]


def refused(repo: Path, out: Path, env=None, protect: Path | None = None) -> tuple[bool, str]:
    protect = protect or repo
    before = snapshot(protect)
    res = stage(repo, out, env=env)
    after = snapshot(protect)
    return res.returncode != 0 and before == after and no_traceback(res), f"exit {res.returncode}"


@case("refuses the repo itself as output")
def _():
    r = fixture()
    return refused(r, r)


@case("refuses a folder that contains the repo")
def _():
    r = fixture()
    return refused(r, r.parent, protect=r.parent)


@case("refuses the home directory")
def _():
    home = tmp()
    (home / "important.txt").write_text("keep")
    r = fixture()
    return refused(r, home, env=git_env(home), protect=home)


@case("refuses a non-empty folder it did not create")
def _():
    r = fixture()
    other = r.parent / "notes"
    other.mkdir()
    (other / "mine.txt").write_text("keep")
    return refused(r, other, protect=other)


@case("a missing repo is a one-line failure, not a traceback")
def _():
    base = tmp()
    res = run("stage", str(base / "nope"), "--out", str(base / "site"), cwd=base)
    return res.returncode != 0 and no_traceback(res) and res.stderr.strip() != "", f"exit {res.returncode}"


summary()
