#!/bin/sh
# Startup sequence for the app container:
#   1. wait for the Chroma container to actually be reachable (it starts
#      empty and takes a moment to come up — without this, ingest.py would
#      fail trying to connect to a Chroma that isn't listening yet)
#   2. seed the knowledge base (safe to run every time: ingest.py upserts,
#      it doesn't duplicate on a re-run)
#   3. start the actual app
set -e

echo "Waiting for Chroma at $CHROMA_HOST:$CHROMA_PORT..."
python - << 'PYEOF'
import os
import time

import chromadb

host = os.environ.get("CHROMA_HOST", "localhost")
port = int(os.environ.get("CHROMA_PORT", "8000"))

for attempt in range(30):
    try:
        chromadb.HttpClient(host=host, port=port).heartbeat()
        print("Chroma is up.")
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit(f"Chroma at {host}:{port} never became reachable after 60s.")
PYEOF

echo "Seeding knowledge base..."
python src/ingest.py

echo "Starting app..."
exec python app.py
