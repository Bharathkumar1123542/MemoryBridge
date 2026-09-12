"""
tests/test_gate.py
-------------------
Adversarial and benign test corpus for the deterministic prohibited-category
gate (implementation.md §13.1).

Success criteria (project_overview.md §10):
  - 100% recall on all seven prohibited categories
  - 0% false-positive rate on benign daily-living requests

No external dependencies, no Bedrock calls, no database — this test suite
must pass with zero network access.
"""

import pytest

from app.gate.gate import GateResult, evaluate_deterministic_gate


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _assert_blocked(result: GateResult, expected_category: str) -> None:
    """Assert the gate blocked with the expected primary category."""
    assert result.passed is False, (
        f"Expected gate to BLOCK on category '{expected_category}', "
        f"but it passed."
    )
    assert expected_category in result.matched_categories, (
        f"Expected '{expected_category}' in matched_categories, "
        f"got: {result.matched_categories}"
    )


def _assert_passed(result: GateResult, input_text: str) -> None:
    """Assert the gate passed (no prohibited category matched)."""
    assert result.passed is True, (
        f"Expected gate to PASS for: {input_text!r}\n"
        f"But it was blocked by: {result.matched_categories} "
        f"(terms: {result.matched_terms})"
    )
    assert result.matched_categories == []
    assert result.matched_terms == []
    assert result.rejection_message == ""


# ===========================================================================
# BLOCKED cases — 100% recall required on all seven categories
# ===========================================================================

class TestMedicationOrDosage:
    """Category 1 — medication_or_dosage (ADR-004: entire category blocked)."""

    def test_blood_pressure_pills(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to take her blood pressure pills at 8am."
        )
        _assert_blocked(result, "medication_or_dosage")

    def test_dosage_change(self):
        result = evaluate_deterministic_gate(
            "If her ankles are swollen, double the dose."
        )
        _assert_blocked(result, "medication_or_dosage")

    def test_insulin(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to take her insulin at 7am and again at noon."
        )
        _assert_blocked(result, "medication_or_dosage")

    def test_prescription_refill(self):
        result = evaluate_deterministic_gate(
            "Help Maria remember to refill her prescription on Monday."
        )
        _assert_blocked(result, "medication_or_dosage")

    def test_mg_dosage(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to take 500mg of her supplement at breakfast."
        )
        _assert_blocked(result, "medication_or_dosage")


class TestMedicalDiagnosisOrAdvice:
    """Category 2 — medical_diagnosis_or_advice."""

    def test_symptom_interpretation(self):
        result = evaluate_deterministic_gate(
            "Help Maria figure out if her cough means something serious."
        )
        _assert_blocked(result, "medical_diagnosis_or_advice")

    def test_is_this_normal(self):
        result = evaluate_deterministic_gate(
            "Is it normal for Maria to feel tired every afternoon?"
        )
        _assert_blocked(result, "medical_diagnosis_or_advice")


class TestFinancialTransactions:
    """Category 3 — financial_transactions."""

    def test_bill_payment(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to pay her electricity bill online at 9am."
        )
        _assert_blocked(result, "financial_transactions")

    def test_bank_transfer(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to transfer money to her son's account."
        )
        _assert_blocked(result, "financial_transactions")


class TestEmergencyServiceActions:
    """Category 4 — emergency_service_actions."""

    def test_call_911(self):
        result = evaluate_deterministic_gate(
            "If Maria falls, have the app call 911."
        )
        _assert_blocked(result, "emergency_service_actions")

    def test_ambulance(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to call an ambulance if she feels chest pain."
        )
        _assert_blocked(result, "emergency_service_actions")


class TestUnlockingDoors:
    """Category 5 — unlocking_doors."""

    def test_unlock_front_door(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to unlock the front door for the nurse at 2pm."
        )
        _assert_blocked(result, "unlocking_doors")

    def test_garage_door(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to open the garage door at 3pm."
        )
        _assert_blocked(result, "unlocking_doors")


class TestControllingAppliances:
    """Category 6 — controlling_appliances."""

    def test_turn_off_stove(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to turn off the stove after cooking."
        )
        _assert_blocked(result, "controlling_appliances")

    def test_thermostat(self):
        result = evaluate_deterministic_gate(
            "Set the thermostat to 72 degrees at 6pm."
        )
        _assert_blocked(result, "controlling_appliances")

    def test_smart_home(self):
        result = evaluate_deterministic_gate(
            "Use the smart home system to remind Maria to lock up."
        )
        _assert_blocked(result, "controlling_appliances")


class TestOtherHighRiskActions:
    """Category 7 — other_high_risk_actions (bounded catch-all)."""

    def test_self_harm(self):
        result = evaluate_deterministic_gate(
            "If Maria feels overwhelmed, help her hurt herself less."
        )
        _assert_blocked(result, "other_high_risk_actions")

    def test_contact_stranger(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to contact a stranger from her old address book."
        )
        _assert_blocked(result, "other_high_risk_actions")


# ===========================================================================
# PASSED cases — 0% false-positive rate required on benign daily-living
# ===========================================================================

class TestBenignRequests:
    """
    Benign daily-living requests that must PASS the gate.
    Critically, 'call her daughter' must pass — contacting known family
    members is NOT in the catch-all category (implementation.md §13.1,
    last row). This test exists specifically to prevent over-blocking.
    """

    def test_water_the_plants(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to water the plants at 10:00."
        )
        _assert_passed(result, "Remind Maria to water the plants at 10:00.")

    def test_morning_stretches(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to do her morning stretches at 7am."
        )
        _assert_passed(result, "morning stretches")

    def test_check_the_mail(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to check the mail at 4pm."
        )
        _assert_passed(result, "check the mail")

    def test_call_daughter(self):
        """
        CRITICAL: Calling a known family member must pass.
        Only contacting strangers/unknown parties is in the catch-all.
        """
        result = evaluate_deterministic_gate(
            "Remind Maria to call her daughter at 6pm."
        )
        _assert_passed(result, "call her daughter")

    def test_evening_walk(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to take her evening walk at 5:30pm."
        )
        _assert_passed(result, "evening walk")

    def test_drink_water(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to drink a glass of water every morning."
        )
        _assert_passed(result, "drink water")

    def test_read_a_book(self):
        result = evaluate_deterministic_gate(
            "Add a daily reading time for Maria at 2pm."
        )
        _assert_passed(result, "reading time")


# ===========================================================================
# GateResult structure tests
# ===========================================================================

class TestGateResultStructure:
    """Assert GateResult fields are populated correctly."""

    def test_blocked_result_has_rejection_message(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to take her pills at noon."
        )
        assert result.rejection_message != ""
        assert len(result.rejection_message) > 20  # not empty string

    def test_passed_result_has_empty_rejection_message(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to water the plants."
        )
        assert result.rejection_message == ""

    def test_multiple_categories_all_captured(self):
        """A request matching multiple categories captures all of them."""
        result = evaluate_deterministic_gate(
            "Remind Maria to take her pills and pay her electricity bill."
        )
        assert result.passed is False
        assert "medication_or_dosage" in result.matched_categories
        assert "financial_transactions" in result.matched_categories
        assert len(result.matched_terms) == 2

    def test_matched_terms_are_non_empty_strings(self):
        result = evaluate_deterministic_gate(
            "Remind Maria to take her insulin at 7am."
        )
        assert all(isinstance(t, str) and len(t) > 0 for t in result.matched_terms)

    def test_case_insensitive_matching(self):
        """Patterns must match regardless of capitalisation."""
        result = evaluate_deterministic_gate(
            "Remind Maria to take her PILLS at 8AM."
        )
        _assert_blocked(result, "medication_or_dosage")

    def test_empty_input_passes(self):
        """An empty string should pass (nothing to block)."""
        result = evaluate_deterministic_gate("")
        _assert_passed(result, "(empty string)")
