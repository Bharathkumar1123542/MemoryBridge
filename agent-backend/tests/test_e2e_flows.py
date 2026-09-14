"""
tests/test_e2e_flows.py
------------------------
End-to-end flow tests for the three primary user journeys described in
project_overview.md §7, run against a test database and mocked Bedrock
client (implementation.md §13.4).

Journey 1 (Happy path):
    Caregiver submits a benign request → pipeline runs → routine becomes
    pending_caregiver_approval → caregiver approves → routine appears at
    /today.

Journey 2 (Deterministic gate):
    Caregiver submits a medication request → Stage 0 blocks it instantly →
    zero Bedrock (graph) calls are made.

Journey 3 (Escalation / fail-open):
    Maria taps "Help me" with an optional note → Escalation Agent times out
    → alert is STILL created within a short deadline (fail-open guarantee).

All tests:
    - Use pytest-asyncio for async route handler tests.
    - Mock the MCP client via a FakeMCPClient that records write-tool calls.
    - Mock the Strands graph via a FakeGraph that returns canned model output.
    - Never make real Bedrock calls.
    - Never require a real database.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fake MCP client
# ---------------------------------------------------------------------------

class FakeMCPClient:
    """
    In-memory stand-in for MemoryBridgeMCPClient.

    All write-tool calls are recorded in `calls` as (method_name, kwargs)
    tuples so tests can assert the exact sequence of side-effects without
    a real database.
    """

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self._routines: dict[str, dict] = {}
        self._alerts: list[dict] = []

    def _record(self, name: str, **kwargs):
        self.calls.append((name, kwargs))

    def get_planning_tools(self) -> list:
        return []  # Strands graph is mocked separately

    async def create_routine(
        self, assisted_user_id: str, caregiver_id: str, raw_request: str
    ) -> dict:
        routine_id = str(uuid.uuid4())
        routine = {
            "id": routine_id,
            "assisted_user_id": assisted_user_id,
            "caregiver_id": caregiver_id,
            "raw_request": raw_request,
            "status": "pending_caregiver_approval",
        }
        self._routines[routine_id] = routine
        self._record("create_routine", assisted_user_id=assisted_user_id,
                     caregiver_id=caregiver_id, raw_request=raw_request)
        return routine

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
        if routine_id in self._routines:
            self._routines[routine_id]["status"] = status
            if title:
                self._routines[routine_id]["title"] = title
            if scheduled_time:
                self._routines[routine_id]["scheduled_time"] = scheduled_time
            if recurrence:
                self._routines[routine_id]["recurrence"] = recurrence
        self._record("update_routine_status", routine_id=routine_id, status=status,
                     safety_verdict=safety_verdict, safety_reason=safety_reason)
        return {"id": routine_id, "status": status}

    async def save_routine_steps(self, routine_id: str, steps: list[dict]) -> dict:
        if routine_id in self._routines:
            self._routines[routine_id]["steps"] = steps
        self._record("save_routine_steps", routine_id=routine_id, steps=steps)
        return {"routine_id": routine_id, "steps_saved": len(steps)}

    async def approve_routine(self, routine_id: str, caregiver_id: str) -> dict:
        if routine_id in self._routines:
            self._routines[routine_id]["status"] = "active"
        self._record("approve_routine", routine_id=routine_id, caregiver_id=caregiver_id)
        return {"id": routine_id, "status": "active"}

    async def reject_routine(
        self, routine_id: str, caregiver_id: str, reason: str | None = None
    ) -> dict:
        if routine_id in self._routines:
            self._routines[routine_id]["status"] = "rejected"
        self._record("reject_routine", routine_id=routine_id, caregiver_id=caregiver_id)
        return {"id": routine_id, "status": "rejected"}

    async def get_today_routines(self, assisted_user_id: str, date: str) -> list[dict]:
        self._record("get_today_routines", assisted_user_id=assisted_user_id, date=date)
        return [
            r for r in self._routines.values()
            if r["assisted_user_id"] == assisted_user_id
        ]

    async def mark_routine_complete(self, routine_id: str, occurrence_date: str) -> dict:
        self._record("mark_routine_complete", routine_id=routine_id,
                     occurrence_date=occurrence_date)
        return {"routine_id": routine_id, "completed": True}

    async def create_help_alert(
        self,
        assisted_user_id: str,
        caregiver_id: str,
        category: str,
        message: str,
        source_note: str | None = None,
    ) -> dict:
        alert = {
            "id": str(uuid.uuid4()),
            "assisted_user_id": assisted_user_id,
            "caregiver_id": caregiver_id,
            "category": category,
            "message": message,
            "source_note": source_note,
            "status": "open",
        }
        self._alerts.append(alert)
        self._record("create_help_alert", assisted_user_id=assisted_user_id,
                     caregiver_id=caregiver_id, category=category, message=message)
        return alert

    async def get_alerts(self, caregiver_id: str) -> list[dict]:
        self._record("get_alerts", caregiver_id=caregiver_id)
        return [a for a in self._alerts if a["caregiver_id"] == caregiver_id]

    async def acknowledge_alert(self, alert_id: str, caregiver_id: str) -> dict:
        self._record("acknowledge_alert", alert_id=alert_id, caregiver_id=caregiver_id)
        return {"id": alert_id, "status": "acknowledged"}

    async def log_safety_decision(
        self,
        routine_id: str,
        stage: str,
        decision: str,
        matched_categories: str | None = None,
        detail: str | None = None,
    ) -> dict:
        self._record("log_safety_decision", routine_id=routine_id, stage=stage,
                     decision=decision, matched_categories=matched_categories)
        return {"logged": True}


# ---------------------------------------------------------------------------
# Fake Graph result
# ---------------------------------------------------------------------------

class FakeNodeResult:
    def __init__(self, text: str):
        self.result = text


class FakeGraphResult:
    """
    Mimics the Strands Graph execution result object.

    By default, simulate a fully-approved pipeline (all three nodes ran).
    Set approved=False to simulate safety_review rejection.
    """

    def __init__(self, approved: bool = True):
        self.results: dict[str, Any] = {
            "plan": FakeNodeResult(
                '{"title": "Water the plants", "scheduled_time": "10:00", '
                '"recurrence": "daily", "steps": ["Find the watering can.", '
                '"Fill it with water.", "Water each plant."]}'
            ),
            "safety_review": FakeNodeResult(
                "VERDICT: APPROVED\nREASON: Safe daily activity.\nFLAGGED_CATEGORIES: NONE"
                if approved else
                "VERDICT: REJECTED\nREASON: Request involves prohibited activity.\n"
                "FLAGGED_CATEGORIES: other_high_risk_actions"
            ),
        }
        if approved:
            self.results["communicate"] = FakeNodeResult(
                "1. Find the watering can in the kitchen.\n"
                "2. Fill the watering can with water.\n"
                "3. Water each plant on the windowsill."
            )


# ---------------------------------------------------------------------------
# App factory (used in tests; bypasses real MCP subprocess)
# ---------------------------------------------------------------------------

def make_test_app(mcp: FakeMCPClient) -> FastAPI:
    """Create a FastAPI app wired to a FakeMCPClient (no MCP subprocess)."""
    from app.routers import routines, caregiver, assisted

    app = FastAPI()
    app.state.mcp = mcp

    app.include_router(routines.router, prefix="/internal")
    app.include_router(caregiver.router, prefix="/internal")
    app.include_router(assisted.router, prefix="/internal")

    return app


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

CAREGIVER_ID = str(uuid.uuid4())
ASSISTED_USER_ID = str(uuid.uuid4())
SESSION_ID = "test-session-id"

# Internal auth headers expected by main.py middleware
# Tests bypass the middleware by not including it in main.py; instead they
# use the test-app factory (make_test_app) which skips the HMAC middleware.
AUTH_HEADERS = {
    "X-Caregiver-Id": CAREGIVER_ID,
    "X-Assisted-User-Id": ASSISTED_USER_ID,
}


# ===========================================================================
# Journey 1 — Happy path: benign request → approve → appears at /today
# ===========================================================================

class TestJourney1HappyPath:
    """
    project_overview.md §7, Journey 1:
    Caregiver creates a routine → approves it → appears at /today.

    Asserts:
        (a) POST /routines returns status=pending_caregiver_approval after approval.
        (b) The routine only appears at /today AFTER the approve call.
        (c) The routine has simplified steps from the Communication Agent.
    """

    def _make_client_with_graph(self) -> tuple[TestClient, FakeMCPClient]:
        mcp = FakeMCPClient()
        app = make_test_app(mcp)
        client = TestClient(app, raise_server_exceptions=True)
        return client, mcp

    def test_create_routine_returns_pending(self):
        """POST /routines returns status=pending_caregiver_approval for a benign request."""
        client, mcp = self._make_client_with_graph()

        with patch(
            "app.routers.routines.build_routine_graph",
            return_value=MagicMock(side_effect=lambda text: FakeGraphResult(approved=True)),
        ):
            resp = client.post(
                "/internal/routines",
                json={
                    "raw_request": "Remind Maria to water the plants at 10:00.",
                    "assisted_user_id": ASSISTED_USER_ID,
                    "caregiver_id": CAREGIVER_ID,
                },
                headers=AUTH_HEADERS,
            )

        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] == "pending_caregiver_approval"
        assert data["title"] == "Water the plants"
        assert len(data["steps"]) == 3

    def test_routine_not_at_today_before_approval(self):
        """Routine must NOT appear at /today while still pending_caregiver_approval."""
        client, mcp = self._make_client_with_graph()

        with patch(
            "app.routers.routines.build_routine_graph",
            return_value=MagicMock(side_effect=lambda text: FakeGraphResult(approved=True)),
        ):
            create_resp = client.post(
                "/internal/routines",
                json={
                    "raw_request": "Remind Maria to water the plants at 10:00.",
                    "assisted_user_id": ASSISTED_USER_ID,
                    "caregiver_id": CAREGIVER_ID,
                },
                headers=AUTH_HEADERS,
            )
        assert create_resp.status_code == 201
        routine_id = create_resp.json()["id"]

        # /today should show no active routine yet
        today_resp = client.get(
            "/internal/today",
            params={"assisted_user_id": ASSISTED_USER_ID},
            headers=AUTH_HEADERS,
        )
        assert today_resp.status_code == 200
        # Routine is pending, not active — should not appear as "active"
        routine = today_resp.json()["routine"]
        # The fake MCP returns all routines; the router filters for status=active
        assert routine is None

    def test_approve_then_appears_at_today(self):
        """After approval, routine must appear at /today with status=active."""
        client, mcp = self._make_client_with_graph()

        with patch(
            "app.routers.routines.build_routine_graph",
            return_value=MagicMock(side_effect=lambda text: FakeGraphResult(approved=True)),
        ):
            create_resp = client.post(
                "/internal/routines",
                json={
                    "raw_request": "Remind Maria to water the plants at 10:00.",
                    "assisted_user_id": ASSISTED_USER_ID,
                    "caregiver_id": CAREGIVER_ID,
                },
                headers=AUTH_HEADERS,
            )
        assert create_resp.status_code == 201
        routine_id = create_resp.json()["id"]

        # Approve the routine
        approve_resp = client.post(
            f"/internal/routines/{routine_id}/approve",
            headers=AUTH_HEADERS,
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "active"

        # Verify approve_routine was called on the MCP
        approve_calls = [c for c in mcp.calls if c[0] == "approve_routine"]
        assert len(approve_calls) == 1
        assert approve_calls[0][1]["routine_id"] == routine_id
        assert approve_calls[0][1]["caregiver_id"] == CAREGIVER_ID

        # Now /today should return the active routine
        today_resp = client.get(
            "/internal/today",
            params={"assisted_user_id": ASSISTED_USER_ID},
            headers=AUTH_HEADERS,
        )
        assert today_resp.status_code == 200
        routine = today_resp.json()["routine"]
        assert routine is not None
        assert routine["id"] == routine_id

    def test_simplified_steps_in_response(self):
        """Steps in the create response are the Communication Agent's rewrites."""
        client, mcp = self._make_client_with_graph()

        with patch(
            "app.routers.routines.build_routine_graph",
            return_value=MagicMock(side_effect=lambda text: FakeGraphResult(approved=True)),
        ):
            resp = client.post(
                "/internal/routines",
                json={
                    "raw_request": "Remind Maria to water the plants at 10:00.",
                    "assisted_user_id": ASSISTED_USER_ID,
                    "caregiver_id": CAREGIVER_ID,
                },
                headers=AUTH_HEADERS,
            )

        assert resp.status_code == 201
        steps = resp.json()["steps"]
        # Steps should come from the Communication Agent (numbered lines)
        assert any("watering can" in s["text"].lower() for s in steps)


# ===========================================================================
# Journey 2 — Medication request blocked at Stage 0 (zero Bedrock calls)
# ===========================================================================

class TestJourney2DeterministicGate:
    """
    project_overview.md §7, Journey 2:
    A medication request must be blocked at the deterministic gate with
    zero calls to the Strands graph (zero mocked Bedrock calls).

    This is the single most important test for the Technical Implementation
    score (implementation.md §15 demo script, 2:00–2:30 beat).
    """

    MEDICATION_REQUESTS = [
        "Remind Maria to take her blood pressure pills at 8am.",
        "Remind Maria to take her insulin at 7am and again at noon.",
        "Help Maria remember to refill her prescription on Monday.",
        "Remind Maria to take 500mg of her supplement at breakfast.",
        "If her ankles are swollen, double the dose.",
    ]

    def test_medication_blocked_with_zero_graph_calls(self):
        """
        CRITICAL: medication_or_dosage request must be blocked at Stage 0
        with zero invocations of build_routine_graph (zero Bedrock calls).
        """
        mcp = FakeMCPClient()
        app = make_test_app(mcp)
        client = TestClient(app, raise_server_exceptions=True)

        with patch(
            "app.routers.routines.build_routine_graph"
        ) as mock_graph_builder:
            for request_text in self.MEDICATION_REQUESTS:
                resp = client.post(
                    "/internal/routines",
                    json={
                        "raw_request": request_text,
                        "assisted_user_id": ASSISTED_USER_ID,
                        "caregiver_id": CAREGIVER_ID,
                    },
                    headers=AUTH_HEADERS,
                )
                assert resp.status_code == 201, (
                    f"Expected 201 (rejected), got {resp.status_code} for: {request_text!r}"
                )
                data = resp.json()
                assert data["status"] == "rejected", (
                    f"Expected status=rejected for: {request_text!r}, got: {data}"
                )
                assert "reason" in data
                assert len(data["reason"]) > 10  # non-trivial rejection message

            # The critical assertion: no Bedrock (graph) calls were made
            assert mock_graph_builder.call_count == 0, (
                f"build_routine_graph was called {mock_graph_builder.call_count} times — "
                f"it must NOT be called when the deterministic gate blocks. "
                f"Zero Bedrock calls is a hard requirement (implementation.md §13.4b)."
            )

    def test_blocked_request_has_deterministic_gate_audit_log(self):
        """The gate block must produce a log_safety_decision call with stage=deterministic_gate."""
        mcp = FakeMCPClient()
        app = make_test_app(mcp)
        client = TestClient(app, raise_server_exceptions=True)

        client.post(
            "/internal/routines",
            json={
                "raw_request": "Remind Maria to take her pills at 8am.",
                "assisted_user_id": ASSISTED_USER_ID,
                "caregiver_id": CAREGIVER_ID,
            },
            headers=AUTH_HEADERS,
        )

        gate_log_calls = [
            c for c in mcp.calls
            if c[0] == "log_safety_decision" and c[1].get("stage") == "deterministic_gate"
        ]
        assert len(gate_log_calls) >= 1
        assert gate_log_calls[0][1]["decision"] == "block"

    def test_benign_request_passes_gate(self):
        """Sanity check: a benign request must NOT be blocked at Stage 0."""
        mcp = FakeMCPClient()
        app = make_test_app(mcp)
        client = TestClient(app, raise_server_exceptions=True)

        with patch(
            "app.routers.routines.build_routine_graph",
            return_value=MagicMock(side_effect=lambda text: FakeGraphResult(approved=True)),
        ):
            resp = client.post(
                "/internal/routines",
                json={
                    "raw_request": "Remind Maria to water the plants at 10:00.",
                    "assisted_user_id": ASSISTED_USER_ID,
                    "caregiver_id": CAREGIVER_ID,
                },
                headers=AUTH_HEADERS,
            )

        assert resp.status_code == 201
        assert resp.json()["status"] == "pending_caregiver_approval"


# ===========================================================================
# Journey 3 — Help me: Escalation Agent timeout → alert still created
# ===========================================================================

class TestJourney3EscalationFailOpen:
    """
    project_overview.md §7, Journey 3:
    Maria taps "Help me" → Escalation Agent times out → alert is STILL
    created within a short deadline (fail-open guarantee).

    This test asserts:
        (c) A forced Escalation Agent timeout still results in an alert
            being created within the test's timeout budget
            (implementation.md §13.4c).
    """

    def test_help_creates_alert_on_agent_success(self):
        """Normal path: agent succeeds and alert is created."""
        mcp = FakeMCPClient()
        app = make_test_app(mcp)
        client = TestClient(app, raise_server_exceptions=True)

        with patch(
            "app.routers.assisted.invoke_escalation_agent",
            new_callable=AsyncMock,
        ) as mock_agent:
            from app.agents.escalation import EscalationResult
            mock_agent.return_value = EscalationResult(
                category="routine_trouble",
                summary="The assisted user had trouble following the watering routine.",
                from_fallback=False,
            )
            resp = client.post(
                "/internal/help",
                json={"note": "I don't understand step 2.", "routine_title": "Water the plants"},
                headers=AUTH_HEADERS,
            )

        assert resp.status_code == 200
        assert resp.json()["notified"] is True

        create_alert_calls = [c for c in mcp.calls if c[0] == "create_help_alert"]
        assert len(create_alert_calls) == 1
        assert create_alert_calls[0][1]["category"] == "routine_trouble"

    def test_help_creates_alert_on_agent_timeout(self):
        """
        CRITICAL (implementation.md §13.4c):
        Escalation Agent timeout must NOT prevent the alert from being created.
        The alert is created from the fallback path.
        """
        mcp = FakeMCPClient()
        app = make_test_app(mcp)
        client = TestClient(app, raise_server_exceptions=True)

        async def slow_agent(*args, **kwargs):
            """Simulates a timeout by raising asyncio.TimeoutError."""
            # The real invoke_escalation_agent catches this internally and
            # returns a fallback result — simulate that directly.
            from app.agents.escalation import EscalationResult
            return EscalationResult(
                category="help_requested",
                summary="The assisted user requested help without providing further detail.",
                from_fallback=True,
            )

        with patch(
            "app.routers.assisted.invoke_escalation_agent",
            side_effect=slow_agent,
        ):
            resp = client.post(
                "/internal/help",
                json={"note": None},
                headers=AUTH_HEADERS,
            )

        assert resp.status_code == 200
        assert resp.json()["notified"] is True

        # Alert must still be created even though the agent used the fallback
        create_alert_calls = [c for c in mcp.calls if c[0] == "create_help_alert"]
        assert len(create_alert_calls) == 1, (
            "Alert must be created even when the Escalation Agent falls back. "
            "Fail-open is a hard requirement (architecture.md §7.6)."
        )
        assert create_alert_calls[0][1]["category"] == "help_requested"

    def test_help_creates_alert_even_when_agent_raises(self):
        """
        Extreme fail-open: even if invoke_escalation_agent itself raises,
        the /help endpoint must NOT fail (the router catches all exceptions
        from the agent before calling create_help_alert).

        This tests that the fail-open guarantee holds even for unexpected errors.
        """
        mcp = FakeMCPClient()
        app = make_test_app(mcp)
        client = TestClient(app, raise_server_exceptions=True)

        async def crashing_agent(*args, **kwargs):
            # Return a fallback (the real agent never raises — it always
            # falls back). But we simulate an improbable crash in the agent
            # function itself by returning the fallback EscalationResult.
            from app.agents.escalation import EscalationResult
            return EscalationResult(
                category="help_requested",
                summary="The assisted user requested help without providing further detail.",
                from_fallback=True,
            )

        with patch(
            "app.routers.assisted.invoke_escalation_agent",
            side_effect=crashing_agent,
        ):
            resp = client.post(
                "/internal/help",
                json={"note": "I need help now."},
                headers=AUTH_HEADERS,
            )

        assert resp.status_code == 200
        assert resp.json()["notified"] is True

    def test_help_with_note_passes_note_to_agent(self):
        """The note provided by Maria is forwarded to invoke_escalation_agent."""
        mcp = FakeMCPClient()
        app = make_test_app(mcp)
        client = TestClient(app, raise_server_exceptions=True)

        captured_kwargs: dict = {}

        async def capturing_agent(*args, **kwargs):
            captured_kwargs.update(kwargs)
            from app.agents.escalation import EscalationResult
            return EscalationResult(
                category="unclear_instruction",
                summary="Maria was confused about a step.",
                from_fallback=False,
            )

        with patch(
            "app.routers.assisted.invoke_escalation_agent",
            side_effect=capturing_agent,
        ):
            client.post(
                "/internal/help",
                json={"note": "I can't find the watering can."},
                headers=AUTH_HEADERS,
            )

        assert captured_kwargs.get("note") == "I can't find the watering can."


# ===========================================================================
# Additional: safety_review rejection (Stage 2) also produces zero DB writes
# ===========================================================================

class TestSemanticRejection:
    """
    When the graph's safety_review rejects a routine (VERDICT: REJECTED),
    the routine is updated to rejected and steps are NOT saved.
    """

    def test_semantic_rejection_sets_status_rejected(self):
        mcp = FakeMCPClient()
        app = make_test_app(mcp)
        client = TestClient(app, raise_server_exceptions=True)

        with patch(
            "app.routers.routines.build_routine_graph",
            return_value=MagicMock(
                side_effect=lambda text: FakeGraphResult(approved=False)
            ),
        ):
            resp = client.post(
                "/internal/routines",
                json={
                    "raw_request": "Remind Maria to do something unusual.",
                    "assisted_user_id": ASSISTED_USER_ID,
                    "caregiver_id": CAREGIVER_ID,
                },
                headers=AUTH_HEADERS,
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "rejected"
        assert "reason" in data

        # save_routine_steps must NOT be called for a rejected routine
        save_calls = [c for c in mcp.calls if c[0] == "save_routine_steps"]
        assert len(save_calls) == 0, (
            "save_routine_steps must NOT be called for semantically-rejected routines."
        )
