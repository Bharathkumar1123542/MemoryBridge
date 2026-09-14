"""
memorybridge_mcp.server
-----------------------
Local MCP server for MemoryBridge.

Transport: stdio (started as a subprocess of agent-backend).
Credential boundary: DATABASE_URL is read from the environment here and
    passed to the asyncpg connection pool. It exists NOWHERE else in the
    system — not in FastAPI route handlers, not in any Strands Agent object.

Tool registration follows architecture.md §9:
  - Read tools  → may be bound to the Routine Planning Agent (read-only).
  - Write tools → bound ONLY to application code (FastAPI routers), never
                  to any Strands Agent. This is the implementation of ADR-002.
"""

import asyncio
import os

import asyncpg
from mcp.server.fastmcp import FastMCP

from . import tools_read, tools_write

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------
mcp = FastMCP("memorybridge-mcp")

# ---------------------------------------------------------------------------
# Connection pool — created once at startup, shared across all tool calls.
# DATABASE_URL must be present in the subprocess environment (injected by
# agent-backend from AWS Secrets Manager / docker-compose env file).
# ---------------------------------------------------------------------------
_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it on first call."""
    global _pool
    if _pool is None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL is not set in the MCP server's environment. "
                "This variable must be injected at subprocess startup."
            )
        _pool = await asyncpg.create_pool(
            dsn=database_url,
            min_size=1,
            max_size=5,
            command_timeout=30.0,  # 30 second timeout for runaway queries
            # Neon requires SSL; sslmode=require should be in the DSN.
            # asyncpg respects the sslmode query parameter in the DSN string.
        )
    return _pool


# ---------------------------------------------------------------------------
# Inject the pool getter into both tool modules so they share the same pool
# without circular imports.
# ---------------------------------------------------------------------------
tools_read.get_pool = _get_pool
tools_write.get_pool = _get_pool

# ---------------------------------------------------------------------------
# Read tools — these two may be bound to the Routine Planning Agent.
# Every other agent in the system is constructed with tools=[] (architecture.md §7.4).
# ---------------------------------------------------------------------------
mcp.tool()(tools_read.get_assisted_user_profile)
mcp.tool()(tools_read.get_existing_routines)

# ---------------------------------------------------------------------------
# Write tools — bound ONLY to FastAPI application code, never to any Agent.
# Registering them here makes them available to the MCP client; the
# tool-binding filter in agent-backend/app/mcp_client.py ensures no Agent
# ever receives them. test_tool_binding.py enforces this in CI (ADR-002).
# ---------------------------------------------------------------------------
mcp.tool()(tools_write.create_routine)
mcp.tool()(tools_write.save_routine_steps)
mcp.tool()(tools_write.update_routine_status)
mcp.tool()(tools_write.approve_routine)
mcp.tool()(tools_write.reject_routine)
mcp.tool()(tools_write.get_today_routines)
mcp.tool()(tools_write.mark_routine_complete)
mcp.tool()(tools_write.create_help_alert)
mcp.tool()(tools_write.get_alerts)
mcp.tool()(tools_write.acknowledge_alert)
mcp.tool()(tools_write.log_safety_decision)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")
