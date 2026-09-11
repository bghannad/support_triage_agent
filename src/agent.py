"""LangGraph graph: classify -> retrieve -> tool_call -> decide -> answer/escalate.

This is the actual "agent" — it wraps the retrieval you already built and
tested (retrieval.py) inside a stateful graph that also classifies the
ticket, optionally calls a mocked tool, and branches between auto-answering
and escalating to a human.

Usage (manual test):
    python src/agent.py "I was charged twice this month, can I get a refund?"
"""

import os
import sys
from typing import Literal, TypedDict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from retrieval import retrieve as retrieve_kb
from tools import check_account_status

load_dotenv()

# Cheap/fast model for both classification and answer drafting. Overridable
# via .env in case pricing/availability changes which "mini" model is best.
MODEL_NAME = os.environ.get("AGENT_MODEL", "gpt-4o-mini")

CONFIDENCE_THRESHOLD = 0.6
TOOL_ELIGIBLE_CATEGORIES = {"billing", "account_access"}


# ---------------------------------------------------------------------------
# State: one dict that flows through every node, accumulating fields.
# total=False because most fields don't exist yet when the graph starts —
# only "ticket" is present at the entry point.
# ---------------------------------------------------------------------------
class TicketState(TypedDict, total=False):
    ticket: str
    category: str
    confidence: float
    classification_reasoning: str
    retrieved_docs: list[dict]
    tool_result: dict | None
    decision: Literal["auto_answer", "escalate"]
    escalation_reason: str
    response: str


# Structured-output schema for the classify node. Using a Pydantic model
# instead of asking the LLM to "return JSON" in a prompt and hoping it behaves
# with_structured_output() below guarantees a validated object
# back, not a raw string we then have to parse and hope doesn't break.
class ClassificationResult(BaseModel):
    category: Literal["billing", "account_access", "technical", "security", "other"]
    confidence: float = Field(ge=0, le=1, description="0-1 confidence in this classification")
    reasoning: str = Field(description="One sentence explaining the classification")


# -----------------------------------------------------------------------------
# Nodes — each takes the current state, does one job, returns a dict of the
# fields it wants to update.
# LangGraph merges that dict into the state before passing it to the next node.
# -----------------------------------------------------------------------------


def classify_node(state: TicketState) -> dict:
    llm = ChatOpenAI(model=MODEL_NAME, temperature=0)
    structured_llm = llm.with_structured_output(ClassificationResult)

    result = structured_llm.invoke(
        "Classify this customer support ticket into exactly one category: "
        "billing, account_access, technical, security, or other. "
        "Give a confidence score between 0 and 1, and a one-sentence reason.\n\n"
        f"Ticket: {state['ticket']}"
    )

    return {
        "category": result.category,
        "confidence": result.confidence,
        "classification_reasoning": result.reasoning,
    }


def retrieve_node(state: TicketState) -> dict:
    # Reuses the exact retrieve() function you already tested standalone —
    # the agent doesn't reimplement RAG, it just calls into it.
    hits = retrieve_kb(state["ticket"], k=3)
    return {"retrieved_docs": hits}


def tool_call_node(state: TicketState) -> dict:
    # Simplification explained = this decision (call the tool or don't) is
    # hardcoded on category, not decided by theb LLM itself via function-calling.
    # A more sophisticated version would let the model choose dynamically.
    if state.get("category") not in TOOL_ELIGIBLE_CATEGORIES:
        return {"tool_result": None}

    result = check_account_status(state["ticket"])
    return {"tool_result": result}


def decide_node(state: TicketState) -> dict:
    """Decide auto_answer vs escalate, and WHY.

    This is a real node (not just an edge-selector function) specifically so
    the reason gets written into state — visible in logs/traces, and usable
    by escalate_node to explain itself, rather than being a decision that
    happens invisibly.
    """
    if state.get("category") == "security":
        return {
            "decision": "escalate",
            "escalation_reason": "Security-related ticket — always routed to a human per policy.",
        }

    confidence = state.get("confidence", 0.0)
    if confidence < CONFIDENCE_THRESHOLD:
        return {
            "decision": "escalate",
            "escalation_reason": (
                f"Classification confidence too low ({confidence:.2f} < {CONFIDENCE_THRESHOLD})."
            ),
        }

    tool_result = state.get("tool_result")
    if tool_result and tool_result.get("account_status") == "locked":
        return {
            "decision": "escalate",
            "escalation_reason": "Account is locked — needs human verification before proceeding.",
        }

    return {"decision": "auto_answer", "escalation_reason": ""}


def route_after_decision(state: TicketState) -> str:
    """Edge-selector: just reads the decision decide_node already computed
    and stored. All the actual logic lives in decide_node, above — this
    function's only job is picking which node to go to next."""
    return state["decision"]


def answer_node(state: TicketState) -> dict:
    llm = ChatOpenAI(model=MODEL_NAME, temperature=0.3)

    context = "\n\n".join(
        f"[{doc['metadata']['title']}]\n{doc['document']}"
        for doc in state.get("retrieved_docs", [])
    )

    prompt = (
        "You are a support agent. Answer the customer's ticket using ONLY the "
        "knowledge base context below. Be concise and direct. If the context "
        "doesn't fully cover the question, say so honestly rather than guessing.\n\n"
        f"Knowledge base context:\n{context}\n\n"
        f"Customer ticket: {state['ticket']}"
    )

    result = llm.invoke(prompt)
    return {"response": result.content}


def escalate_node(state: TicketState) -> dict:
    message = (
        "This ticket has been escalated to a human support agent. "
        f"Reason: {state.get('escalation_reason', 'unspecified')}"
    )
    return {"response": message}


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------


def build_graph():
    graph = StateGraph(TicketState)

    graph.add_node("classify", classify_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("tool_call", tool_call_node)
    graph.add_node("decide", decide_node)
    graph.add_node("answer", answer_node)
    graph.add_node("escalate", escalate_node)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "retrieve")
    graph.add_edge("retrieve", "tool_call")
    graph.add_edge("tool_call", "decide")
    graph.add_conditional_edges(
        "decide",
        route_after_decision,
        {"auto_answer": "answer", "escalate": "escalate"},
    )
    graph.add_edge("answer", END)
    graph.add_edge("escalate", END)

    return graph.compile()


if __name__ == "__main__":
    app = build_graph()

    ticket = " ".join(sys.argv[1:]) or "I was charged twice this month, can I get a refund?"
    print(f"Ticket: {ticket}\n")

    final_state = app.invoke({"ticket": ticket})

    print(f"Category: {final_state['category']}  (confidence={final_state['confidence']:.2f})")
    print(f"Classification reasoning: {final_state['classification_reasoning']}")
    if final_state.get("tool_result"):
        print(f"Tool result: {final_state['tool_result']}")
    print(f"Decision: {final_state['decision']}")
    if final_state.get("escalation_reason"):
        print(f"Escalation reason: {final_state['escalation_reason']}")
    print(f"\nResponse:\n{final_state['response']}")
