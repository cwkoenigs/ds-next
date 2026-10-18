"""Reference `envmerge`: validates the judge (its tests must pass here, and fail on the mutants).
The dotenv parsing, schema and type rules are the same as in ref/envcheck.py."""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
TYPES = {"string", "int", "bool", "port", "url", "enum"}
BOOLS = {"true", "false", "yes", "no", "on", "off", "1", "0"}
ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "$": "$"}


class SchemaError(ValueError):
    pass


def parse_dotenv(text: str, filename: str) -> tuple[dict[str, str], list[str]]:
    """{NAME: value} and the ERROR lines for lines that cannot be parsed."""
    found: dict[str, str] = {}
    errors: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("export ", "export\t")):
            line = line[7:].lstrip()
        name, sep, rest = line.partition("=")
        name = name.strip()
        if not sep or not NAME_RE.fullmatch(name):
            errors.append(f"ERROR {filename}:{lineno}: cannot parse line")
            continue
        rest = rest.strip()
        try:
            found[name] = _value(rest)
        except ValueError as e:
            errors.append(f"ERROR {filename}:{lineno}: {e}")
    return found, errors


def _value(rest: str) -> str:
    if rest.startswith("'"):
        end = rest.find("'", 1)
        if end < 0:
            raise ValueError("unterminated single quote")
        _only_comment(rest[end + 1:])
        return rest[1:end]
    if rest.startswith('"'):
        out, i = [], 1
        while i < len(rest):
            c = rest[i]
            if c == "\\" and i + 1 < len(rest) and rest[i + 1] in ESCAPES:
                out.append(ESCAPES[rest[i + 1]])
                i += 2
                continue
            if c == '"':
                _only_comment(rest[i + 1:])
                return "".join(out)
            out.append(c)
            i += 1
        raise ValueError("unterminated double quote")
    m = re.search(r"\s#", rest)
    if m:
        rest = rest[:m.start()]
    return rest.strip()


def _only_comment(tail: str) -> None:
    tail = tail.strip()
    if tail and not tail.startswith("#"):
        raise ValueError("text after the closing quote")


def load_schema(path: Path) -> dict[str, dict]:
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise SchemaError(f"cannot read {path}: {e}") from e
    table = data.get("vars", {})  # a schema with no variables is a valid, empty schema
    if not isinstance(table, dict):
        raise SchemaError("[vars] must be a table of variables")
    specs: dict[str, dict] = {}
    for name, spec in table.items():
        if not NAME_RE.fullmatch(name) or not isinstance(spec, dict):
            raise SchemaError(f"[vars.{name}] is not a valid variable table")
        kind = spec.get("type")
        if kind not in TYPES:
            raise SchemaError(f"[vars.{name}] type must be one of {', '.join(sorted(TYPES))}")
        if not isinstance(spec.get("required", False), bool):
            raise SchemaError(f"[vars.{name}] required must be true or false")
        if "default" in spec and not isinstance(spec["default"], str):
            raise SchemaError(f"[vars.{name}] default must be a string")
        values = spec.get("values")
        if kind == "enum" and not (isinstance(values, list) and values and all(isinstance(v, str) for v in values)):
            raise SchemaError(f"[vars.{name}] enum needs a values list of strings")
        specs[name] = {"type": kind, "required": spec.get("required", False), "default": spec.get("default"),
                       "values": values or []}
    return specs


def type_problem(spec: dict, value: str) -> str | None:
    kind = spec["type"]
    if kind == "int" and not re.fullmatch(r"[+-]?\d+", value):
        return f"{value!r} is not an int"
    if kind == "bool" and value.lower() not in BOOLS:
        return f"{value!r} is not a bool"
    if kind == "port" and not (value.isdigit() and 1 <= int(value) <= 65535):
        return f"{value!r} is not a port (1 to 65535)"
    if kind == "url":
        parts = urlsplit(value)
        if not parts.scheme or not parts.netloc:
            return f"{value!r} is not a url"
    if kind == "enum" and value not in spec["values"]:
        return f"{value!r} is not one of {', '.join(spec['values'])}"
    return None


def quote(value: str) -> str:
    out = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("\n", "\\n").replace("\t", "\\t")
    return f'"{out}"'


def check(specs: dict[str, dict], merged: dict[str, str], allow_unknown: bool) -> tuple[list[str], list[str], dict]:
    """(ERROR lines, WARN lines, merged variables with defaults filled in)."""
    errors: list[str] = []
    warns: list[str] = []
    final = dict(merged)
    for name, spec in specs.items():
        if name not in final:
            if spec["default"] is not None:
                final[name] = spec["default"]
            elif spec["required"]:
                errors.append(f"ERROR {name}: required and missing")
            continue
        problem = type_problem(spec, final[name])
        if problem:
            errors.append(f"ERROR {name}: {problem}")
    for name in merged:
        if name not in specs:
            if allow_unknown:
                warns.append(f"WARN {name}: not in the schema")
            else:
                errors.append(f"ERROR {name}: not in the schema")
    return errors, warns, final


def write_out(out: Path, names: list[str], final: dict[str, str]) -> None:
    """Whole or not at all: a temporary file beside out, then an atomic replace."""
    text = f"# generated by envmerge from {', '.join(names)}\n" + "".join(
        f"{name}={quote(final[name])}\n" for name in sorted(final))
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix=".envmerge-")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.replace(tmp, out)


def main() -> None:
    p = argparse.ArgumentParser(prog="envmerge")
    p.add_argument("schema")
    p.add_argument("files", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--allow-unknown", action="store_true")
    a = p.parse_args()
    try:
        specs = load_schema(Path(a.schema))
    except SchemaError as e:
        print(f"ERROR schema: {e}")
        sys.exit(1)
    merged: dict[str, str] = {}
    errors: list[str] = []
    for f in a.files:
        try:
            text = Path(f).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"envmerge: {e}", file=sys.stderr)
            sys.exit(2)
        found, errs = parse_dotenv(text, f)
        merged.update(found)
        errors.extend(errs)
    problems, warns, final = check(specs, merged, a.allow_unknown)
    errors.extend(problems)
    for line in sorted(errors + warns):
        print(line)
    if errors:
        sys.exit(1)
    try:
        write_out(Path(a.out), [Path(f).name for f in a.files], final)
    except OSError as e:
        print(f"envmerge: {e}", file=sys.stderr)
        sys.exit(2)
    print(f"MERGED {len(final)} from {len(a.files)} files")
    sys.exit(0)


if __name__ == "__main__":
    main()
