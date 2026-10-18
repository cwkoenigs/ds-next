# Sourced by run.sh and change.sh. Sets KB (prompt text), ADD (--add-dir), MCPCFG and ALLOW for an arm.
# Inputs: ARM, WORK (the folder beside the repo where canon is copied), REPO, CANON, HERE, TASK,
# and COPY=1 to copy the canon there (a fresh build) or COPY=0 to reuse a copy that exists.
LESSONS_TXT="It has lessons: gotchas/*.md are mistakes already made once and the rules that prevent them; the other *.md files are standards. Read the lessons that apply before you start."
LIB_TXT="It has canon-lib (lib/), the team's accepted, tested code: add it with \`uv add --editable $WORK/canon/lib\` and import from canon_lib instead of writing that code yourself (lib/src/canon_lib/__init__.py lists the modules)."
KB=""; ADD=""; MCPCFG='{"mcpServers": {}}'; ALLOW=""
case "$ARM" in
  lessons|lib|both)
    if [ "${COPY:-1}" = 1 ]; then
      mkdir -p "$WORK/canon"
      if [ "$ARM" != lib ]; then
        cp -R "$CANON/gotchas" "$WORK/canon/"; cp "$CANON"/*.md "$WORK/canon/"
        [ -d "$CANON/adr" ] && cp -R "$CANON/adr" "$WORK/canon/"
      fi
      if [ "$ARM" != lessons ]; then
        rsync -a --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache "$CANON/lib" "$WORK/canon/"
      fi
    fi
    case "$ARM" in
      lessons) KB="Your team's knowledge base is at $WORK/canon. $LESSONS_TXT" ;;
      lib)     KB="Your team's knowledge base is at $WORK/canon. $LIB_TXT" ;;
      both)    KB="Your team's knowledge base is at $WORK/canon. $LESSONS_TXT $LIB_TXT" ;;
    esac
    ADD="--add-dir $WORK/canon" ;;
  code)
    if [ ! -f "$REPO/.ds/manifest.toml" ]; then
      mkdir -p "$REPO/.ds"; printf '[repo]\nname = "%s"\ntags = ["python", "cli"]\n' "$TASK" > "$REPO/.ds/manifest.toml"
    fi
    MCPCFG="$(printf '{"mcpServers": {"ds": {"type": "stdio", "command": "%s", "args": ["mcp"], "env": {"DS_CANON": "%s"}}}}' \
      "$HERE/../../.venv/bin/ds-next" "$CANON")"
    KB="Your team's knowledge base is reachable through the \`ds\` MCP tools. code_search finds the team's accepted, tested functions by what they do; code_get reads one, with only what it needs and its tests; code_add copies them into this repo (import them from your package instead of writing that code yourself). canon_list and canon_read give the team's lessons: gotchas are mistakes already made once, and the rules that prevent them. Search and read the lessons that apply before you start."
    ALLOW="mcp__ds__code_search mcp__ds__code_get mcp__ds__code_add mcp__ds__canon_list mcp__ds__canon_read" ;;
  without) ;;
  *) echo "unknown arm $ARM" >&2; exit 2 ;;
esac
