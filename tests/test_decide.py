"""The escalation policy: decide_node is plain if/else rules, so it is fully testable.

These tests protect the business rules: security always escalates, low confidence
escalates, a locked account escalates, everything else is answered automatically.
"""

from agent import CONFIDENCE_THRESHOLD, decide_node, escalate_node, route_after_decision


def test_security_always_escalates_even_with_high_confidence():
    state = {"category": "security", "confidence": 0.99, "tool_result": None}
    result = decide_node(state)
    assert result["decision"] == "escalate"
    assert "Security" in result["escalation_reason"]


def test_low_confidence_escalates():
    state = {"category": "billing", "confidence": CONFIDENCE_THRESHOLD - 0.01, "tool_result": None}
    result = decide_node(state)
    assert result["decision"] == "escalate"
    assert "confidence" in result["escalation_reason"].lower()


def test_confidence_exactly_at_threshold_is_not_escalated():
    # The rule is "confidence < threshold", so the threshold itself passes.
    state = {"category": "technical", "confidence": CONFIDENCE_THRESHOLD, "tool_result": None}
    assert decide_node(state)["decision"] == "auto_answer"


def test_locked_account_escalates():
    state = {
        "category": "account_access",
        "confidence": 0.9,
        "tool_result": {"account_status": "locked"},
    }
    result = decide_node(state)
    assert result["decision"] == "escalate"
    assert "locked" in result["escalation_reason"].lower()


def test_normal_ticket_is_auto_answered():
    state = {"category": "technical", "confidence": 0.9, "tool_result": None}
    result = decide_node(state)
    assert result == {"decision": "auto_answer", "escalation_reason": ""}


def test_missing_confidence_counts_as_zero_and_escalates():
    # decide_node defaults a missing confidence to 0.0 -> safest outcome.
    assert decide_node({"category": "billing"})["decision"] == "escalate"


def test_route_after_decision_returns_the_stored_decision():
    assert route_after_decision({"decision": "escalate"}) == "escalate"
    assert route_after_decision({"decision": "auto_answer"}) == "auto_answer"


def test_escalate_node_message_contains_the_reason():
    result = escalate_node({"escalation_reason": "Account is locked"})
    assert "escalated to a human" in result["response"]
    assert "Account is locked" in result["response"]
