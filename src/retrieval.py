"""Query the Chroma collection for relevant KB chunks given a ticket/question.

Usage (manual test):
    python src/retrieval.py "I was charged twice this month, can I get a refund?"
"""

import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

from db import get_collection

load_dotenv()

EMBEDDING_MODEL = "text-embedding-3-small"


def retrieve(query: str, k: int = 3) -> list[dict]:
    """Return the top-k most relevant KB chunks for a query.

    Each result: {"document": chunk text, "metadata": {...}, "distance": float}
    Lower distance = more similar. Metric is cosine (set once, in db.py) —
    measures angle between vectors, the standard choice for text embeddings.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    openai_client = OpenAI(api_key=api_key)

    query_embedding = (
        openai_client.embeddings.create(model=EMBEDDING_MODEL, input=[query]).data[0].embedding
    )

    collection = get_collection()
    results = collection.query(query_embeddings=[query_embedding], n_results=k)
    # print("result inside retriev from chroma", results)

    hits = []
    # zip : walks these three lists at the same index simultaneously
    for doc, metadata, distance in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        hits.append({"document": doc, "metadata": metadata, "distance": distance})
    return hits


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "How do I reset my password?"
    print(f"Query: {query}\n")

    for rank, hit in enumerate(retrieve(query, k=3), start=1):
        print(
            f"#{rank}  [{hit['metadata']['category']}] {hit['metadata']['title']}  "
            f"(distance={hit['distance']:.4f})"
        )
        print(f"    {hit['document'][:150]}...")
        print()
