#!/bin/sh
# Make a uv project for a reference (or mutant) solution. Usage: make_ref.sh <task> <module.py> <dir>
set -eu
TASK="$1"; MOD="$2"; DIR="$3"
mkdir -p "$DIR"; cd "$DIR"
uv init -q --package --name "$TASK" . >/dev/null
cp "$MOD" "src/$TASK/__init__.py"
uv add -q --dev pytest ruff >/dev/null
mkdir -p tests; printf 'def test_imports():\n    import %s  # noqa: F401\n' "$TASK" > tests/test_smoke.py
