"""Reference `mcheck`: proves the checks pass on a correct solution."""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from datetime import date, datetime
from pathlib import Path

POINTER = re.compile(r"\[\[([a-z0-9-]+)(?:@(\d+))?\]\]")
CODE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]{0,3}\1[`~]*[ \t]*$|\Z)|(`+)[^`\n].*?\2",
                  re.DOTALL | re.MULTILINE)


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def is_date(v) -> bool:
    return isinstance(v, date) and not isinstance(v, datetime)


def findings(manifest: Path, index: Path, docs: Path | None) -> list[str]:
    out: list[str] = []
    try:
        data = json.loads(index.read_text())
        rows = data["standards"]
        versions = {r["id"]: r["version"] for r in rows}
        if not all(isinstance(k, str) and is_int(v) for k, v in versions.items()):
            raise ValueError("bad entry")
    except (OSError, ValueError, KeyError, TypeError) as e:
        return [f"ERROR index: cannot read {index}: {e}"]
    try:
        m = tomllib.loads(manifest.read_text())
    except (OSError, ValueError) as e:
        return [f"ERROR manifest: cannot read {manifest}: {e}"]
    seen = set()
    for section in ("adopted", "declined"):
        table = m.get(section, {})
        if not isinstance(table, dict):
            out.append(f"ERROR manifest: [{section}] must be a table of tables")
            continue
        for sid, entry in table.items():
            seen.add(sid)
            if not isinstance(entry, dict):
                out.append(f"ERROR {sid}: [{section}.{sid}] must be a table")
                continue
            v = entry.get("version")
            if sid not in versions:
                out.append(f"ERROR {sid}: not in the catalogue")
                continue
            if not is_int(v):
                out.append(f"ERROR {sid}: version must be an integer")
            elif not 1 <= v <= versions[sid]:
                out.append(f"ERROR {sid}: version {v} is one the catalogue never had (current {versions[sid]})")
            elif v < versions[sid]:
                what = "adopted" if section == "adopted" else "declined"
                out.append(f"PENDING {sid}: {what} v{v}, the catalogue has v{versions[sid]}")
            if section == "adopted" and not is_date(entry.get("date")):
                out.append(f"ERROR {sid}: date must be a TOML date")
            if section == "declined":
                reason = entry.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    out.append(f"ERROR {sid}: reason must be non-empty text")
                if not is_date(entry.get("revisit")):
                    out.append(f"ERROR {sid}: revisit must be a TOML date")
    for sid in versions:
        if sid not in seen:
            out.append(f"PENDING {sid}: not adopted or declined")
    if docs is not None:
        for f in sorted(docs.rglob("*.md")):
            rel = f.relative_to(docs)
            for mm in POINTER.finditer(CODE.sub("", f.read_text(errors="replace"))):
                sid, pin = mm.group(1), mm.group(2)
                if sid not in versions:
                    out.append(f"ERROR {rel}: [[{sid}]] is not in the catalogue")
                elif pin is not None and not 1 <= int(pin) <= versions[sid]:
                    out.append(f"ERROR {rel}: [[{sid}@{pin}]] pins a version the catalogue never had")
    return sorted(set(out))


def main() -> None:
    p = argparse.ArgumentParser(prog="mcheck")
    p.add_argument("manifest")
    p.add_argument("--index", required=True)
    p.add_argument("--docs")
    a = p.parse_args()
    lines = findings(Path(a.manifest), Path(a.index), Path(a.docs) if a.docs else None)
    for ln in lines:
        print(ln)
    sys.exit(2 if any(ln.startswith("ERROR") for ln in lines) else 1 if lines else 0)
