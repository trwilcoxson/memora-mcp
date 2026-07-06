"""Prove the save -> paraphrase-search loop through the real MCP server.

Saves a fact in one server session, then retrieves it in a second, fresh
server process using a query that shares no keywords with the saved text.
That second process is the point: recall survives the process that learned
the fact, and matching is semantic, not lexical.
"""

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

FACT = (
    "For the payments service we decided to pin the Stripe API version to "
    "2026-05-28 because the June release changed webhook signature ordering "
    "and broke our replay tests."
)
PARAPHRASE = "why is our billing provider locked to an older release?"

SERVER = StdioServerParameters(
    command=sys.executable,
    args=["-m", "memora_mcp.server"],
    env=dict(os.environ),
)


async def call(session: ClientSession, tool: str, args: dict) -> str:
    result = await session.call_tool(tool, args)
    return "\n".join(c.text for c in result.content if getattr(c, "text", None))


async def main() -> None:
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print(f"tools: {names}")
            print("\n== save ==")
            print(await call(session, "memory_save", {"content": FACT}))

    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(f"\n== search (fresh process): {PARAPHRASE!r} ==")
            out = await call(session, "memory_search", {"query": PARAPHRASE, "top_k": 3})
            print(out)
            if "No matching memories" in out or "stripe" not in out.lower():
                print("\nFAIL: paraphrase did not recall the saved fact")
                sys.exit(1)
            print("\nPASS: cross-process semantic recall works")


if __name__ == "__main__":
    asyncio.run(main())
