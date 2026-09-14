"""
agent-backend.app.gate.gate
-----------------------------
Deterministic prohibited-category gate — Stage 0 of the MemoryBridge pipeline.

evaluate_deterministic_gate() runs as plain Python inside the FastAPI request
handler, BEFORE the Strands Graph is invoked at all. A blocked request results
in zero calls to Amazon Bedrock (architecture.md §11).

This is the implementation of "Safety First, AI Second" as a control-flow
property, not a prompt constraint.
"""

from dataclasses import dataclass, field

from .categories import PROHIBITED_CATEGORIES, REJECTION_MESSAGES


@dataclass
class GateResult:
    """
    Result returned by evaluate_deterministic_gate().

    Attributes:
        passed:              True if no prohibited categories matched.
        matched_categories:  List of category names that triggered a block.
        matched_terms:       The specific terms that matched (one per category,
                             for the audit log and caregiver-facing message).
        rejection_message:   Human-readable rejection copy for the first
                             matched category; empty string if passed=True.
    """
    passed: bool
    matched_categories: list[str] = field(default_factory=list)
    matched_terms: list[str] = field(default_factory=list)
    rejection_message: str = ""


def evaluate_deterministic_gate(raw_text: str) -> GateResult:
    """
    Evaluate a caregiver's raw request against all seven prohibited categories.

    Checks every category sequentially. A single pattern match per category
    is sufficient to block — the loop breaks at the first match within a
    category but continues to the next category to capture all violations.
    This gives the caregiver a complete list of why the request was blocked,
    rather than stopping at the first issue.

    Args:
        raw_text: The caregiver's raw natural-language request.

    Returns:
        GateResult with passed=True if no categories matched, or
        passed=False with the list of matched categories, terms, and the
        rejection message for the first (most specific) category matched.

    Note:
        This function is pure and has no side effects. The caller (FastAPI
        router) is responsible for writing the audit log entry via the MCP
        client's log_safety_decision tool.
    """
    matched_categories: list[str] = []
    matched_terms: list[str] = []

    for category, patterns in PROHIBITED_CATEGORIES.items():
        for pattern in patterns:
            match = pattern.search(raw_text)
            if match:
                matched_categories.append(category)
                matched_terms.append(match.group(0).strip())
                break  # one match per category is enough to block

    passed = len(matched_categories) == 0

    # Use the rejection message for the first matched category.
    # If multiple categories match, the caregiver sees the most specific
    # message; all categories are logged in the audit trail.
    rejection_message = (
        ""
        if passed
        else REJECTION_MESSAGES.get(
            matched_categories[0],
            "This request falls outside what MemoryBridge is able to safely automate.",
        )
    )

    return GateResult(
        passed=passed,
        matched_categories=matched_categories,
        matched_terms=matched_terms,
        rejection_message=rejection_message,
    )
