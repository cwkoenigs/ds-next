import json
from pathlib import Path

import pytest

from ds_next.kb import Canon, Skills

STANDARDS = [
    ("adr-000", 1, "Repo knowledge system", ["*"]),
    ("testing", 1, "Testing and QA", ["*"]),
    ("error-handling", 1, "Error handling", ["service", "package"]),
    ("idempotency", 1, "Idempotency", ["service", "pipeline"]),
]


def make_canon(root: Path, bump: dict[str, int] | None = None) -> Canon:
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for sid, v, title, applies in STANDARDS:
        v = (bump or {}).get(sid, v)
        (root / f"{sid}.md").write_text(f"---\nid: {sid}\nversion: {v}\n---\n\n# {title}\n\nBody of {sid}.\n")
        rows.append({"id": sid, "version": v, "title": title, "applies_to": applies, "owner": "o",
                     "supersedes": None, "status": "accepted", "hash": "x", "path": f"{sid}.md"})
    scaffolds = []
    for sid, status, path, tags in [("python-cli", "accepted", ["python", "cli"], ["python", "package", "cli"]),
                                    ("python-draft", "proposed", ["python", "draft"], ["python"])]:
        d = root / "scaffolds" / sid
        files = {"pyproject.toml": 'name = "{{name}}"\ndescription = {{purpose_json}}\n',
                 "src/__package__/__init__.py": '"""{{purpose}}"""\n',
                 "dot-gitignore": ".venv/\n"}
        for rel, text in files.items():
            (d / "files" / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / "files" / rel).write_text(text)
        (d / "SCAFFOLD.md").write_text(f"---\nid: {sid}\n---\n\n# {sid}\n\nAbout {sid}.\n")
        scaffolds.append({"id": sid, "version": 3, "title": f"T {sid}", "path": path, "tags": tags,
                          "owner": "o", "status": status, "defaults": {"test_cmd": "uv run pytest -q"},
                          "hash": "x", "dir": f"scaffolds/{sid}", "files": sorted(files)})
    (root / "index.json").write_text(json.dumps({"generated": "today", "standards": rows, "scaffolds": scaffolds}))
    return Canon(root)


@pytest.fixture
def canon(tmp_path) -> Canon:
    return make_canon(tmp_path / "canon")


@pytest.fixture
def skills(tmp_path) -> Skills:
    root = tmp_path / "skills-os"
    for name, desc in [("so-capture", "Capture gotchas. Long tail."), ("so-changes", "Record decisions.")]:
        (root / name).mkdir(parents=True)
        (root / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n\nSteps.\n")
    return Skills(root)
