"""Chunk support-KB docs, embed them, and load into Chroma.

Run this after:
  1. `docker compose -f docker/docker-compose.yml up -d` (starts Chroma)
  2. `.env` has a real OPENAI_API_KEY

Usage:
    python src/ingest.py
"""

import os
import sys
import glob
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from db import get_collection, reset_collection

load_dotenv()

KB_DIR = Path(__file__).resolve().parent.parent / "data" / "kb"
EMBEDDING_MODEL = "text-embedding-3-small"  # open ai cheapest way
COLLECTION_NAME = "support_kb"

# Simple chunking config. Our KB docs are short (one topic each), so most files
# end up as a single chunk — but we still chunk defensively in case a doc grows.
MAX_CHARS = 800
OVERLAP_CHARS = 100


def chunk_text(text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Split text into overlapping chunks by character count.

    Character-based chunking is crude (it can cut mid-sentence) but is simple,
    predictable, and good enough for these short docs. A production system
    would likely chunk by paragraph/section boundaries instead.
    --> ["text", "text" , ...]
    """
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunks.append(text[start:end].strip())
        start = end - overlap  # step forward, keeping some overlap for context continuity
    return [c for c in chunks if c]


def parse_doc(filepath: Path) -> tuple[str, str, str]:
    """Extract (category, title, body) from a KB markdown file.

    Expects the convention we wrote into every KB doc:
        # Category: <category>
        # Title: <title>
        <body...>
    --> tuple[str, str, str] : (category, title, body)
    """
    text = filepath.read_text(encoding="utf-8")
    lines = text.splitlines()

    category = "uncategorized"
    title = filepath.stem
    body_start = 0

    for i, line in enumerate(lines):
        if line.startswith("# Category:"):
            category = line.split(":", 1)[1].strip()
        elif line.startswith("# Title:"):
            title = line.split(":", 1)[1].strip()
        elif line.strip() and not line.startswith("#"):
            body_start = i
            break

    body = "\n".join(lines[body_start:]).strip()
    return category, title, body


# # this output is a tuple, not a dict or a custom object:
# the caller (main()) has to unpack it positionally: category, title, body = parse_doc(filepath)


# now you input list[str] of z.B 10 text chunk -> u get 10 vectors back
def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts in one API call (cheaper + faster than one-by-one)."""
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    # response.data is returned in the same order as the input list
    return [item.embedding for item in response.data]


def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or api_key.startswith("sk-...") or not api_key.startswith("sk-"):
        raise RuntimeError(
            "OPENAI_API_KEY missing or looks like a placeholder — check your .env file."
        )

    openai_client = OpenAI(api_key=api_key)

    # Connection + collection logic now lives in db.py (shared with retrieval.py)
    # so the distance metric can't drift between the two files.
    # --reset wipes and rebuilds the collection first — only needed the one time
    # DISTANCE_METRIC changes; normal runs just upsert into the existing collection.
    if "--reset" in sys.argv:
        collection = reset_collection()
    else:
        collection = get_collection()

    kb_files = sorted(glob.glob(str(KB_DIR / "*.md")))  # sorted for determinism
    if not kb_files:
        raise RuntimeError(f"No KB docs found in {KB_DIR}")

    all_ids, all_docs, all_metadatas = [], [], []

    for filepath in kb_files:
        filepath = Path(filepath)
        category, title, body = parse_doc(filepath)
        chunks = chunk_text(body)

        for i, chunk in enumerate(chunks):
            chunk_id = f"{filepath.stem}::chunk{i}"
            all_ids.append(chunk_id)
            all_docs.append(chunk)
            all_metadatas.append(
                {
                    "source": filepath.name,
                    "category": category,
                    "title": title,
                    "chunk_index": i,
                }
            )

    print(f"Prepared {len(all_docs)} chunks from {len(kb_files)} KB docs.")

    # Embed in one batch call (fine at this scale; would page into batches of ~500
    # for a much larger KB to stay under API request-size limits).
    embeddings = embed_texts(openai_client, all_docs)

    collection.upsert(
        ids=all_ids,
        embeddings=embeddings,
        documents=all_docs,
        metadatas=all_metadatas,
    )

    print(f"Upserted {len(all_docs)} chunks into Chroma collection '{COLLECTION_NAME}'.")
    print(f"Collection now has {collection.count()} total chunks.")


if __name__ == "__main__":
    main()
