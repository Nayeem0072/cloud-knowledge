"""
Seed script — ingests all docs into LightRAG in one shot.

Usage:
    python scripts/seed.py

Required environment variables:
    LIGHTRAG_URL       — e.g. https://synesis-stream-gateway.convay.com/kb
    LIGHTRAG_API_KEY   — Bearer token for LightRAG API

Optional environment variables:
    DOCS_DIR           — path to docs root (default: ./docs)
"""

import os
import sys
from pathlib import Path

# Reuse ingest logic from the existing script
sys.path.insert(0, str(Path(__file__).parent))
from ingest import ingest_file


DOCS_DIR = Path(os.environ.get("DOCS_DIR", "docs"))


def main() -> None:
    if not os.environ.get("LIGHTRAG_URL"):
        print("Error: LIGHTRAG_URL is not set", file=sys.stderr)
        sys.exit(1)
    if not os.environ.get("LIGHTRAG_API_KEY"):
        print("Error: LIGHTRAG_API_KEY is not set", file=sys.stderr)
        sys.exit(1)

    docs = sorted(DOCS_DIR.glob("**/*.md"))
    if not docs:
        print(f"No .md files found under {DOCS_DIR}/", file=sys.stderr)
        sys.exit(1)

    print(f"Seeding {len(docs)} document(s) from {DOCS_DIR}/\n")
    failed = []

    for path in docs:
        try:
            ingest_file(str(path))
        except Exception as e:
            print(f"FAILED {path}: {e}", file=sys.stderr)
            failed.append(path)

    print(f"\nDone. {len(docs) - len(failed)}/{len(docs)} succeeded.")
    if failed:
        print("Failed:", *failed, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
