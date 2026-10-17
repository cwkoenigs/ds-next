Build `stage`, a command that stages a repository's Markdown into a folder a docs site builds.
It is this repository's console script `stage` (declared in pyproject.toml).

    stage <repo> --out <directory>

- Every `*.md` file under <repo> is copied to <out> at the same relative path, skipping `.git`,
  `node_modules`, `.venv` and <out> itself.
- `<repo>/README.md` becomes `<out>/index.md`, the site's home page. If the repo also has its own
  `index.md` at the top, it becomes `<out>/repo-index.md`. No page may be lost or overwritten.
- Relative links between pages (`[text](path.md)`, with or without `#anchor`) are rewritten so
  they still point at the right page after the moves above. Links to URLs are left alone.
- Files that pages link to (images and other non-Markdown files under <repo>) are copied too,
  so the links keep working.
- <out> is emptied before staging, because old pages must not linger. That makes the choice of
  <out> dangerous: stage must refuse an <out> that is <repo> itself, contains <repo>, is the
  home directory or `/`, or is an existing non-empty directory that stage did not create.
  stage marks a directory it created, so running it again on the same <out> works.
- On any failure, print a one-line reason to stderr and exit non-zero, without a traceback.

Write tests. `uv run pytest -q` and `uv run ruff check .` must pass.
