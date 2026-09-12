"""
tests/test_graph_conditions.py
--------------------------------
Tests for the is_approved() condition function that gates the
safety_review → communicate edge in the Strands Graph.

All tests use mocked state objects — no Bedrock calls, no MCP subprocess.
The corpus covers well-formed responses, edge cases, and failure modes.

Reference: implementation.md §13.3
Fail-closed requirement: any response that does NOT contain
"VERDICT: APPROVED" must evaluate to False (architecture.md §15).
"""

from types import SimpleNamespace

import pytest

from app.agents.graph import is_approved


# ---------------------------------------------------------------------------
# Helper: build a mock graph state from a string result
# ---------------------------------------------------------------------------
def _make_state(safety_review_result: str | None) -> SimpleNamespace:
    """
    Build a minimal mock of the Strands Graph state object.

    The real state object has state.results["safety_review"].result (a string
    or object whose str() representation contains the verdict).
    """
    if safety_review_result is None:
        return SimpleNamespace(results={})

    return SimpleNamespace(
        results={
            "safety_review": SimpleNamespace(result=safety_review_result)
        }
    )


# ===========================================================================
# APPROVED cases — is_approved() must return True
# ===========================================================================

class TestApprovedCases:

    def test_clean_approved_response(self):
        state = _make_state(
            "VERDICT: APPROVED\n"
            "REASON: The routine involves only safe daily living activities.\n"
            "FLAGGED_CATEGORIES: NONE"
        )
        assert is_approved(state) is True

    def test_approved_with_surrounding_whitespace(self):
        state = _make_state(
            "\n\nVERDICT: APPROVED\nREASON: Routine is safe.\nFLAGGED_CATEGORIES: NONE\n\n"
        )
        assert is_approved(state) is True

    def test_approved_with_extra_preamble(self):
        """Model sometimes adds a preamble before the verdict — still approved."""
        state = _make_state(
            "I have reviewed the routine carefully.\n\n"
            "VERDICT: APPROVED\n"
            "REASON: No prohibited categories detected.\n"
            "FLAGGED_CATEGORIES: NONE"
        )
        assert is_approved(state) is True


# ===========================================================================
# REJECTED cases — is_approved() must return False (fail-closed)
# ===========================================================================

class TestRejectedCases:

    def test_clean_rejected_response(self):
        state = _make_state(
            "VERDICT: REJECTED\n"
            "REASON: The routine involves medication administration.\n"
            "FLAGGED_CATEGORIES: medication_or_dosage"
        )
        assert is_approved(state) is False

    def test_rejected_multiple_categories(self):
        state = _make_state(
            "VERDICT: REJECTED\n"
            "REASON: Multiple prohibited categories detected.\n"
            "FLAGGED_CATEGORIES: medication_or_dosage, emergency_service_actions"
        )
        assert is_approved(state) is False


# ===========================================================================
# Fail-closed edge cases — must all return False
# ===========================================================================

class TestFailClosedEdgeCases:
    """
    Any response that does NOT contain the exact 'VERDICT: APPROVED' marker
    must evaluate to False. This includes: missing marker, None result,
    empty string, garbled output, partial text.
    """

    def test_missing_safety_review_result(self):
        """No safety_review key in results — treat as rejected."""
        state = _make_state(None)
        assert is_approved(state) is False

    def test_empty_string_result(self):
        state = _make_state("")
        assert is_approved(state) is False

    def test_missing_verdict_marker(self):
        """Response contains REASON and FLAGGED_CATEGORIES but no VERDICT line."""
        state = _make_state(
            "REASON: The routine appears safe.\n"
            "FLAGGED_CATEGORIES: NONE"
        )
        assert is_approved(state) is False

    def test_partial_verdict_word(self):
        """'APPROVED' alone without the 'VERDICT: ' prefix must not trigger approval."""
        state = _make_state("The routine was APPROVED by the reviewer.")
        assert is_approved(state) is False

    def test_lowercase_verdict_not_approved(self):
        """Marker is case-sensitive — lowercase 'verdict: approved' must fail."""
        state = _make_state("verdict: approved\nreason: safe.")
        assert is_approved(state) is False

    def test_verdict_rejected_then_approved_in_reason(self):
        """
        'VERDICT: REJECTED' followed by 'APPROVED' in the reason text.
        Must return False — only the explicit 'VERDICT: APPROVED' marker counts.
        """
        state = _make_state(
            "VERDICT: REJECTED\n"
            "REASON: This would only be APPROVED if medication were removed.\n"
            "FLAGGED_CATEGORIES: medication_or_dosage"
        )
        assert is_approved(state) is False

    def test_garbled_output(self):
        """Model returns unexpected/garbled output — must be fail-closed."""
        state = _make_state("Error: context length exceeded. Please retry.")
        assert is_approved(state) is False

    def test_none_result_attribute(self):
        """result attribute exists but is None."""
        state = SimpleNamespace(
            results={"safety_review": SimpleNamespace(result=None)}
        )
        assert is_approved(state) is False

    def test_missing_results_attribute(self):
        """State object has no results attribute at all — must not raise."""
        state = SimpleNamespace()  # no results attribute
        assert is_approved(state) is False

    def test_non_string_result(self):
        """result is a non-string type — str() conversion must still work."""
        state = SimpleNamespace(
            results={"safety_review": SimpleNamespace(result=42)}
        )
        assert is_approved(state) is False
