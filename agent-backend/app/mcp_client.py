"""
agent-backend.app.mcp_client
------------------------------
MCP client singleton and tool-binding filter for the agent-backend.

This module is the single place where:
  1. The MCP subprocess is started (stdio transport).
  2. The full tool list is fetched from the MCP server.
  3. Only read-only tools are filtered and returned for Agent construction.
  4. All write tools are called directly (by application code, never by agents).

Architecture references:
  - architecture.md §7.4 — least-privilege tool binding
  - architecture.md §9   — MCP server tool contract
  - ADR-002              — no Agent ever holds a write tool
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from mcp import stdio_client, StdioServerParameters
from strands.tools.mcp import MCPClient

from .config import MCP_SERVER_COMMAND, MCP_SERVER_ARGS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool name sets — single source of truth for the binding filter.
# test_tool_binding.py imports READ_ONLY_TOOLS to assert that no agent
# ever receives a name outside this set (ADR-002 enforcement).
# ---------------------------------------------------------------------------
READ_ONLY_TOOLS: frozenset[str] = frozenset({
    "get_assisted_user_profile",
    "get_existing_routines",
})

WRITE_TOOLS: frozenset[str] = frozenset({
    "create_routine",
    "save_routine_steps",
    "update_routine_status",
    "approve_routine",
    "reject_routine",
    "get_today_routines",
    "mark_routine_complete",
    "create_help_alert",
    "get_alerts",
    "log_safety_decision",
})


class MemoryBridgeMCPClient:
    """
    Wrapper around the Strands MCPClient that manages the subprocess lifecycle
    and exposes typed methods for every write tool.

    Usage (in FastAPI lifespan):
        async with mcp_client_context() as client:
            app.state.mcp = client
            yield

    The MCP subprocess stays alive for the full lifetime of the application
    process — it is not started/stopped per request.
    """

    def __init__(self, raw_client: MCPClient) -> None:
        self._client = raw_client

    # -----------------------------------------------------------------------
    # Tool list for Agent construction (read-only subset only)
    # -----------------------------------------------------------------------
    def get_planning_tools(self) -> list:
        """
        Return the tool objects for the Routine Planning Agent.

        Filters the full tool list to READ_ONLY_TOOLS only. This is the
        implementation of least-privilege tool binding (architecture.md §7.4).
        The Semantic Safety Reviewer, Communication Agent, and Escalation Agent
        are constructed with tools=[] — they never call this method.
        """
        all_tools = self._client.list_tools_sync()
        planning_tools = [
            t for t in all_tools if t.tool_name in READ_ONLY_TOOLS
        ]
        logger.info(
            "Planning tools bound: %s",
            [t.tool_name for t in planning_tools],
        )
        return planning_tools

    # -----------------------------------------------------------------------
    # Write tool methods — called by FastAPI routers ONLY, never by Agents
    # Each method is a thin async wrapper that calls the MCP tool by name
    # and returns the parsed result dict.
    # -----------------------------------------------------------------------

    async def create_routine(
        self, assisted_user_id: str, caregiver_id: str, raw_request: str
    ) -> dict:
        return await self._call("create_routine", {
            "assisted_user_id": assisted_user_id,
            "caregiver_id": caregiver_id,
            "raw_request": raw_request,
        })

    async def save_routine_steps(
        self, routine_id: str, steps: list[dict]
    ) -> dict:
        return await self._call("save_routine_steps", {
            "routine_id": routine_id,
            "steps": steps,
        })

    async def update_routine_status(
        self,
        routine_id: str,
        status: str,
        safety_verdict: str | None = None,
        safety_reason: str | None = None,
        title: str | None = None,
        scheduled_time: str | None = None,
        recurrence: str | None = None,
    ) -> dict:
        return await self._call("update_routine_status", {
            "routine_id": routine_id,
            "status": status,
            "safety_verdict": safety_verdict,
            "safety_reason": safety_reason,
            "title": title,
            "scheduled_time": scheduled_time,
            "recurrence": recurrence,
        })

    async def approve_routine(
        self, routine_id: str, caregiver_id: str
    ) -> dict:
        return await self._call("approve_routine", {
            "routine_id": routine_id,
            "caregiver_id": caregiver_id,
        })

    async def reject_routine(
        self, routine_id: str, caregiver_id: str, reason: str | None = None
    ) -> dict:
        return await self._call("reject_routine", {
            "routine_id": routine_id,
            "caregiver_id": caregiver_id,
            "reason": reason,
        })

    async def get_today_routines(
        self, assisted_user_id: str, date: str
    ) -> list[dict]:
        return await self._call("get_today_routines", {
            "assisted_user_id": assisted_user_id,
            "date": date,
        })

    async def mark_routine_complete(
        self, routine_id: str, occurrence_date: str
    ) -> dict:
        return await self._call("mark_routine_complete", {
            "routine_id": routine_id,
            "occurrence_date": occurrence_date,
        })

    async def create_help_alert(
        self,
        assisted_user_id: str,
        caregiver_id: str,
        category: str,
        message: str,
        source_note: str | None = None,
    ) -> dict:
        return await self._call("create_help_alert", {
            "assisted_user_id": assisted_user_id,
            "caregiver_id": caregiver_id,
            "category": category,
            "message": message,
            "source_note": source_note,
        })

    async def get_alerts(self, caregiver_id: str) -> list[dict]:
        return await self._call("get_alerts", {
            "caregiver_id": caregiver_id,
        })

    async def acknowledge_alert(
        self, alert_id: str, caregiver_id: str
    ) -> dict:
        return await self._call("acknowledge_alert", {
            "alert_id": alert_id,
            "caregiver_id": caregiver_id,
        })

    async def log_safety_decision(
        self,
        routine_id: str,
        stage: str,
        decision: str,
        matched_categories: str | None = None,
        detail: str | None = None,
    ) -> dict:
        return await self._call("log_safety_decision", {
            "routine_id": routine_id,
            "stage": stage,
            "decision": decision,
            "matched_categories": matched_categories,
            "detail": detail,
        })

    # -----------------------------------------------------------------------
    # Internal helper
    # -----------------------------------------------------------------------
    async def _call(self, tool_name: str, arguments: dict) -> dict | list:
        """
        Call an MCP tool by name with the given arguments.

        The Strands MCPClient is sync; we run the call in a thread executor
        to avoid blocking the FastAPI event loop.
        """
        import asyncio

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._client.call_tool_sync(tool_name, arguments),
        )
        # MCPClient returns a ToolResult; extract the content
        if hasattr(result, "content") and result.content:
            import json
            raw = result.content[0].text if hasattr(result.content[0], "text") else str(result.content[0])
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return {"raw": raw}
        return {}


@asynccontextmanager
async def mcp_client_context() -> AsyncGenerator[MemoryBridgeMCPClient, None]:
    """
    Async context manager that starts the MCP subprocess and yields a
    MemoryBridgeMCPClient. Use in FastAPI's lifespan handler.

    Example:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with mcp_client_context() as mcp:
                app.state.mcp = mcp
                yield
    """
    raw = MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command=MCP_SERVER_COMMAND,
                args=MCP_SERVER_ARGS,
            )
        )
    )
    with raw:
        logger.info("MCP subprocess started: %s %s", MCP_SERVER_COMMAND, MCP_SERVER_ARGS)
        yield MemoryBridgeMCPClient(raw)
        logger.info("MCP subprocess stopped.")
