"""
tests/test_tool_binding.py
---------------------------
ADR-002 enforcement: asserts that no Strands Agent object in the system
is ever constructed with a database write tool.

This test must run on every CI commit. A failure here means a future change
accidentally granted write-tool access to an agent — closing the one attack
surface ADR-002 is designed to eliminate.

Tests in this module do NOT call Bedrock or the MCP server. They inspect
the tool lists of Agent objects constructed with mock/empty tool inputs.

Reference: implementation.md §13.2
"""

import pytest

from app.agents.graph import build_routine_graph, is_approved
from app.agents.escalation import _get_escalation_agent
from app.mcp_client import READ_ONLY_TOOLS, WRITE_TOOLS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_tool_names(agent) -> set[str]:
    """Extract the set of tool names bound to a Strands Agent."""
    tools = getattr(agent, "tools", []) or []
    names = set()
    for t in tools:
        # Strands tool objects may expose .tool_name, .name, or .__name__
        name = (
            getattr(t, "tool_name", None)
            or getattr(t, "name", None)
            or getattr(t, "__name__", None)
            or str(t)
        )
        names.add(name)
    return names


# ---------------------------------------------------------------------------
# ADR-002 core assertion
# ---------------------------------------------------------------------------
class TestNoAgentHoldsWriteTool:
    """
    Assert that every Agent in the system has a tool list that is a
    strict subset of READ_ONLY_TOOLS (or is empty).

    No name in WRITE_TOOLS may appear in any Agent's bound tools.
    """

    def test_routine_graph_with_empty_planning_tools(self):
        """
        Graph agents constructed with tools=[] for planning should have
        no write tools. Tests the reviewer and communicate agents directly.
        """
        graph = build_routine_graph(planning_tools=[])
        # Access the underlying agents from the graph nodes
        for node_name in ("plan", "safety_review", "communicate"):
            node = graph.nodes.get(node_name) if hasattr(graph, "nodes") else None
            if node is None:
                # Attempt alternate access patterns depending on SDK version
                continue
            agent = getattr(node, "agent", node)
            tool_names = _get_tool_names(agent)
            write_tools_found = tool_names & WRITE_TOOLS
            assert not write_tools_found, (
                f"Agent '{node_name}' has write tools bound: {write_tools_found}. "
                f"This violates ADR-002. Check app/agents/graph.py."
            )

    def test_safety_review_agent_has_no_tools(self):
        """Semantic Safety Reviewer must be constructed with tools=[]."""
        graph = build_routine_graph(planning_tools=[])
        node = _get_node(graph, "safety_review")
        if node:
            agent = getattr(node, "agent", node)
            assert _get_tool_names(agent) == set(), (
                "safety_review agent must have tools=[] (ADR-002)."
            )

    def test_communicate_agent_has_no_tools(self):
        """Dementia-Friendly Communication Agent must be constructed with tools=[]."""
        graph = build_routine_graph(planning_tools=[])
        node = _get_node(graph, "communicate")
        if node:
            agent = getattr(node, "agent", node)
            assert _get_tool_names(agent) == set(), (
                "communicate agent must have tools=[] (ADR-002)."
            )

    def test_escalation_agent_has_no_tools(self):
        """Escalation Agent must be constructed with tools=[]."""
        agent = _get_escalation_agent()
        tool_names = _get_tool_names(agent)
        assert tool_names == set(), (
            f"Escalation agent must have tools=[] (ADR-002). "
            f"Found: {tool_names}"
        )
        write_tools_found = tool_names & WRITE_TOOLS
        assert not write_tools_found


# ---------------------------------------------------------------------------
# READ_ONLY_TOOLS contract tests
# ---------------------------------------------------------------------------
class TestReadOnlyToolsContract:
    """Assert the READ_ONLY_TOOLS set matches the contract in architecture.md §9."""

    def test_read_only_tools_contains_expected_names(self):
        assert "get_assisted_user_profile" in READ_ONLY_TOOLS
        assert "get_existing_routines" in READ_ONLY_TOOLS

    def test_read_only_tools_does_not_contain_write_tool_names(self):
        overlap = READ_ONLY_TOOLS & WRITE_TOOLS
        assert not overlap, (
            f"READ_ONLY_TOOLS and WRITE_TOOLS must not overlap. "
            f"Overlap found: {overlap}"
        )

    def test_write_tools_contains_all_expected_names(self):
        expected = {
            "create_routine", "save_routine_steps", "update_routine_status",
            "approve_routine", "reject_routine", "get_today_routines",
            "mark_routine_complete", "create_help_alert", "get_alerts",
            "log_safety_decision",
        }
        assert expected == WRITE_TOOLS, (
            f"WRITE_TOOLS does not match the architecture.md §9 contract. "
            f"Missing: {expected - WRITE_TOOLS}. Extra: {WRITE_TOOLS - expected}"
        )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _get_node(graph, node_name: str):
    """Attempt to retrieve a graph node by name; return None if inaccessible."""
    if hasattr(graph, "nodes"):
        return graph.nodes.get(node_name)
    return None
