Build `stage`, this repository's console script, which stages a repo's Markdown for a docs site:

    stage <repo> --out <directory>

Copy every `*.md` under <repo> (skip .git, node_modules, .venv) into <out> at the same relative
path. README.md becomes `index.md` (the home page); a top-level `index.md` in the repo becomes
`repo-index.md`. Rewrite relative links between pages so they still work, and copy the
images and files the pages link to. Clear <out> first so old pages don't linger; running it again
on the same <out> should work. Errors should be a one-line message and a non-zero exit. Write
tests; `uv run pytest -q` and `uv run ruff check .` must pass.
