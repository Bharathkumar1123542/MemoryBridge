"""
agent-backend.app.routers.caregiver
--------------------------------------
FastAPI router for caregiver-facing endpoints that are NOT routine actions.

Endpoints:
    GET  /internal/alerts                      — list open alerts
    POST /internal/alerts/{id}/acknowledge     — acknowledge an alert

Routine creation, approval, and rejection live in routers/routines.py.
The /today and /help endpoints live in routers/assisted.py.
"""

import logging

from fastapi import APIRouter, HTTPException, Request, status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["caregiver"])


# ---------------------------------------------------------------------------
# GET /internal/alerts
# ---------------------------------------------------------------------------

@router.get("/alerts")
async def list_alerts(request: Request):
    """
    Return all alerts for the authenticated caregiver, newest first.

    The caregiver_id is read from the X-Caregiver-Id header, which the
    Next.js BFF sets after resolving the session cookie.
    """
    caregiver_id = request.headers.get("X-Caregiver-Id", "")
    if not caregiver_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Caregiver-Id header is required.",
        )

    mcp = request.app.state.mcp
    try:
        alerts = await mcp.get_alerts(caregiver_id=caregiver_id)
    except Exception as exc:
        logger.error("get_alerts failed caregiver_id=%s: %s", caregiver_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not retrieve alerts.",
        ) from exc

    return {"alerts": alerts}


# ---------------------------------------------------------------------------
# POST /internal/alerts/{id}/acknowledge
# ---------------------------------------------------------------------------

@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, request: Request):
    """
    Mark an alert as acknowledged by the caregiver.

    Idempotent — acknowledging an already-acknowledged alert is a no-op.
    """
    caregiver_id = request.headers.get("X-Caregiver-Id", "")
    if not caregiver_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Caregiver-Id header is required.",
        )

    mcp = request.app.state.mcp
    try:
        result = await mcp.acknowledge_alert(
            alert_id=alert_id,
            caregiver_id=caregiver_id,
        )
    except Exception as exc:
        logger.error(
            "acknowledge_alert failed alert_id=%s: %s", alert_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not acknowledge alert.",
        ) from exc

    return {
        "id": alert_id,
        "status": result.get("status", "acknowledged"),
    }
