"""
agent-backend.app.gate.categories
-----------------------------------
Prohibited-category rule table for the MemoryBridge deterministic gate.

This module is the implementation of Stage 0 (architecture.md §11,
implementation.md §8). It runs BEFORE any model call — a match here results
in zero Bedrock invocations.

Design decisions:
  - Patterns are intentionally broad (word-boundary, case-insensitive).
    False positives are cheaper than false negatives for this gate, because
    the caregiver can always rephrase and resubmit, and the Semantic Safety
    Reviewer (architecture.md §7.3) is the independent second layer this gate
    is explicitly not relied on alone.
  - Each category has exactly one compiled Pattern list. A single match on
    any pattern in a category is enough to block the entire request.
  - ADR-004: The medication_or_dosage category blocks the entire category,
    including plain reminders, because distinguishing a reminder from a dosage
    change is itself a clinical judgment this prototype does not have.
  - Patterns use raw strings (r"...") throughout to avoid accidental
    escape-sequence interpretation.
"""

import re

# Type alias for clarity
_PatternList = list[re.Pattern[str]]

PROHIBITED_CATEGORIES: dict[str, _PatternList] = {
    # -----------------------------------------------------------------------
    # 1. Medication or dosage (ADR-004: entire category blocked, not just dosage)
    # -----------------------------------------------------------------------
    "medication_or_dosage": [
        re.compile(
            r"\b(medicat\w*|medicine|pill|pills|tablet|tablets|capsule|capsules"
            r"|dosage|dose|doses|insulin|prescription|prescribe|refill"
            r"|medication reminder)\b",
            re.IGNORECASE,
        ),
        # Catches "500mg", "10 mg", etc. — separate pattern for the unit alone
        re.compile(r"\d+\s*mg\b", re.IGNORECASE),
    ],

    # -----------------------------------------------------------------------
    # 2. Medical diagnosis or advice
    # -----------------------------------------------------------------------
    "medical_diagnosis_or_advice": [
        re.compile(
            r"\b(diagnos\w*|symptom\w*|medical advice|is she sick|is he sick"
            r"|what does .{0,20} mean medically|doctor|physician|nurse)\b",
            re.IGNORECASE,
        ),
        # Phrase patterns — too long for a single \b word match
        re.compile(
            r"(is (this|it) normal|does this mean|should (i|we) be worried"
            r"|figure out if .{0,30} means|means something (serious|wrong|bad))",
            re.IGNORECASE,
        ),
    ],

    # -----------------------------------------------------------------------
    # 3. Financial transactions
    # -----------------------------------------------------------------------
    "financial_transactions": [
        re.compile(
            r"\b(pay\b|payment|transfer|wire\b|bank account|donate\b"
            r"|donation|subscri\w*|purchase|buy .{0,20} online|invest\w*"
            r"|credit card|debit card|send money|withdraw)\b",
            re.IGNORECASE,
        ),
    ],

    # -----------------------------------------------------------------------
    # 4. Emergency-service actions
    # -----------------------------------------------------------------------
    "emergency_service_actions": [
        re.compile(
            r"\b(call 911|call 999|call 112|ambulance|fire department"
            r"|emergency services|paramedic|call the police|dial emergency)\b",
            re.IGNORECASE,
        ),
    ],

    # -----------------------------------------------------------------------
    # 5. Unlocking doors / granting physical access
    # -----------------------------------------------------------------------
    "unlocking_doors": [
        re.compile(
            r"\b(unlock\w*|disarm|let .{0,15} in|open the (front |back |side )?"
            r"door|garage door|grant access|buzz .{0,10} in)\b",
            re.IGNORECASE,
        ),
    ],

    # -----------------------------------------------------------------------
    # 6. Controlling appliances / smart-home devices
    # -----------------------------------------------------------------------
    "controlling_appliances": [
        re.compile(
            r"\b(turn (on|off) the (stove|oven|thermostat|heater|microwave"
            r"|dishwasher|washing machine|dryer)|smart lock|smart plug"
            r"|smart home|home automation|alexa|google home)\b",
            re.IGNORECASE,
        ),
        # Thermostat / temperature phrasing — not always preceded by 'turn'
        re.compile(
            r"(adjust the thermostat|set the thermostat|set the temperature"
            r"|thermostat to \d+)",
            re.IGNORECASE,
        ),
    ],

    # -----------------------------------------------------------------------
    # 7. Other high-risk actions (bounded catch-all — project_overview.md §9.1.7)
    # Covers violence/self-harm and contacting unknown third parties.
    # Does NOT block known-family contact (see test_gate.py benign case:
    # "Remind Maria to call her daughter at 6pm" must pass).
    # -----------------------------------------------------------------------
    "other_high_risk_actions": [
        re.compile(
            r"\b(contact (a stranger|someone new|an unknown|unknown person)"
            r"|self[- ]?harm|hurt (myself|herself|himself|yourself)"
            r"|suicide|kill (myself|herself|himself))\b",
            re.IGNORECASE,
        ),
    ],
}

# ---------------------------------------------------------------------------
# Caregiver-facing rejection messages (implementation.md §8.1)
# Keyed by category name. Used by the FastAPI router to generate the
# plain-language response shown to the caregiver after a block.
# ---------------------------------------------------------------------------
REJECTION_MESSAGES: dict[str, str] = {
    "medication_or_dosage": (
        "MemoryBridge doesn't handle medication reminders or dosage — "
        "even simple ones — because that needs clinical judgment we're not "
        "able to provide safely. Please use a dedicated medication app or "
        "talk to a pharmacist."
    ),
    "medical_diagnosis_or_advice": (
        "MemoryBridge can't offer medical advice or interpret symptoms. "
        "Please contact a healthcare provider."
    ),
    "financial_transactions": (
        "MemoryBridge doesn't handle payments, transfers, or purchases "
        "of any kind."
    ),
    "emergency_service_actions": (
        "MemoryBridge never contacts emergency services. "
        "If this is urgent, please contact them directly."
    ),
    "unlocking_doors": (
        "MemoryBridge doesn't control locks or door access."
    ),
    "controlling_appliances": (
        "MemoryBridge doesn't control appliances or smart-home devices."
    ),
    "other_high_risk_actions": (
        "This request falls outside what MemoryBridge is able to safely "
        "automate. Please handle it directly."
    ),
}
