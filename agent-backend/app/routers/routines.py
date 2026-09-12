"""
agent-backend.app.routers.routines
------------------------------------
FastAPI router for routine management endpoints.

Implements the pipeline described in architecture.md §7 and
the endpoint specs in implementation.md §10.

Endpoints:
    POST   /internal/routines                  — create + run pipeline
    GET    /internal/routines                  — list all routines
    POST   /internal/routines/{id}/approve     — caregiver approve
    POST   /internal/routines/{id}/reject      — caregiver reject

Pipeline stages (architecture.md §7):
    Stage 0: Deterministic gate (gate.py)       — no Bedrock calls if blocked
    Stage 1: Routine Planning Agent             — via Strands Graph
    Stage 2: Semantic Safety Reviewer           — via Strands Graph (conditional)
    Stage 3: Dementia-Friendly Communication    — via Strands Graph (conditional)

All write operations go through the MCP client — no router ever touches
the database directly (architecture.md §1 Principle 4).
"""

import json
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ..agents.graph import build_routine_graph
from ..gate.gate import evaluate_deterministic_gate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["routines"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class CreateRoutineRequest(BaseModel):
    raw_request: str
    assisted_user_id: str
    caregiver_id: str


class RejectRoutineRequest(BaseModel):
    reason: str | None = None


# ---------------------------------------------------------------------------
# Output parsers — extract structured fields from agent text responses
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(r'"title"\s*:\s*"([^"]+)"', re.IGNORECASE)
_TIME_RE = re.compile(r'"scheduled_time"\s*:\s*"([^"]+)"', re.IGNORECASE)
_RECURRENCE_RE = re.compile(r'"recurrence"\s*:\s*"([^"]+)"', re.IGNORECASE)


def _parse_plan_output(text: str) -> dict:
    """
    Extract planning fields from the Routine Planning Agent's response.

    The agent is instructed to return structured fields. We attempt a JSON
    parse first; fall back to regex extraction for title, scheduled_time,
    recurrence. Steps are extracted from JSON 'steps' key or enumerated lines.

    Returns a dict with keys: title, scheduled_time, recurrence, steps (list[str]).
    """
    # Try JSON parse from a code block or raw JSON
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw_json = json_match.group(1) if json_match else text

    try:
        data = json.loads(raw_json)
        steps_raw = data.get("steps", [])
        if isinstance(steps_raw, list):
            steps = [
                s.get("text", s) if isinstance(s, dict) else str(s)
                for s in steps_raw
            ]
        else:
            steps = []
        return {
            "title": str(data.get("title", "Untitled routine")),
            "scheduled_time": str(data.get("scheduled_time", "09:00")),
            "recurrence": str(data.get("recurrence", "daily")),
            "steps": steps,
        }
    except (json.JSONDecodeError, ValueError):
        pass

    # Regex fallback
    title_m = _TITLE_RE.search(text)
    time_m = _TIME_RE.search(text)
    rec_m = _RECURRENCE_RE.search(text)
    # Naive step extraction: numbered lines
    step_lines = re.findall(r"^\s*\d+[.)]\s*(.+)$", text, re.MULTILINE)
    return {
        "title": title_m.group(1) if title_m else "Untitled routine",
        "scheduled_time": time_m.group(1) if time_m else "09:00",
        "recurrence": rec_m.group(1) if rec_m else "daily",
        "steps": step_lines,
    }


def _parse_communicate_output(text: str, original_steps: list[str]) -> list[str]:
    """
    Extract rewritten steps from the Communication Agent's response.

    Falls back to the original (plan-stage) steps if parsing fails, so that
    a communication agent failure is non-fatal to the pipeline.
    """
    # Try numbered lines first
    numbered = re.findall(r"^\s*\d+[.)]\s*(.+)$", text, re.MULTILINE)
    if numbered:
        return [s.strip() for s in numbered]

    # Try JSON list
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(s) for s in data]
        if isinstance(data, dict) and "steps" in data:
            return [str(s) for s in data["steps"]]
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: return original plan steps
    logger.warning("_parse_communicate_output: could not parse — using original steps.")
    return original_steps


def _is_graph_approved(graph_result) -> bool:
    """
    Return True if the communicate node ran (graph reached Stage 3).

    If 'communicate' is absent from results, the safety review rejected it.
    """
    try:
        results = graph_result.results if hasattr(graph_result, "results") else {}
        return "communicate" in results
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# POST /internal/routines
# ---------------------------------------------------------------------------

@router.post("/routines", status_code=status.HTTP_201_CREATED)
async def create_routine(body: CreateRoutineRequest, request: Request):
    """
    Create a new routine by running the full pipeline:

        Stage 0: Deterministic gate
        Stage 1: Routine Planning Agent
        Stage 2: Semantic Safety Reviewer
        Stage 3: Dementia-Friendly Communication Agent

    Returns a JSON object describing the final state of the routine.
    Blocked requests (Stages 0 or 2) return status='rejected' with a reason.
    Approved requests return status='pending_caregiver_approval' with steps.
    """
    mcp = request.app.state.mcp

    # ------------------------------------------------------------------
    # Stage 0 — Deterministic gate (zero Bedrock calls on block)
    # ------------------------------------------------------------------
    gate_result = evaluate_deterministic_gate(body.raw_request)

    if not gate_result.passed:
        # Create a stub routine row so the rejection is visible in history
        try:
            routine = await mcp.create_routine(
                assisted_user_id=body.assisted_user_id,
                caregiver_id=body.caregiver_id,
                raw_request=body.raw_request,
            )
            routine_id = routine.get("id", "unknown")
            await mcp.update_routine_status(
                routine_id=routine_id,
                status="rejected",
                safety_verdict="rejected",
                safety_reason=gate_result.rejection_message,
            )
            await mcp.log_safety_decision(
                routine_id=routine_id,
                stage="deterministic_gate",
                decision="block",
                matched_categories=", ".join(gate_result.matched_categories),
                detail=f"Matched terms: {gate_result.matched_terms}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Stage 0 audit write failed: %s", exc)
            routine_id = "unavailable"

        logger.info(
            "Stage 0 blocked routine_id=%s categories=%s",
            routine_id,
            gate_result.matched_categories,
        )
        return {
            "id": routine_id,
            "status": "rejected",
            "reason": gate_result.rejection_message,
        }

    # ------------------------------------------------------------------
    # Create pending routine row (before Bedrock calls)
    # ------------------------------------------------------------------
    try:
        routine = await mcp.create_routine(
            assisted_user_id=body.assisted_user_id,
            caregiver_id=body.caregiver_id,
            raw_request=body.raw_request,
        )
        routine_id = routine.get("id")
        if not routine_id:
            raise ValueError("create_routine returned no id")
    except Exception as exc:
        logger.error("create_routine MCP call failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable. Please try again.",
        ) from exc

    await mcp.log_safety_decision(
        routine_id=routine_id,
        stage="deterministic_gate",
        decision="pass",
        matched_categories=None,
        detail=None,
    )

    # ------------------------------------------------------------------
    # Stages 1–3 — Strands Graph (plan → safety_review → communicate)
    # ------------------------------------------------------------------
    try:
        planning_tools = mcp.get_planning_tools()
        graph = build_routine_graph(planning_tools)

        import asyncio
        loop = asyncio.get_event_loop()
        graph_result = await loop.run_in_executor(
            None, lambda: graph(body.raw_request)
        )
    except Exception as exc:
        logger.error("Graph execution failed for routine_id=%s: %s", routine_id, exc)
        await mcp.update_routine_status(
            routine_id=routine_id,
            status="rejected",
            safety_verdict="rejected",
            safety_reason="temporarily_unavailable",
        )
        return {
            "id": routine_id,
            "status": "rejected",
            "reason": "The routine pipeline is temporarily unavailable. Please try again.",
        }

    # ------------------------------------------------------------------
    # Stage 2 result: was the routine approved by the safety reviewer?
    # ------------------------------------------------------------------
    try:
        safety_review_result = graph_result.results.get("safety_review")
        safety_text = str(safety_review_result.result) if safety_review_result else ""
    except Exception:
        safety_text = ""

    graph_approved = _is_graph_approved(graph_result)

    await mcp.log_safety_decision(
        routine_id=routine_id,
        stage="semantic_review",
        decision="pass" if graph_approved else "block",
        matched_categories=None,
        detail=safety_text[:500] if safety_text else None,
    )

    if not graph_approved:
        # Extract reason from safety_review output
        reason_match = re.search(r"REASON:\s*(.+)", safety_text, re.IGNORECASE)
        reason = reason_match.group(1).strip() if reason_match else "Request rejected by safety review."

        await mcp.update_routine_status(
            routine_id=routine_id,
            status="rejected",
            safety_verdict="rejected",
            safety_reason=reason,
        )
        logger.info("Stage 2 rejected routine_id=%s", routine_id)
        return {
            "id": routine_id,
            "status": "rejected",
            "reason": reason,
        }

    # ------------------------------------------------------------------
    # Stage 3 result: extract plan + communication rewrites
    # ------------------------------------------------------------------
    try:
        plan_result = graph_result.results.get("plan")
        plan_text = str(plan_result.result) if plan_result else body.raw_request
        plan_data = _parse_plan_output(plan_text)
    except Exception as exc:
        logger.warning("Plan output parsing failed: %s", exc)
        plan_data = {
            "title": "Routine",
            "scheduled_time": "09:00",
            "recurrence": "daily",
            "steps": [],
        }

    try:
        comms_result = graph_result.results.get("communicate")
        comms_text = str(comms_result.result) if comms_result else ""
        simplified_steps = _parse_communicate_output(comms_text, plan_data["steps"])
    except Exception as exc:
        logger.warning("Communication output parsing failed: %s", exc)
        simplified_steps = plan_data["steps"]

    # ------------------------------------------------------------------
    # Persist structured output
    # ------------------------------------------------------------------
    steps_payload = [
        {
            "step_number": i + 1,
            "original_text": plan_data["steps"][i] if i < len(plan_data["steps"]) else s,
            "simplified_text": s,
        }
        for i, s in enumerate(simplified_steps)
    ]

    try:
        await mcp.update_routine_status(
            routine_id=routine_id,
            status="pending_caregiver_approval",
            safety_verdict="approved",
            safety_reason=None,
            title=plan_data["title"],
            scheduled_time=plan_data["scheduled_time"],
            recurrence=plan_data["recurrence"],
        )
        if steps_payload:
            await mcp.save_routine_steps(routine_id=routine_id, steps=steps_payload)
    except Exception as exc:
        logger.error("Failed to persist routine results: %s", exc)

    logger.info(
        "Routine pipeline complete: routine_id=%s status=pending_caregiver_approval",
        routine_id,
    )

    return {
        "id": routine_id,
        "status": "pending_caregiver_approval",
        "title": plan_data["title"],
        "scheduled_time": plan_data["scheduled_time"],
        "recurrence": plan_data["recurrence"],
        "steps": [
            {"step_number": s["step_number"], "text": s["simplified_text"]}
            for s in steps_payload
        ],
    }


# ---------------------------------------------------------------------------
# GET /internal/routines
# ---------------------------------------------------------------------------

@router.get("/routines")
async def list_routines(request: Request, assisted_user_id: str):
    """
    Return all routines for the given assisted user, newest first.

    Includes rejected entries with their reason (architecture.md §6.2 —
    transparency: caregivers can see why a request was blocked).
    """
    mcp = request.app.state.mcp
    try:
        routines = await mcp.get_today_routines(
            assisted_user_id=assisted_user_id,
            date=datetime.now(timezone.utc).date().isoformat(),
        )
    except Exception as exc:
        logger.error("list_routines failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not retrieve routines.",
        ) from exc

    return {"routines": routines}


# ---------------------------------------------------------------------------
# POST /internal/routines/{id}/approve
# ---------------------------------------------------------------------------

@router.post("/routines/{routine_id}/approve")
async def approve_routine(routine_id: str, request: Request):
    """
    Caregiver approves a pending routine. Sets status to 'active'.

    This is the ONLY code path in the system that can set status='active'
    (architecture.md §6.2, ADR-002).
    """
    # Extract caregiver_id from the verified session headers
    caregiver_id = request.headers.get("X-Caregiver-Id", "")
    if not caregiver_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Caregiver-Id header is required.",
        )

    mcp = request.app.state.mcp
    try:
        result = await mcp.approve_routine(
            routine_id=routine_id,
            caregiver_id=caregiver_id,
        )
    except Exception as exc:
        logger.error("approve_routine failed routine_id=%s: %s", routine_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not approve routine.",
        ) from exc

    return {"id": routine_id, "status": result.get("status", "active")}


# ---------------------------------------------------------------------------
# POST /internal/routines/{id}/reject
# ---------------------------------------------------------------------------

@router.post("/routines/{routine_id}/reject")
async def reject_routine(routine_id: str, body: RejectRoutineRequest, request: Request):
    """
    Caregiver rejects a pending routine.
    """
    caregiver_id = request.headers.get("X-Caregiver-Id", "")
    if not caregiver_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Caregiver-Id header is required.",
        )

    mcp = request.app.state.mcp
    try:
        result = await mcp.reject_routine(
            routine_id=routine_id,
            caregiver_id=caregiver_id,
            reason=body.reason,
        )
    except Exception as exc:
        logger.error("reject_routine failed routine_id=%s: %s", routine_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not reject routine.",
        ) from exc

    return {"id": routine_id, "status": result.get("status", "rejected")}
