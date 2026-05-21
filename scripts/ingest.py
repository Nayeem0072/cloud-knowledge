"""
Ingest script — called by the GitHub Action to upsert or delete knowledge base docs.

Usage:
    python scripts/ingest.py upsert docs/features/billing.md
    python scripts/ingest.py delete docs/features/billing.md

Required environment variables:
    LIGHTRAG_URL       — e.g. https://kb-production.up.railway.app
    LIGHTRAG_API_KEY   — Bearer token for LightRAG API
"""

import sys
import json
import os
import requests
import frontmatter  # pip install python-frontmatter


LIGHTRAG_URL = os.environ["LIGHTRAG_URL"].rstrip("/")
LIGHTRAG_KEY = os.environ["LIGHTRAG_API_KEY"]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {LIGHTRAG_KEY}",
        "Content-Type": "application/json",
    }


def build_triples_preamble(meta: dict) -> str:
    """
    Convert frontmatter fields into explicit RELATION triples.

    LightRAG extracts graph edges from prose via an LLM pass, which is
    non-deterministic. Prepending explicit triples ensures that the edges
    defined in frontmatter always appear in the graph, regardless of how
    the LLM interprets the prose.
    """
    lines = []
    fid = meta.get("id", "")

    for dep in meta.get("depends_on") or []:
        lines.append(f"RELATION: {fid} depends_on {dep}")

    for rel in meta.get("related_to") or []:
        lines.append(f"RELATION: {fid} related_to {rel}")

    if meta.get("service"):
        lines.append(f"RELATION: {fid} owned_by_service {meta['service']}")

    if meta.get("owned_by"):
        lines.append(f"RELATION: {fid} owned_by_team {meta['owned_by']}")

    if meta.get("type"):
        lines.append(f"ENTITY_TYPE: {fid} is_type {meta['type']}")

    return "\n".join(lines)


def ingest_file(path: str) -> None:
    """Load a Markdown file, prepend graph triples, and POST to LightRAG /insert."""
    doc = frontmatter.load(path)
    preamble = build_triples_preamble(doc.metadata)
    content = (preamble + "\n\n" + doc.content) if preamble else doc.content

    payload = {
        "content": content,
        "metadata": {"source": path, **doc.metadata},
    }

    resp = requests.post(
        f"{LIGHTRAG_URL}/insert",
        headers=_headers(),
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    print(f"Ingested {path} → {resp.status_code}")


def delete_file(path: str) -> None:
    """Remove a document from the LightRAG index by its source path."""
    payload = {"filter": {"source": path}}

    resp = requests.post(
        f"{LIGHTRAG_URL}/delete",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    # 404 is acceptable — doc may never have been indexed
    if resp.status_code not in (200, 204, 404):
        resp.raise_for_status()
    print(f"Deleted {path} → {resp.status_code}")


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: ingest.py <upsert|delete> <path>", file=sys.stderr)
        sys.exit(1)

    action, path = sys.argv[1], sys.argv[2]

    if action == "upsert":
        ingest_file(path)
    elif action == "delete":
        delete_file(path)
    else:
        print(f"Unknown action: {action!r}. Use 'upsert' or 'delete'.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
