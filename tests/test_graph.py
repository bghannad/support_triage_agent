"""The whole LangGraph flow, end to end, with the LLM and retrieval replaced by fakes.

This tests the wiring (which nodes run, in which order, which branch is taken),
not the model's quality. No OpenAI key and no Chroma are needed.
"""

import pytest

import agent


@pytest.fixture
def fake_graph(monkeypatch):
    """Build the real graph, but with fake classify / retrieve / answer steps."""
    calls = {"retrieve": 0, "answer": 0}

    def make(category, confidence=0.9):
        def fake_classify(state):
            return {
                "category": category,
                "confidence": confidence,
                "classification_reasoning": "fake",
            }

        def fake_retrieve(query, k=3):
            calls["retrieve"] += 1
            return [{"document": "fake article", "metadata": {"title": "Fake"}, "distance": 0.1}]

        def fake_answer(state):
            calls["answer"] += 1
            return {"response": "fake answer"}

        monkeypatch.setattr(agent, "classify_node", fake_classify)
        monkeypatch.setattr(agent, "retrieve_kb", fake_retrieve)
        monkeypatch.setattr(agent, "answer_node", fake_answer)
        return agent.build_graph(), calls

    return make


def test_security_ticket_is_escalated_and_never_answered(fake_graph):
    graph, calls = fake_graph("security")
    final = graph.invoke({"ticket": "Someone logged into my account"})

    assert final["decision"] == "escalate"
    assert "escalated to a human" in final["response"]
    assert calls["answer"] == 0


def test_technical_ticket_is_answered_without_the_tool(fake_graph):
    graph, calls = fake_graph("technical")
    final = graph.invoke({"ticket": "My files are not syncing"})

    assert final["decision"] == "auto_answer"
    assert final["tool_result"] is None
    assert final["response"] == "fake answer"
    assert calls["answer"] == 1


def test_locked_account_is_escalated_via_the_tool(fake_graph):
    graph, calls = fake_graph("account_access")
    final = graph.invoke({"ticket": "My account is locked"})

    assert final["tool_result"]["account_status"] == "locked"
    assert final["decision"] == "escalate"
    assert calls["answer"] == 0


def test_low_confidence_is_escalated(fake_graph):
    graph, _ = fake_graph("billing", confidence=0.3)
    final = graph.invoke({"ticket": "something about money?"})

    assert final["decision"] == "escalate"


def test_retrieval_runs_for_every_ticket_even_when_escalated(fake_graph):
    # Documents current behaviour (a known inefficiency): retrieval runs before
    # the decision, so escalated tickets are retrieved for nothing.
    graph, calls = fake_graph("security")
    graph.invoke({"ticket": "Someone logged into my account"})

    assert calls["retrieve"] == 1
