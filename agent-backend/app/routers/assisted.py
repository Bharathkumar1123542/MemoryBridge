"""
agent-backend.app.routers.assisted
-------------------------------------
FastAPI router for Maria's (assisted user) /today interface endpoints.

Endpoints:
    GET  /internal/today                         — current routine for today
    POST /internal/routines/{id}/complete        — mark today's routine done
    POST /internal/help                          — "Help me" button

The /help endpoint implements fail-open design (architecture.md §7.6):
    - The Escalation Agent runs with a hard 3-second timeout.
    - If the agent fails or times out, the alert is STILL created using
      Maria's raw note. The alert's existence never depends on the agent.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ..agents.escalation import invoke_escalation_agent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["assisted"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class HelpRequest(BaseModel):
    note: str | None = None
    routine_title: str | None = None  # optional: which routine Maria was on


class CompleteRoutineBody(BaseModel):
    occurrence_date: str | None = None  # defaults to today if absent


# ---------------------------------------------------------------------------
# GET /internal/today
# ---------------------------------------------------------------------------

@router.get("/today")
async def get_today(request: Request, assisted_user_id: str):
    """
    Return the current routine due today for the assisted user.

    Response:
        { "routine": { id, title, steps: [...] } | null }

    A null routine means there is nothing scheduled right now — Maria sees
    "Nothing to do right now. Check back later."
    """
    mcp = request.app.state.mcp
    today = datetime.now(timezone.utc).date().isoformat()

    try:
        routines = await mcp.get_today_routines(
            assisted_user_id=assisted_user_id,
            date=today,
        )
    except Exception as exc:
        logger.error("get_today_routines failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not retrieve today's routines.",
        ) from exc

    # Return the first active routine, or null
    active = next(
        (r for r in routines if r.get("status") == "active"),
        None,
    )

    if active is None:
        return {"routine": None}

    return {
        "routine": {
            "id": active.get("id"),
            "title": active.get("title", "Today's Routine"),
            "steps": active.get("steps", []),
        }
    }


# ---------------------------------------------------------------------------
# POST /internal/routines/{id}/complete
# ---------------------------------------------------------------------------

@router.post("/routines/{routine_id}/complete")
async def complete_routine(
    routine_id: str,
    body: CompleteRoutineBody,
    request: Request,
):
    """
    Mark a routine as completed for today's occurrence.

    Idempotent — marking the same routine complete twice returns success.
    """
    mcp = request.app.state.mcp
    occurrence_date = (
        body.occurrence_date
        or datetime.now(timezone.utc).date().isoformat()
    )

    try:
        await mcp.mark_routine_complete(
            routine_id=routine_id,
            occurrence_date=occurrence_date,
        )
    except Exception as exc:
        logger.error(
            "mark_routine_complete failed routine_id=%s: %s", routine_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not record completion.",
        ) from exc

    return {"id": routine_id, "completed": True}


# ---------------------------------------------------------------------------
# POST /internal/help
# ---------------------------------------------------------------------------

@router.post("/help")
async def help_me(body: HelpRequest, request: Request):
    """
    Handle Maria's "Help me" button tap.

    Fail-open design (architecture.md §7.6):
        1. Run the Escalation Agent with a 3-second hard timeout.
        2. Whether the agent succeeds or falls back, create the alert via MCP.
        3. The alert is ALWAYS created — the agent's success only affects
           how informative the category + summary are.

    Required headers (set by web/lib/session.ts via BFF):
        X-Assisted-User-Id  — the assisted user's ID
        X-Caregiver-Id      — the caregiver who should receive the alert
    """
    assisted_user_id = request.headers.get("X-Assisted-User-Id", "")
    caregiver_id = request.headers.get("X-Caregiver-Id", "")

    if not assisted_user_id or not caregiver_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Assisted-User-Id and X-Caregiver-Id headers are required.",
        )

    # ------------------------------------------------------------------
    # Escalation Agent — 3-second timeout, always falls back (never raises)
    # ------------------------------------------------------------------
    escalation = await invoke_escalation_agent(
        note=body.note,
        routine_title=body.routine_title,
    )

    logger.info(
        "Escalation Agent result: category=%s from_fallback=%s",
        escalation.category,
        escalation.from_fallback,
    )

    # ------------------------------------------------------------------
    # Create the alert via MCP — fail-open: if this write fails, we log
    # the error but still return { notified: true } because the failure
    # is an infrastructure issue, not a user error. The caregiver will
    # see the alert whenever the DB connection recovers.
    # ------------------------------------------------------------------
    mcp = request.app.state.mcp
    try:
        await mcp.create_help_alert(
            assisted_user_id=assisted_user_id,
            caregiver_id=caregiver_id,
            category=escalation.category,
            message=escalation.summary,
            source_note=body.note,
        )
        logger.info("Help alert created for assisted_user_id=%s", assisted_user_id)
    except Exception as exc:
        # Log but do NOT raise — fail-open (architecture.md §7.6)
        logger.error(
            "create_help_alert MCP call failed (alert may be delayed): %s", exc
        )

    return {"notified": True}
