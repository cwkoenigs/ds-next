"""The steps both sides run, from the real canon's index."""
import fnmatch
import json
import os
import sys
from pathlib import Path

canon = json.loads(Path(sys.argv[1] + "/index.json").read_text())
skills_root = sys.argv[2]
skills = sorted(d for d in os.listdir(skills_root) if os.path.isfile(f"{skills_root}/{d}/SKILL.md"))
acc = [s for s in canon["scaffolds"] if s.get("status") == "accepted"]
acc_blocks = [b for b in canon["blocks"] if b.get("status") == "accepted"]
code = canon["code"]
S = []
w = lambda tool, args=None, cwd="work": S.append({"cwd": cwd, "tool": tool, "args": args or {}})
w("canon_list"); w("canon_list", {"tags": "python,cli"}); w("canon_list", {"tags": "node, web"})
for s in canon["standards"]: w("canon_read", {"id": s["id"]})
w("canon_read", {"id": "no-such-standard"}); w("canon_read", {}); w("canon_read", {"name": "[testing]"})
w("skills_list")
for n in skills: w("skill_read", {"name": n})
w("skill_read", {"name": "nope"})
w("scaffold_list")
for s in canon["scaffolds"]: w("scaffold_get", {"id": s["id"]})
w("scaffold_get", {"id": "nope"})
w("block_list", {"tags": ""}); w("block_list", {"tags": "python, snowflake"})
for b in canon["blocks"]: w("block_get", {"id": b["id"]})
w("block_get", {"id": "nope"})
for q in ["user text into TOML", "empty an output folder safely", "snowflake connection", "retry with backoff", "read a csv",
          "log", "the", "validateEmail", "path", "secrets from env"]:
    w("code_search", {"query": q})
for c in code: w("code_get", {"id": c["id"]})
w("code_get", {"query": "toml"}); w("code_get", {}); w("code_get", {"id": "nope:x"})
w("project_status")
w("snowflake_search", {"kind": "bad", "query": "x"}); w("snowflake_search", {"kind": "docs", "query": "x"})
w("capture", {"title": "Dates  in   TOML", "body": "Write dates quoted.\n", "applies_to": ["python", "toml"]})
w("capture", {"title": "Dates in TOML", "body": "again"})
# projects: one per accepted scaffold, created from work/
for i, sc in enumerate(acc):
    name = f"demo-{sc['id']}"[:41].rstrip("-")
    w("scaffold_project", {"scaffold": sc["id"], "scaffold_version": sc["version"], "name": name, "purpose": "x", "directory": "<ROOT>/projects"})  # not fetched yet
    w("scaffold_get", {"id": sc["id"]})
    args = {"scaffold": sc["id"], "scaffold_version": sc["version"], "name": name, "purpose": f"Demo of {sc['id']} for the port check", "owner": "Port Check",
            "directory": "<ROOT>/projects", "tags": ["extra-tag"], "notes": "made by the comparison" if i % 2 else "", "test_cmd": "" }
    if i == 0: args["snowflake"] = "ANALYTICS.ORDERS"
    if i == 1:
        tags = list(sc["tags"]) + ["extra-tag"]
        first = min(st["id"] for st in canon["standards"] if any(pt == "*" or any(fnmatch.fnmatchcase(t, pt) for t in tags) for pt in st["applies_to"]))
        args["declines"] = {first: "not here yet"}
    w("scaffold_project", args)
w("scaffold_project", {"scaffold": acc[0]["id"], "scaffold_version": acc[0]["version"], "name": f"demo-{acc[0]['id']}"[:41].rstrip("-"), "purpose": "again", "owner": "x", "directory": "<ROOT>/projects"})  # exists
w("scaffold_project", {"scaffold": acc[0]["id"], "scaffold_version": acc[0]["version"], "name": "Bad_Name", "purpose": "x", "owner": "x", "directory": "<ROOT>/projects"})
w("scaffold_project", {"scaffold": acc[0]["id"], "scaffold_version": acc[0]["version"], "name": "class", "purpose": "x", "owner": "x", "directory": "<ROOT>/projects"})
w("scaffold_project", {"scaffold": acc[0]["id"], "scaffold_version": acc[0]["version"], "name": "okname", "purpose": "two\nlines", "owner": "x", "directory": "<ROOT>/projects"})
# in the first project: status, code, blocks
p0 = f"projects/demo-{acc[0]['id']}"[:50]
p0 = "projects/" + f"demo-{acc[0]['id']}"[:41].rstrip("-")
w("project_status", cwd=p0)
by_block = {}
for c in code:
    if c["status"] in ("accepted", "proposed"): by_block.setdefault(c["block"], []).append(c["id"])
blocks_with_code = [b for b in acc_blocks if b["id"] in by_block]
b1, b2 = blocks_with_code[0], blocks_with_code[1]
w("code_add", {"ids": ",".join(by_block[b1["id"]][:2])}, cwd=p0)
w("code_add", {"ids": by_block[b1["id"]][2:3] or by_block[b1["id"]][:1]}, cwd=p0)
w("block_add", {"id": b2["id"]}, cwd=p0)
w("block_add", {"id": b2["id"]}, cwd=p0)
w("code_add", {"ids": json.dumps(by_block[b2["id"]][:1])}, cwd=p0)
w("code_add", {"ids": "nope:x"}, cwd=p0)
w("code_add", {}, cwd=p0)
w("block_add", {"id": "nope"}, cwd=p0)
w("project_status", cwd=p0)
w("block_add", {"id": b1["id"]}, cwd="work")
std = {x["id"]: x for x in canon["standards"]}
sid = min(std)
bk = acc_blocks[0]
def m(body): return "[repo]\nname = \"case\"\ntags = [\"python\", \"package\", \"cli\"]\n" + body
R = [
 {"name": "missing", "manifest": None, "docs": {}},
 {"name": "not-toml", "manifest": "[repo\nname=", "docs": {}},
 {"name": "no-repo", "manifest": "x = 1\n", "docs": {}},
 {"name": "bad-tags", "manifest": "[repo]\nname = \"\"\ntags = []\n[blocks]\nnope = 3\n", "docs": {}},
 {"name": "statuses", "manifest": m(f"""
[standards.{sid}]
status = "adoptd"
[standards.unknown-std]
status = "adopted"
[standards.testing]
status = "adopted"
version = 0
[standards.security]
status = "adopted"
version = 1
by = " "
[standards.error-handling]
status = "adopted"
version = 99
by = "a"
[standards.logging]
status = "declined"
version = 1
by = "a"
[standards.docs]
status = "declined"
version = 1
by = "a"
reason = "r"
revisit = "not-a-date"
[standards.idempotency]
status = "declined"
version = 1
by = "a"
reason = "later"
revisit = 2020-01-31
[standards.cli-ux]
status = "declined"
version = 1
by = "a"
reason = "later"
revisit = "2099-12-31"
[blocks.{bk['id']}]
version = 1
[blocks.nope-block]
version = 1
"""), "docs": {"README.md": "See [[testing]] and [[nope]] and [[testing@99]].\n\n```\n[[ignored-in-code]]\n```\nAnd `[[also-ignored]]`.\n", "docs/guide.md": "[[security@1]] [[gone]]\n", ".hidden/x.md": "[[hidden]]\n", "node_modules/y.md": "[[vendored]]\n", "notes/.private.md": "[[dotfile]]\n"}},
 {"name": "bad-standards-table", "manifest": m("standards = 3\n"), "docs": {}},
 {"name": "type-outputs", "manifest": "[repo]\nname = \"t\"\ntags = [\"python\"]\ntype = \"analysis\"\noutputs = [\"report\", \"\"]\n", "docs": {}},
]
P = ["[[testing]] [[testing@0]] [[testing@1]] [[nope@2]]", "~~~\n[[a]]\n~~~~\n[[b]]", "```\nunclosed [[c]]", "``[[d]]`` and `x` [[e]]", "[[UPPER]] [[ok-id]]"]
A = [
 {"name": "existing-app", "files": {"README.md": "# Existing App\n\n[![badge](x)](y)\n\nTurns order data into finance reports. More text here.\n",
   "pyproject.toml": "[project]\nname = \"existing-app\"\ndependencies = [\"snowflake-connector-python\", \"rich\"]\n[project.scripts]\nx = \"y:z\"\n[tool.ruff]\nline-length = 100\n",
   "src/existing_app/__init__.py": "", ".env": "SNOWFLAKE_USER=x\n", "Dockerfile": "FROM python\n"}, "adopt_all": False},
 {"name": "Web_Thing", "files": {"README.md": "# Web\n\n- list first\n\nA web app! It serves pages.\n", "package.json": "{\"dependencies\": {\"next\": \"14\"}, \"devDependencies\": {\"typescript\": \"5\"}, \"scripts\": {\"test\": \"x\", \"typecheck\": \"y\"}}",
   "AGENTS.md": "# Agents\n\nOwn notes.\n", "docs/adr/0001.md": "# ADR\n", "CLAUDE.md": "x\n"}, "adopt_all": True},
]
Path(sys.argv[3]).write_text(json.dumps({"steps": S, "reconcile": R, "pointers": P, "adopt": A}, indent=1))
print(len(S), "steps;", len(acc), "accepted scaffolds;", "blocks used:", b1["id"], b2["id"])
