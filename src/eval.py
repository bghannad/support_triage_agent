"""Evaluation harness.

Two genuinely different things get measured here:
  1. Classification: does classify_node() predict the right ticket category?
     (accuracy / precision / recall / F1 — same kind of metrics as any
     classification task.)
  2. Retrieval: does retrieve() surface the right KB doc among its top-k
     results? (recall@k, and MRR — see evaluate_retrieval() docstring for
     why these are two different questions.)

Usage:
    python src/eval.py
"""

import json
from pathlib import Path

from dotenv import load_dotenv
from sklearn.metrics import accuracy_score, classification_report

from agent import classify_node
from retrieval import retrieve as retrieve_kb

load_dotenv()

EVAL_FILE = Path(__file__).resolve().parent.parent / "data" / "eval" / "test_tickets.json"
RETRIEVAL_K = 3


def load_eval_set() -> list[dict]:
    with open(EVAL_FILE) as f:
        return json.load(f)


def evaluate_classification(tickets: list[dict]) -> dict:
    y_true, y_pred = [], []

    for t in tickets:
        result = classify_node({"ticket": t["ticket"]})
        y_true.append(t["true_category"])
        y_pred.append(result["category"])
        t["predicted_category"] = result["category"]  # stashed for the report below

    report = classification_report(y_true, y_pred, zero_division=0, output_dict=True)
    accuracy = accuracy_score(y_true, y_pred)

    return {"accuracy": accuracy, "report": report}


def evaluate_retrieval(tickets: list[dict], k: int = RETRIEVAL_K) -> dict:
    """recall@k: did the correct doc appear ANYWHERE in the top k results?
    MRR (Mean Reciprocal Rank): rewards the correct doc ranking HIGHER within
    those top k, not just being present. A doc at rank 1 scores 1.0, rank 2
    scores 0.5, rank 3 scores 0.33, absent scores 0 — so two systems can have
    identical recall@k but different MRR if one consistently ranks the right
    answer higher than the other.
    """
    scored = [t for t in tickets if t.get("expected_doc")]  # skip tickets with no correct doc
    hits = 0
    reciprocal_ranks = []

    for t in scored:
        results = retrieve_kb(t["ticket"], k=k)
        sources = [r["metadata"]["source"] for r in results]
        t["retrieved_sources"] = sources  # stashed for the report below

        if t["expected_doc"] in sources:
            hits += 1
            rank = sources.index(t["expected_doc"]) + 1  # 1-indexed --> human ranking 1,2,3,...
            reciprocal_ranks.append(1 / rank)
        else:
            reciprocal_ranks.append(0.0)

    return {
        "recall_at_k": hits / len(scored),
        "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks),
        "k": k,
        "n_scored": len(scored),
    }


def main():
    tickets = load_eval_set()
    print(f"Loaded {len(tickets)} test tickets.\n")

    print("=" * 60)
    print("CLASSIFICATION EVAL")
    print("=" * 60)
    cls = evaluate_classification(tickets)
    print(f"Accuracy: {cls['accuracy']:.2%}\n")
    for category, metrics in cls["report"].items():
        if isinstance(metrics, dict):  # skips the scalar 'accuracy' key sklearn also puts here
            print(
                f"  {category:20s} precision={metrics['precision']:.2f}  "
                f"recall={metrics['recall']:.2f}  f1={metrics['f1-score']:.2f}  "
                f"support={int(metrics['support'])}"
            )

    misses = [t for t in tickets if t["predicted_category"] != t["true_category"]]
    if misses:
        print("\nMisclassifications:")
        for t in misses:
            print(f"  [{t['true_category']} -> {t['predicted_category']}] {t['ticket'][:70]}")

    print("\n" + "=" * 60)
    print("RETRIEVAL EVAL")
    print("=" * 60)
    ret = evaluate_retrieval(tickets)
    print(
        f"Recall@{ret['k']}: {ret['recall_at_k']:.2%}  "
        f"(correct doc appeared in top {ret['k']} results)"
    )
    print(
        f"MRR: {ret['mrr']:.3f}  "
        f"(rewards the correct doc ranking HIGHER within top {ret['k']}, not just present)"
    )
    print(f"Scored on {ret['n_scored']}/{len(tickets)} tickets (some have no single correct doc)")

    ret_misses = [
        t
        for t in tickets
        if t.get("expected_doc") and t["expected_doc"] not in t.get("retrieved_sources", [])
    ]
    if ret_misses:
        print("\nRetrieval misses:")
        for t in ret_misses:
            print(f"  expected '{t['expected_doc']}', got {t['retrieved_sources']}")
            print(f"    ticket: {t['ticket'][:70]}")


if __name__ == "__main__":
    main()
