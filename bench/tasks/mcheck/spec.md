Build `mcheck`, a command that checks a repository's standards manifest against a catalogue.
It is this repository's console script `mcheck` (declared in pyproject.toml).

    mcheck <manifest.toml> --index <index.json> [--docs <directory>]

The catalogue, index.json: `{"standards": [{"id": "<id>", "version": <int>, ...}, ...]}`.

The manifest, TOML:

    [adopted.<id>]
    version = <int>        # the catalogue version the repo follows
    date = <date>          # a TOML date, e.g. 2026-10-17

    [declined.<id>]
    version = <int>        # the version that was declined
    reason = "<text>"      # why, non-empty
    revisit = <date>       # when to look again

Output, one line per finding, sorted, then exit status:

- `ERROR <id>: <what>` for anything wrong: an id the catalogue lacks, a missing or mistyped
  field, a version the catalogue never had.
- `PENDING <id>: <what>` when the catalogue has something newer than the manifest records: an
  adopted standard with a newer version, a declined standard with a newer version than the
  one declined, or a catalogue standard the manifest does not mention at all.
- Exit 0 when there is nothing, 1 when there are only PENDING lines, 2 when there is any ERROR.
- A missing, unreadable or malformed manifest or index is an ERROR line (id `manifest` or
  `index`) and exit 2. mcheck never prints a traceback, whatever the input.

`--docs <directory>`: also read every `*.md` under it. A pointer is `[[<id>]]` or
`[[<id>@<N>]]` in prose. Report `ERROR <file>: [[<id>]] is not in the catalogue` and
`ERROR <file>: [[<id>@<N>]] pins a version the catalogue never had`. Code is not prose:
pointers inside fenced code blocks and inline code are ignored.

Write tests. `uv run pytest -q` and `uv run ruff check .` must pass.
