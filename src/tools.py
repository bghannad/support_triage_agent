"""Mocked tool functions the agent can call.

In a real system, this would call an internal billing/account API using an
authenticated account ID.
Here we fake it by scanning the ticket text for a few trigger phrases, so
the SAME ticket always produces the SAME mocked result (deterministic:
important for reproducible testing and, later, the evaluation harness).
"""

from typing import TypedDict


class AccountStatus(TypedDict):
    account_status: str
    payment_status: str
    last_login_days_ago: int
    note: str


def check_account_status(ticket_text: str) -> AccountStatus:
    """Mocked 'look up account status' tool.

    Real version: would take an account ID (looked up separately from the
    logged-in session), not raw ticket text, and call a real internal
    service. This mock exists purely to demonstrate the agent calling a
    tool mid-pipeline and using its result to inform the escalation
    decision downstream.
    """
    text = ticket_text.lower()

    if "locked" in text or "can't log in" in text or "cannot log in" in text:
        return {
            "account_status": "locked",
            "payment_status": "current",
            "last_login_days_ago": 12,
            "note": "Account locked after failed login attempts.",
        }

    if any(
        kw in text
        for kw in ["charged twice", "refund", "failed payment", "declined", "double charge"]
    ):
        return {
            "account_status": "active",
            "payment_status": "past_due",
            "last_login_days_ago": 1,
            "note": "Recent payment issue on file.",
        }

    return {
        "account_status": "active",
        "payment_status": "current",
        "last_login_days_ago": 2,
        "note": "No issues found on account.",
    }
