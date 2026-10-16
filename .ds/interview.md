# Interview

<!-- ds:local interview 2026-10-16 -->
- **name**: ds-next
- **purpose**: A Claude-Code-style terminal over Cortex Code that scaffolds projects from the canon and keeps them reconciled
- **owner**: ckoenigs
- **kind**: cli
- **test_cmd**: uv run pytest -q
- **lint_cmd**: uv run ruff check .
- **tags**: ['python', 'package', 'cli']
- **snowflake**: 
- **notes**: Live tests call Cortex Code: DS_LIVE=1 uv run pytest -m live.
- **declines**: {}
