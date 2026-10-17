You are building a small Python project from a spec, in the repository you are in. It was just created from the team's python-cli scaffold. Work only inside it.

The team's knowledge base (the "canon") is reachable only through the `ds` MCP tools; its files are not readable. The tools:
- canon_list / canon_read: standards and gotchas (kind gotcha = a mistake already made once). Pass tags to canon_list to see what applies.
- block_list / block_get / block_add: accepted, tested code blocks. block_get shows a block's API, source and tests; block_add copies it into this repo (module, tests, requirements, manifest entry).
- scaffold_list / scaffold_get: the canon's project scaffolds.
- project_status: reconciles this repo against the canon. It must report no errors at the end.

Rules that make this a fair test:
- Do NOT run the `cortex` CLI or start a live Cortex session (the account's request cap is used up). Prove behaviour with unit tests that fake the SDK client.
- Do not commit or push. Install only into this repo's own virtualenv (`uv add` and `uv sync` are fine).
- Bash is limited to `uv` and `git`. Use `uv run ...` for Python, pytest and ruff.

