import asyncio
import os
import shutil
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

DS_NEXT = shutil.which("ds-next") or str(Path(sys.executable).parent / "ds-next")


@pytest.mark.skipif(not Path(DS_NEXT).exists(), reason="ds-next console script not installed")
def test_mcp_serves_the_knowledge_base_tools(canon, tmp_path):
    async def run():
        env = {**os.environ, "DS_CANON": str(canon.root)}
        params = StdioServerParameters(command=DS_NEXT, args=["mcp"], env=env, cwd=str(tmp_path))
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            names = {t.name for t in (await s.list_tools()).tools}
            text = (await s.call_tool("canon_read", {"id": "testing"})).content[0].text
            return names, text

    names, text = asyncio.run(run())
    assert {"canon_list", "canon_read", "block_list", "block_get", "block_add", "scaffold_get"} <= names
    assert "Body of testing." in text
