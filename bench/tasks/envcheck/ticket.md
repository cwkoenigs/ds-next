Build `envcheck`, this repository's console script, which checks dotenv files against a schema:

    envcheck <schema.toml> <file.env> [<file.env> ...] [--print]

The schema is TOML: one `[vars.<NAME>]` table per variable, with `type` (one of `string`, `int`,
`bool`, `port`, `url`, `enum`), optional `required` (bool, default false), optional `default`
(a string), and for `enum` a `values` list of strings. A dotenv file has `NAME=value` lines; blank
lines and `#` comment lines are ignored; an optional `export ` prefix is allowed; a value may be
unquoted (a trailing ` # comment` is stripped and surrounding whitespace trimmed), single-quoted
(taken literally) or double-quoted (with `\n`, `\t`, `\\`, `\"` and `\$` escapes). Names match
`[A-Za-z_][A-Za-z0-9_]*`. Later files override earlier ones.

Type rules: `int` is an optional sign and digits; `bool` is true/false/yes/no/on/off/1/0 in any
case; `port` is an integer from 1 to 65535; `url` has a scheme and a host; `enum` must be one of
`values`; `string` is anything.

After merging the files, report each problem as `ERROR <NAME>: ...`, sorted: a required variable
that is missing and has no default; a value of the wrong type; a variable that is not in the
schema (`ERROR <NAME>: not in the schema`). A line that cannot be parsed is
`ERROR <file>:<line number>: ...`. A schema that cannot be read or is malformed is
`ERROR schema: ...`, and nothing else is checked. Exit 0 if there are no errors, 1 otherwise.
With `--print`, after the report and only when there are no errors, print the merged variables
as `NAME=value` lines, sorted by name, with defaults filled in and every value double-quoted using
the escapes above. Any other failure is one line on stderr and a non-zero exit, never a traceback.
Write tests; `uv run pytest -q` and `uv run ruff check .` must pass.
