Build `publish`, this repository's console script, which publishes a repo's docs to the team
site's staging area after checking the repo's standards manifest:

    publish <repo> --index <index.json> --out <directory>

The manifest is `<repo>/.ds/manifest.toml`: `[adopted.<id>]` tables (`version`, `date`) and
`[declined.<id>]` tables (`version`, `reason`, `revisit`). index.json is
`{"standards": [{"id": ..., "version": <int>}, ...]}`. Print sorted lines `ERROR <id>: ...` for
problems (unknown id, bad or missing field, a version that never existed; use id `manifest` or
`index` when a file can't be read or parsed) and `PENDING <id>: ...` where the catalogue has
moved on (a newer version than adopted or declined, or a standard the manifest doesn't mention).

Pages: every `*.md` under <repo> (skip .git, node_modules, .venv) goes to <out> at the same
relative path; README.md becomes index.md, and a top-level index.md becomes repo-index.md.
Rewrite relative links between pages so they still work, and copy the images and files the
pages link to. Pointers in page text, `[[id]]` and `[[id@N]]`, become links: `[id](/standards/id/)`
and `[id vN](/standards/id/vN/)`. A pointer to an unknown id or to a version that never existed
is `ERROR <page path in repo>: [[...]] ...`. Pointers inside code are not pointers.

Finally write `<out>/publish.json`: `{"repo": <repo folder name>, "adopted": [ids],
"pages": [paths relative to <out>], "pointers": {id: count}}`, lists sorted.

If there is any ERROR, write nothing under <out> and exit 2. Otherwise publish, and exit 1 if
anything is PENDING, 0 if clean. Running it again on the same <out> must work, and must not
leave pages from an earlier run that no longer exist in the repo. Any other failure is one line
on stderr and a non-zero exit, never a traceback. Write tests; `uv run pytest -q` and
`uv run ruff check .` must pass.
