"""
memorybridge_mcp.tools_write
-----------------------------
Write-side MCP tools for MemoryBridge.

IMPORTANT — ADR-002:
    These tools are bound ONLY to FastAPI application code (routers).
    No Strands Agent object in this system is ever given access to any
    tool defined in this module. The tool-binding filter in
    agent-backend/app/mcp_client.py enforces this at construction time,
    and test_tool_binding.py asserts it on every CI run.

    A write tool being registered in the MCP server does NOT mean an agent
    can call it — the MCP client in agent-backend filters by name before
    passing any tool to an Agent constructor.

get_pool is injected by server.py at startup to avoid circular imports.
"""

from __future__ import annotations

from typing import Any

from .validation import validate_uuid

# Injected by server.py before any tool call.
get_pool: Any = None


# ---------------------------------------------------------------------------
# create_routine
# Called the moment a caregiver request is received, before Stage 0 runs,
# so every request is visible in history even if immediately rejected.
# ---------------------------------------------------------------------------
async def create_routine(
    assisted_user_id: str,
    caregiver_id: str,
    raw_request: str,
) -> dict:
    """
    Insert a new routine row in status 'pending_caregiver_approval'.

    This is always the first write after a caregiver submits a request.
    The routine exists before Stage 0 runs — ensuring transparent history
    of every request, including instantly-blocked ones (architecture.md §6.2).

    Returns: { "id": str }
    """
    # Validate UUIDs before database call
    validate_uuid(assisted_user_id, "assisted_user_id")
    validate_uuid(caregiver_id, "caregiver_id")
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO routines (assisted_user_id, caregiver_id, raw_request)
            VALUES ($1::uuid, $2::uuid, $3)
            RETURNING id
            """,
            assisted_user_id,
            caregiver_id,
            raw_request,
        )
        return {"id": str(row["id"])}


# ---------------------------------------------------------------------------
# save_routine_steps
# ---------------------------------------------------------------------------
async def save_routine_steps(
    routine_id: str,
    steps: list[dict],
) -> dict:
    """
    Upsert the steps for a routine after the Communication Agent has rewritten them.

    Each step dict must contain:
        step_number     int
        original_text   str   (Planning Agent output)
        simplified_text str   (Communication Agent output)

    Returns: { "saved": int }  (number of steps written)
    """
    validate_uuid(routine_id, "routine_id")
    
    # Validate step structure
    for i, step in enumerate(steps):
        if "step_number" not in step:
            raise ValueError(f"Step {i}: missing required field 'step_number'")
        if "original_text" not in step:
            raise ValueError(f"Step {i}: missing required field 'original_text'")
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Verify routine exists before deleting steps
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM routines WHERE id = $1::uuid)",
                routine_id,
            )
            if not exists:
                raise ValueError(f"Routine '{routine_id}' does not exist")
            
            # Clear any previous steps (e.g., on a retry) before re-inserting.
            await conn.execute(
                "DELETE FROM routine_steps WHERE routine_id = $1::uuid",
                routine_id,
            )
            await conn.executemany(
                """
                INSERT INTO routine_steps
                    (routine_id, step_number, original_text, simplified_text)
                VALUES ($1::uuid, $2, $3, $4)
                """,
                [
                    (
                        routine_id,
                        s["step_number"],
                        s["original_text"],
                        s.get("simplified_text"),
                    )
                    for s in steps
                ],
            )
        return {"saved": len(steps)}


# ---------------------------------------------------------------------------
# update_routine_status
# Used to move a routine to 'rejected' (gate or semantic review block)
# or back to 'pending_caregiver_approval' with enriched metadata after the
# graph completes successfully.
# ---------------------------------------------------------------------------
async def update_routine_status(
    routine_id: str,
    status: str,
    safety_verdict: str | None = None,
    safety_reason: str | None = None,
    title: str | None = None,
    scheduled_time: str | None = None,
    recurrence: str | None = None,
) -> dict:
    """
    Update a routine's status and optional metadata fields.

    status must be one of: pending_caregiver_approval | active | rejected | archived.
    The CHECK constraint on the routines table enforces this at the DB level.

    scheduled_time, if provided, must be 'HH:MM' (24-hour).

    Returns: { "id": str, "status": str }
    """
    validate_uuid(routine_id, "routine_id")
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE routines
            SET    status          = $2,
                   safety_verdict  = COALESCE($3, safety_verdict),
                   safety_reason   = COALESCE($4, safety_reason),
                   title           = COALESCE($5, title),
                   scheduled_time  = COALESCE($6::time, scheduled_time),
                   recurrence      = COALESCE($7, recurrence),
                   reviewed_at     = CASE WHEN $2 IN ('rejected') THEN now()
                                          ELSE reviewed_at END
            WHERE  id = $1::uuid
            RETURNING id, status
            """,
            routine_id,
            status,
            safety_verdict,
            safety_reason,
            title,
            scheduled_time,
            recurrence,
        )
        return {"id": str(row["id"]), "status": row["status"]}


# ---------------------------------------------------------------------------
# approve_routine
# The ONLY code path that can set status = 'active'.
# Called exclusively from POST /internal/routines/{id}/approve.
# ---------------------------------------------------------------------------
async def approve_routine(routine_id: str, caregiver_id: str) -> dict:
    """
    Activate a routine — set status='active', record activated_at.

    This is the single gate between a draft and what Maria sees.
    Only application code (FastAPI router) calls this; no Agent can.

    CRITICAL SECURITY: Only approves routines that passed safety review
    (safety_verdict = 'approved'). This prevents activation of routines
    that were rejected by safety review then manually reset to pending.

    Returns: { "id": str, "status": "active", "activated_at": str }

    Raises:
        ValueError: if the routine is not in 'pending_caregiver_approval'
            state, does not belong to this caregiver, or did not pass
            safety review.
    """
    validate_uuid(routine_id, "routine_id")
    validate_uuid(caregiver_id, "caregiver_id")
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE routines
            SET    status       = 'active',
                   reviewed_at  = now(),
                   activated_at = now()
            WHERE  id           = $1::uuid
              AND  caregiver_id = $2::uuid
              AND  status       = 'pending_caregiver_approval'
              AND  safety_verdict = 'approved'
            RETURNING id, status, activated_at
            """,
            routine_id,
            caregiver_id,
        )
        if row is None:
            raise ValueError(
                f"Routine '{routine_id}' cannot be approved: not found, "
                f"wrong caregiver, not in pending_caregiver_approval state, "
                f"or did not pass safety review (safety_verdict != 'approved')."
            )
        return {
            "id": str(row["id"]),
            "status": row["status"],
            "activated_at": row["activated_at"].isoformat(),
        }


# ---------------------------------------------------------------------------
# reject_routine
# ---------------------------------------------------------------------------
async def reject_routine(
    routine_id: str,
    caregiver_id: str,
    reason: str | None = None,
) -> dict:
    """
    Reject a routine — set status='rejected', record reviewed_at.

    Can reject from 'pending_caregiver_approval' only (the caregiver
    explicitly rejects a draft). Gate-blocked and semantic-review-blocked
    routines are rejected via update_routine_status instead.

    Returns: { "id": str, "status": "rejected" }
    """
    validate_uuid(routine_id, "routine_id")
    validate_uuid(caregiver_id, "caregiver_id")
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE routines
            SET    status        = 'rejected',
                   safety_reason = COALESCE($3, safety_reason),
                   reviewed_at   = now()
            WHERE  id            = $1::uuid
              AND  caregiver_id  = $2::uuid
              AND  status        = 'pending_caregiver_approval'
            RETURNING id, status
            """,
            routine_id,
            caregiver_id,
            reason,
        )
        if row is None:
            raise ValueError(
                f"Routine '{routine_id}' cannot be rejected: not found, "
                f"wrong caregiver, or not in pending_caregiver_approval state."
            )
        return {"id": str(row["id"]), "status": row["status"]}


# ---------------------------------------------------------------------------
# get_today_routines
# ---------------------------------------------------------------------------
async def get_today_routines(assisted_user_id: str, date: str) -> list[dict]:
    """
    Return active routines scheduled for the given date, with their steps.

    date must be 'YYYY-MM-DD'. The query uses scheduled_time (TIME) and
    does NOT filter by time-of-day — returning all active routines for the
    day so the frontend can decide which one to show based on the clock.

    Returns a list of routine dicts, each with a nested 'steps' list.
    Steps are in step_number order.
    """
    validate_uuid(assisted_user_id, "assisted_user_id")
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        routines = await conn.fetch(
            """
            SELECT r.id,
                   r.title,
                   to_char(r.scheduled_time, 'HH24:MI') AS scheduled_time,
                   r.recurrence,
                   r.status,
                   -- Exclude if already completed today
                   NOT EXISTS (
                       SELECT 1 FROM routine_completions rc
                       WHERE  rc.routine_id      = r.id
                         AND  rc.occurrence_date = $2::date
                   ) AS not_yet_completed
            FROM   routines r
            WHERE  r.assisted_user_id = $1::uuid
              AND  r.status = 'active'
            ORDER BY r.scheduled_time NULLS LAST
            """,
            assisted_user_id,
            date,
        )

        result = []
        for r in routines:
            steps = await conn.fetch(
                """
                SELECT step_number, simplified_text
                FROM   routine_steps
                WHERE  routine_id = $1::uuid
                ORDER BY step_number
                """,
                str(r["id"]),
            )
            result.append(
                {
                    "id": str(r["id"]),
                    "title": r["title"],
                    "scheduled_time": r["scheduled_time"],
                    "recurrence": r["recurrence"],
                    "status": r["status"],
                    "not_yet_completed": r["not_yet_completed"],
                    "steps": [
                        {
                            "step_number": s["step_number"],
                            "text": s["simplified_text"],
                        }
                        for s in steps
                    ],
                }
            )
        return result


# ---------------------------------------------------------------------------
# mark_routine_complete
# ---------------------------------------------------------------------------
async def mark_routine_complete(routine_id: str, occurrence_date: str) -> dict:
    """
    Record that the assisted user completed a routine for a given date.

    occurrence_date must be 'YYYY-MM-DD'. The UNIQUE constraint on
    (routine_id, occurrence_date) means this is idempotent — re-tapping
    Done is safe.

    Returns: { "routine_id": str, "occurrence_date": str, "completed": True }
    
    Raises:
        ValueError: If routine_id does not exist
    """
    validate_uuid(routine_id, "routine_id")
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            INSERT INTO routine_completions (routine_id, occurrence_date)
            VALUES ($1::uuid, $2::date)
            ON CONFLICT (routine_id, occurrence_date) DO NOTHING
            RETURNING routine_id
            """,
            routine_id,
            occurrence_date,
        )
        # Verify routine exists if no row was inserted due to conflict or error
        if "INSERT" not in result:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM routines WHERE id = $1::uuid)",
                routine_id,
            )
            if not exists:
                raise ValueError(f"Routine '{routine_id}' does not exist")
        
        return {
            "routine_id": routine_id,
            "occurrence_date": occurrence_date,
            "completed": True,
        }


# ---------------------------------------------------------------------------
# create_help_alert
# ---------------------------------------------------------------------------
async def create_help_alert(
    assisted_user_id: str,
    caregiver_id: str,
    category: str,
    message: str,
    source_note: str | None = None,
) -> dict:
    """
    Create a help alert in the caregiver's alert feed.

    Called by application code in BOTH branches of the Escalation Agent flow
    (architecture.md §7.6):
      - Rich branch: category and message come from the Escalation Agent.
      - Fallback branch: category='help_requested', message=source_note or default.

    In both cases, the alert's existence is guaranteed by deterministic
    application code — the agent's participation is enrichment only.

    Returns: { "id": str }
    """
    validate_uuid(assisted_user_id, "assisted_user_id")
    validate_uuid(caregiver_id, "caregiver_id")
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO alerts
                (assisted_user_id, caregiver_id, category, message, source_note)
            VALUES ($1::uuid, $2::uuid, $3, $4, $5)
            RETURNING id
            """,
            assisted_user_id,
            caregiver_id,
            category,
            message,
            source_note,
        )
        return {"id": str(row["id"])}


# ---------------------------------------------------------------------------
# get_alerts
# ---------------------------------------------------------------------------
async def get_alerts(caregiver_id: str) -> list[dict]:
    """
    Return all alerts for this caregiver, newest first.

    Includes open, acknowledged, and resolved alerts so the caregiver
    has a complete history. The frontend filters by status for display.

    Returns: list of alert dicts.
    """
    validate_uuid(caregiver_id, "caregiver_id")
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT a.id,
                   a.assisted_user_id,
                   a.category,
                   a.message,
                   a.source_note,
                   a.status,
                   a.created_at,
                   a.acknowledged_at,
                   au.name AS assisted_user_name
            FROM   alerts a
            JOIN   assisted_users au ON au.id = a.assisted_user_id
            WHERE  a.caregiver_id = $1::uuid
            ORDER BY a.created_at DESC
            """,
            caregiver_id,
        )
        return [
            {
                "id": str(r["id"]),
                "assisted_user_id": str(r["assisted_user_id"]),
                "assisted_user_name": r["assisted_user_name"],
                "category": r["category"],
                "message": r["message"],
                "source_note": r["source_note"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat(),
                "acknowledged_at": (
                    r["acknowledged_at"].isoformat()
                    if r["acknowledged_at"]
                    else None
                ),
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# acknowledge_alert
# ---------------------------------------------------------------------------
async def acknowledge_alert(
    alert_id: str,
    caregiver_id: str,
) -> dict:
    """
    Mark an alert as acknowledged by the caregiver.

    Idempotent — re-acknowledging an already-acknowledged alert returns
    the current state without error. Sets acknowledged_at timestamp if not
    already set; transitions status to 'acknowledged'.

    Returns: { "id": str, "status": "acknowledged", "acknowledged_at": str | null }
    """
    validate_uuid(alert_id, "alert_id")
    validate_uuid(caregiver_id, "caregiver_id")
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE alerts
            SET    status          = 'acknowledged',
                   acknowledged_at = COALESCE(acknowledged_at, now())
            WHERE  id              = $1::uuid
              AND  caregiver_id    = $2::uuid
            RETURNING id, status, acknowledged_at
            """,
            alert_id,
            caregiver_id,
        )
        if row is None:
            raise ValueError(
                f"Alert '{alert_id}' not found or does not belong to "
                f"caregiver '{caregiver_id}'."
            )
        return {
            "id": str(row["id"]),
            "status": row["status"],
            "acknowledged_at": (
                row["acknowledged_at"].isoformat()
                if row["acknowledged_at"]
                else None
            ),
        }


# ---------------------------------------------------------------------------
# log_safety_decision
# ---------------------------------------------------------------------------
async def log_safety_decision(
    routine_id: str,
    stage: str,
    decision: str,
    matched_categories: str | None = None,
    detail: str | None = None,
) -> dict:
    """
    Append a safety audit log entry.

    Called by application code after every gate evaluation (Stage 0) and
    after every semantic safety review result (Stage 2). Never called by
    an agent — the audit trail is always written by deterministic code
    (architecture.md §13).

    stage:    'deterministic_gate' | 'semantic_review'
    decision: 'pass' | 'block'

    Returns: { "id": str }
    """
    validate_uuid(routine_id, "routine_id")
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO safety_audit_log
                (routine_id, stage, decision, matched_categories, detail)
            VALUES ($1::uuid, $2, $3, $4, $5)
            RETURNING id
            """,
            routine_id,
            stage,
            decision,
            matched_categories,
            detail,
        )
        return {"id": str(row["id"])}
