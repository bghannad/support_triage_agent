"""Shared Chroma connection logic.

Both ingest.py and retrieval.py need to connect to the same Chroma server,
the same collection, and MUST use the same distance metric. Previously that
connection code was duplicated in both files — this pulls it into one place
so the settings can't silently drift apart between them.
"""

import os

import chromadb

COLLECTION_NAME = "support_kb"

# Cosine similarity is the standard choice for comparing text embeddings —
# it measures the ANGLE between vectors (direction/meaning), ignoring their
# magnitude, which is what OpenAI's embedding models are designed around.
# Chroma fixes a collection's metric at creation time and does not allow
# changing it in place — switching requires deleting and recreating the
# collection (see reset_collection() below), then re-running ingest.py.
DISTANCE_METRIC = "cosine"


def get_client() -> chromadb.HttpClient:
    host = os.environ.get("CHROMA_HOST", "localhost")
    port = int(os.environ.get("CHROMA_PORT", "8000"))
    return chromadb.HttpClient(host=host, port=port)


def get_collection():
    client = get_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": DISTANCE_METRIC},
    )


def reset_collection():
    """Delete the collection if it exists, then recreate it fresh under the
    current DISTANCE_METRIC. Only needed when the metric itself changes (or
    you want a clean slate) — normal re-ingestion should NOT call this, since
    it throws away the upsert-in-place behavior ingest.py otherwise gives you.
    """
    client = get_client()
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"Deleted existing '{COLLECTION_NAME}' collection.")
    except Exception:
        pass  # collection didn't exist yet — nothing to delete
    return get_collection()
