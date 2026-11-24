"""The Gradio callback: empty input must not reach the agent (no wasted LLM calls)."""

import app


class _GraphThatMustNotRun:
    def invoke(self, *args, **kwargs):
        raise AssertionError("the agent was called for an empty ticket")


def test_empty_ticket_does_not_call_the_agent(monkeypatch):
    monkeypatch.setattr(app, "_app", _GraphThatMustNotRun())

    for empty in ["", "   ", "\n"]:
        outputs = app.run_ticket(empty)
        assert outputs[-1] == "Enter a ticket above."
