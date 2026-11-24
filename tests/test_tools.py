"""The mocked account-status tool and the node that decides whether to call it."""

import pytest

from agent import tool_call_node
from tools import check_account_status


@pytest.mark.parametrize(
    "ticket",
    [
        "My account is locked",
        "I can't log in since yesterday",
        "I cannot log in anymore",
    ],
)
def test_login_problems_return_a_locked_account(ticket):
    assert check_account_status(ticket)["account_status"] == "locked"


@pytest.mark.parametrize(
    "ticket",
    [
        "I was charged twice this month",
        "Can I get a refund?",
        "My card was declined",
        "There was a double charge",
    ],
)
def test_payment_problems_return_past_due(ticket):
    result = check_account_status(ticket)
    assert result["account_status"] == "active"
    assert result["payment_status"] == "past_due"


def test_anything_else_returns_no_issues():
    result = check_account_status("How do I change my email address?")
    assert result["account_status"] == "active"
    assert result["payment_status"] == "current"


def test_keyword_matching_ignores_case():
    assert check_account_status("ACCOUNT LOCKED")["account_status"] == "locked"


def test_tool_is_deterministic():
    ticket = "I was charged twice"
    assert check_account_status(ticket) == check_account_status(ticket)


def test_tool_is_not_called_for_technical_tickets():
    state = {"ticket": "My account is locked", "category": "technical"}
    assert tool_call_node(state) == {"tool_result": None}


@pytest.mark.parametrize("category", ["billing", "account_access"])
def test_tool_is_called_for_billing_and_account_tickets(category):
    state = {"ticket": "My account is locked", "category": category}
    assert tool_call_node(state)["tool_result"]["account_status"] == "locked"
