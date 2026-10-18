"""What each build read from the knowledge base, from its stream-json log: canon documents read
(lessons arms), canon-lib files read (lib arms), and MCP calls (code arm), plus failed tool calls.
Usage: python reads.py <task> [arm ...]"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

task = sys.argv[1]
arms = sys.argv[2:] or ["without", "lessons", "lib", "both", "code"]
here = Path(__file__).resolve().parent
for arm in arms:
    for p in sorted(here.glob(f"runs/{task}-{arm}-*/build.jsonl")):
        docs, libfiles, mcp, errors, ids = Counter(), Counter(), Counter(), 0, []
        by_id = {}
        for line in p.read_text().splitlines():
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if m.get("type") == "assistant":
                for c in m["message"].get("content", []):
                    if c.get("type") != "tool_use":
                        continue
                    by_id[c["id"]] = c["name"]
                    name, inp = c["name"], c.get("input", {})
                    if name.startswith("mcp__ds__"):
                        mcp[name.removeprefix("mcp__ds__")] += 1
                        if name.endswith("code_add"):
                            ids.append(inp.get("ids"))
                    elif name in ("Read", "Grep", "Glob"):
                        target = str(inp.get("file_path") or inp.get("path") or inp.get("pattern") or "")
                        if "/canon/" in target:
                            rel = target.split("/canon/", 1)[1]
                            (libfiles if rel.startswith("lib") else docs)[rel] += 1
            elif m.get("type") == "user":
                for c in m["message"].get("content", []) if isinstance(m["message"].get("content"), list) else []:
                    if c.get("type") == "tool_result" and c.get("is_error"):
                        errors += 1
        run = p.parent.name
        print(f"{run}: canon docs read {sum(docs.values())} ({len(docs)} distinct); lib files read {sum(libfiles.values())}; "
              f"mcp {dict(mcp) or '-'}; tool errors {errors}")
        if docs:
            print("   docs:", ", ".join(sorted(docs)))
        if libfiles:
            print("   lib:", ", ".join(sorted(re.sub(r'^lib/(src/canon_lib/)?', '', f) for f in libfiles)))
        if ids:
            print("   code_add ids:", ids)
