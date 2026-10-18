Build `mcheck`, this repository's console script, which checks a standards manifest:

    mcheck <manifest.toml> --index <index.json> [--docs <directory>]

index.json is `{"standards": [{"id": ..., "version": <int>}, ...]}`. The manifest has
`[adopted.<id>]` tables (`version`, `date`) and `[declined.<id>]` tables (`version`, `reason`,
`revisit`). Print sorted lines `ERROR <id>: ...` for problems (unknown id, bad or missing field,
a version that never existed; use id `manifest` or `index` if a file can't be read) and
`PENDING <id>: ...` where the catalogue has moved on (newer version than adopted or declined, or
a standard the manifest doesn't mention). Exit 0 if nothing, 1 if only PENDING, 2 if any ERROR.
With --docs, also check `[[id]]` and `[[id@N]]` pointers in the `*.md` files under it and report
`ERROR <file>: [[...]] ...` for an unknown id or a version that never existed. Write tests;
`uv run pytest -q` and `uv run ruff check .` must pass.
