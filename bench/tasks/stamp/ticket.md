Build `stamp`, this repository's console script, which creates a new Python project:

    stamp <target> --name <name> --purpose <text> --owner <text> [--check "<shell command>"]

It creates <target> with `pyproject.toml` (`[project]` name, description = purpose, authors =
[{name = owner}]), `src/<package>/__init__.py` (package = name with - as _, module docstring =
purpose), `.gitlab-ci.yml` (job `test` with `script: [<check>]`, default `uv run pytest -q`, and
`variables: {PURPOSE: <purpose>}`) and `README.md` (`# <name>`, blank line, purpose). Then it
makes <target> a git repo, commits the files, and installs a pre-push hook that runs <check>.
Names are lowercase letters, digits and dashes. Write tests; `uv run pytest -q` and
`uv run ruff check .` must pass.
