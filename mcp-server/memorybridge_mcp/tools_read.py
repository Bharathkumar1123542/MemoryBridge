"""
memorybridge_mcp.tools_read
----------------------------
Read-only MCP tools for MemoryBridge.

These two tools are the ONLY tools that may be bound to a Strands Agent
(specifically, the Routine Planning Agent). Every other agent in the system
receives tools=[] — an empty list (architecture.md §7.4, ADR-002).

get_pool is injected by server.py at startup to avoid circular imports.
"""

from __future__ import annotations

from typing import Any

from .validation import validate_uuid

# Injected by server.py before any tool call; declared here so type checkers
# know it exists and tools_read is importable without the pool being ready.
get_pool: Any = None


async def get_assisted_user_profile(assisted_user_id: str) -> dict:
    """
    Return the assisted user's name, timezone, and titles of their currently
    active routines.

    Read-only. No PII beyond name and timezone is returned. Active routine
    titles are included so the Routine Planning Agent can flag a scheduling
    conflict without being able to see step details or raw caregiver requests.

    Args:
        assisted_user_id: UUID of the assisted user (resolved server-side
            by the FastAPI router — never supplied by the browser directly).

    Returns:
        {
            "id": str,
            "name": str,
            "timezone": str,
            "active_routine_titles": list[str]
        }

    Raises:
        ValueError: if no assisted user with the given id exists or if
            assisted_user_id is not a valid UUID.
    """
    validate_uuid(assisted_user_id, "assisted_user_id")
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT au.id, au.name, au.timezone
            FROM   assisted_users au
            WHERE  au.id = $1::uuid
            """,
            assisted_user_id,
        )

        if row is None:
            raise ValueError(
                f"Assisted user '{assisted_user_id}' not found."
            )

        active_titles = await conn.fetch(
            """
            SELECT title
            FROM   routines
            WHERE  assisted_user_id = $1::uuid
              AND  status = 'active'
              AND  title IS NOT NULL
            ORDER BY scheduled_time
            """,
            assisted_user_id,
        )

        return {
            "id": str(row["id"]),
            "name": row["name"],
            "timezone": row["timezone"],
            "active_routine_titles": [r["title"] for r in active_titles],
        }


async def get_existing_routines(assisted_user_id: str) -> list[dict]:
    """
    Return active routines for this assisted user (title, scheduled_time,
    recurrence) so the Routine Planning Agent can check for time conflicts
    before proposing a schedule.

    Read-only. Step details and raw caregiver requests are NOT returned —
    only the scheduling metadata the Planning Agent needs.

    Args:
        assisted_user_id: UUID of the assisted user.

    Returns:
        List of dicts, each with:
        {
            "id": str,
            "title": str,
            "scheduled_time": str | None,   # "HH:MM" in 24-hour format
            "recurrence": str | None
        }
        
    Raises:
        ValueError: if assisted_user_id is not a valid UUID
    """
    validate_uuid(assisted_user_id, "assisted_user_id")
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id,
                   title,
                   to_char(scheduled_time, 'HH24:MI') AS scheduled_time,
                   recurrence
            FROM   routines
            WHERE  assisted_user_id = $1::uuid
              AND  status = 'active'
            ORDER BY scheduled_time NULLS LAST
            """,
            assisted_user_id,
        )

        return [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "scheduled_time": r["scheduled_time"],
                "recurrence": r["recurrence"],
            }
            for r in rows
        ]
