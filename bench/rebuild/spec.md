Build this repository's command: a Claude-Code-style terminal for our team's knowledge system,
run as the console script this repository already declares in pyproject.toml.

What it must do:

1. Run with no arguments, it opens an interactive terminal: a welcome panel that shows the
   working directory and how many standards, scaffolds and blocks the canon has, then a `›`
   prompt. The canon is the directory in $DS_CANON, else ~/Developer/canon; its index.json
   lists standards, scaffolds and blocks.
2. Slash commands, with Tab completion:
   - /help lists the commands.
   - /canon lists the canon's standards; /canon <id> prints one standard's text.
   - /blocks lists the canon's accepted code blocks.
   - /status shows what the current repository's .ds/manifest.toml records: adopted, declined,
     and anything the canon has a newer version of.
   - /new creates a project (below).
   - /clear starts a fresh session; /exit leaves (Ctrl-D too).
   - An unknown command says it is unknown.
3. Any other text is a turn with Cortex Code (the local `cortex` CLI, through Snowflake's Python
   SDK), shown the way Claude Code shows it, with a live status line while it works. Ctrl-C
   interrupts a turn without leaving. Every tool call that runs a command or writes a file asks
   the person for approval first; reading the knowledge base never asks.
4. Cortex has the knowledge base as tools: list and read standards, list scaffolds.
5. /new: the person picks one of the canon's accepted scaffolds, then fills in one form (name,
   purpose, owner) with suggestions already filled in. Cortex then reviews the draft against the
   canon, and the repository is created from the accepted scaffold's templates in a new folder
   under the working directory, with git initialised and the files committed.

How to build it:

- Follow this repository's standards and gotchas: AGENTS.md points at them, and the ds tools
  read them. They record mistakes already made once.
- Use the canon's accepted code blocks for anything they cover, added with block_add, instead
  of writing that code yourself.
- Write tests for what you add. `uv run pytest -q` and `uv run ruff check .` must pass when you
  finish, and `ds-next reconcile` must report no errors.
- Change nothing outside this repository.
