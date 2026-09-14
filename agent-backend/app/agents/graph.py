"""
agent-backend.app.agents.graph
--------------------------------
Strands Agents Graph for the MemoryBridge routine-creation pipeline
(Stages 1–3: plan → safety_review → [communicate]).

Reference implementations:
  - architecture.md §7.5 (annotated wiring)
  - implementation.md §9 (production entry point)

Design:
  - The graph is acyclic. set_max_node_executions(3) caps worst-case
    execution even though no loops exist (defense-in-depth per SDK guidance).
  - is_approved() is a plain Python function — unit-testable with no
    Bedrock calls. test_graph_conditions.py exercises this in isolation.
  - Temperature is fixed per architecture.md §12:
      Reasoning/Safety agents: 0.2 (consistency > variety)
      Communication agent:     0.4 (avoid mechanically repetitive phrasing)
"""

import logging
from typing import Any

from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.multiagent import GraphBuilder

from ..config import AWS_REGION, BEDROCK_MODEL_ID_FAST, BEDROCK_MODEL_ID_REASONING
from .prompts import (
    COMMUNICATION_SYSTEM_PROMPT,
    ROUTINE_PLANNING_SYSTEM_PROMPT,
    SAFETY_REVIEWER_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Condition function — the conditional edge between safety_review and communicate.
# This is plain Python: no model call, no I/O, no side effects.
# Fail-closed: any response that does NOT contain "VERDICT: APPROVED" is
# treated as rejected (architecture.md §15, failure mode 2).
# ---------------------------------------------------------------------------
def is_approved(state: Any) -> bool:
    """
    Return True only if the safety_review node produced an explicit
    'VERDICT: APPROVED' marker.

    Fail-closed: missing marker, None result, or any exception → False.
    This means a garbled or truncated model response is treated as a
    rejection, not an approval — the conservative outcome.

    Args:
        state: The Strands Graph execution state object.

    Returns:
        bool — True if the routine was explicitly approved.
    """
    try:
        review = state.results.get("safety_review")
        if review is None:
            logger.warning("is_approved: safety_review result is None — treating as rejected.")
            return False
        result_text = str(review.result)
        approved = "VERDICT: APPROVED" in result_text
        if not approved:
            logger.info(
                "is_approved: safety_review did not return VERDICT: APPROVED. "
                "Result snippet: %.200s",
                result_text,
            )
        return approved
    except Exception as exc:  # noqa: BLE001
        logger.error("is_approved: unexpected error — treating as rejected. %s", exc)
        return False


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------
def build_routine_graph(planning_tools: list) -> Any:
    """
    Construct and return the Strands Graph for routine creation.

    Args:
        planning_tools: The list of read-only MCP tool objects returned by
            MemoryBridgeMCPClient.get_planning_tools(). This list is passed
            ONLY to the Routine Planning Agent. All other agents receive
            tools=[] (ADR-002).

    Returns:
        A compiled Strands Graph object ready to invoke.

    Node timeouts and graph limits (architecture.md §7.2):
        set_execution_timeout(45)  — total wall-clock budget for the graph
        set_node_timeout(20)       — per-node wall-clock budget
        set_max_node_executions(3) — defense-in-depth cap (no loops exist)
    """
    # Node: plan — Routine Planning Agent
    plan_agent = Agent(
        name="plan",
        system_prompt=ROUTINE_PLANNING_SYSTEM_PROMPT,
        tools=planning_tools,
        # Temperature passed via BedrockModel; Agent accepts a Model object
        model=BedrockModel(
            model_id=BEDROCK_MODEL_ID_FAST,
            region_name=AWS_REGION,
            temperature=0.2,  # structured extraction — consistency over variety
        ),
    )

    # Node: safety_review — Semantic Safety Reviewer
    # tools=[] — this agent has NO mechanism to call any tool (ADR-002)
    reviewer_agent = Agent(
        name="safety_review",
        system_prompt=SAFETY_REVIEWER_SYSTEM_PROMPT,
        tools=[],
        model=BedrockModel(
            model_id=BEDROCK_MODEL_ID_REASONING,
            region_name=AWS_REGION,
            temperature=0.2,  # safety judgment — consistency is critical
        ),
    )

    # Node: communicate — Dementia-Friendly Communication Agent
    # tools=[] — this agent has NO mechanism to call any tool (ADR-002)
    comms_agent = Agent(
        name="communicate",
        system_prompt=COMMUNICATION_SYSTEM_PROMPT,
        tools=[],
        # Slightly higher temperature: avoid mechanically repetitive phrasing
        # while staying well short of creative-writing settings (architecture.md §12)
        model=BedrockModel(
            model_id=BEDROCK_MODEL_ID_REASONING,
            region_name=AWS_REGION,
            temperature=0.4,
        ),
    )

    builder = GraphBuilder()
    builder.add_node(plan_agent, "plan")
    builder.add_node(reviewer_agent, "safety_review")
    builder.add_node(comms_agent, "communicate")

    # Fixed edges
    builder.add_edge("plan", "safety_review")
    # Conditional edge: communicate only runs if is_approved() → True
    builder.add_edge("safety_review", "communicate", condition=is_approved)

    builder.set_entry_point("plan")
    builder.set_execution_timeout(45)   # seconds — total graph budget
    builder.set_node_timeout(20)        # seconds — per-node budget
    builder.set_max_node_executions(3)  # defense-in-depth; no loops exist

    graph = builder.build()
    logger.info("Routine graph built: plan → safety_review →[cond]→ communicate")
    return graph
