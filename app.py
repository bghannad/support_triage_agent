"""Demo UI for the Support-Ticket Triage Agent, built with Gradio.

Paste a ticket in, see the full agent trace: classification, retrieved KB
context, tool result (if any), the escalation decision and why, and the
final response — not just the final answer, the whole reasoning path.

Usage:
    python app.py
Then open http://localhost:7860
"""

import os
import sys
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

# agent.py (and its own imports of retrieval.py/tools.py) expect to run with
# src/ on the import path — true when you run "python src/agent.py" directly,
# but NOT true here, since app.py lives at the project root. Add src/ to the
# path explicitly so "from agent import build_graph" resolves the same way.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from agent import build_graph

load_dotenv()

# Built once at startup, reused across requests — compiling the graph is
# cheap, but there's no reason to redo it on every single ticket submitted.
_app = build_graph()


def run_ticket(ticket: str):
    if not ticket or not ticket.strip():
        return "Category: —", "Tool result: —", "Decision: —", "Enter a ticket above."

    final_state = _app.invoke({"ticket": ticket})

    category_line = (
        f"{final_state['category']}  (confidence={final_state['confidence']:.2f})\n"
        f"Reasoning: {final_state['classification_reasoning']}"
    )

    tool_result = final_state.get("tool_result")
    tool_line = str(tool_result) if tool_result else "Not called (category doesn't require it)"

    decision_line = final_state["decision"]
    if final_state.get("escalation_reason"):
        decision_line += f"\nReason: {final_state['escalation_reason']}"

    return category_line, tool_line, decision_line, final_state["response"]


with gr.Blocks(title="Support-Ticket Triage Agent") as demo:
    gr.Markdown(
        "# Support-Ticket Triage Agent\n"
        "Classify → RAG retrieve → tool-call → decide → answer/escalate. "
        "Try one of the examples below, or write your own ticket."
    )

    ticket_input = gr.Textbox(
        label="Support ticket",
        placeholder="e.g. I was charged twice this month, can I get a refund?",
        lines=3,
    )
    submit_btn = gr.Button("Run through the agent", variant="primary")

    with gr.Row():
        category_out = gr.Textbox(label="1. Classification", interactive=False)
        tool_out = gr.Textbox(label="2. Tool result", interactive=False)
        decision_out = gr.Textbox(label="3. Decision", interactive=False)

    response_out = gr.Textbox(label="4. Response", interactive=False, lines=4)

    submit_btn.click(
        fn=run_ticket,
        inputs=ticket_input,
        outputs=[category_out, tool_out, decision_out, response_out],
    )

    gr.Examples(
        examples=[
            "I was charged twice this month, can I get a refund?",
            "I think someone accessed my account without permission",
            "My files aren't syncing between my laptop and phone anymore",
            "It says my account is locked, I tried logging in too many times",
        ],
        inputs=ticket_input,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)
