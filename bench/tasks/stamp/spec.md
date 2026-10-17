Build `stamp`, a command that creates a new Python project from templates it carries.
It is this repository's console script `stamp` (declared in pyproject.toml).

    stamp <target> --name <name> --purpose <text> --owner <text> [--check "<shell command>"]

It creates the directory <target> (which must not exist yet, or be empty) containing:

- `pyproject.toml`: `[project]` with `name = <name>`, `description = <purpose>`, and
  `authors = [{name = <owner>}]`.
- `src/<package>/__init__.py`, where <package> is <name> with `-` replaced by `_`. Its module
  docstring is exactly <purpose>.
- `.gitlab-ci.yml`: one job `test` whose `script` is a list with the single command `<check>`
  (default `uv run pytest -q`), and whose `variables` has `PURPOSE: <purpose>`.
- `README.md`: `# <name>`, a blank line, then <purpose>.

Then it makes <target> a git repository, commits all files, and installs a git pre-push hook
that runs <check> and blocks the push if it fails.

Requirements:

- <purpose> and <owner> are free text a person typed, and can contain any characters.
  Every generated file must stay valid (TOML, Python, YAML) and carry the text exactly.
- <name>: lowercase letters, digits and single dashes, starting with a letter. The package must
  be importable. Refuse anything else with a message.
- Never write outside <target>, and never change files that were there before.
- On any failure, print a one-line reason to stderr and exit non-zero, without a traceback.
- Write tests. `uv run pytest -q` and `uv run ruff check .` must pass.
