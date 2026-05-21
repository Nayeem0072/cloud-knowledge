"""
Staleness check — run weekly by GitHub Actions to surface documentation gaps.

Exit code:
    0 — no issues found
    1 — issues found (GitHub Actions will surface output as job failure or annotation)

Checks performed:
    1. Missing documents: a depends_on or related_to reference that has no
       corresponding doc with that id.
    2. Stale reviews: docs where last_reviewed is older than STALE_DAYS days.
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import frontmatter  # pip install python-frontmatter


DOCS_DIR = Path(__file__).parent.parent / "docs"
STALE_DAYS = 90


def load_all_docs() -> list[tuple[Path, dict]]:
    """Return (path, metadata) for every .md file under DOCS_DIR."""
    docs = []
    for path in DOCS_DIR.rglob("*.md"):
        try:
            doc = frontmatter.load(str(path))
            docs.append((path, doc.metadata))
        except Exception as exc:
            print(f"WARNING: could not parse {path}: {exc}", file=sys.stderr)
    return docs


def check_missing_docs(docs: list[tuple[Path, dict]]) -> list[str]:
    """Return a list of issue strings for broken depends_on / related_to references."""
    known_ids = {meta.get("id") for _, meta in docs if meta.get("id")}
    issues = []

    for path, meta in docs:
        doc_id = meta.get("id", str(path))

        for dep in meta.get("depends_on") or []:
            if dep not in known_ids:
                issues.append(
                    f"[MISSING DOC] '{doc_id}' depends_on '{dep}' but no document with that id exists."
                )

        for rel in meta.get("related_to") or []:
            if rel not in known_ids:
                issues.append(
                    f"[MISSING DOC] '{doc_id}' related_to '{rel}' but no document with that id exists."
                )

    return issues


def check_stale_reviews(docs: list[tuple[Path, dict]]) -> list[str]:
    """Return a list of issue strings for docs that haven't been reviewed recently."""
    cutoff = date.today() - timedelta(days=STALE_DAYS)
    issues = []

    for path, meta in docs:
        doc_id = meta.get("id", str(path))
        last_reviewed = meta.get("last_reviewed")

        if last_reviewed is None:
            issues.append(
                f"[STALE] '{doc_id}' has no last_reviewed date."
            )
            continue

        # frontmatter may return a date object or a string
        if isinstance(last_reviewed, str):
            try:
                last_reviewed = date.fromisoformat(last_reviewed)
            except ValueError:
                issues.append(
                    f"[STALE] '{doc_id}' has an unparseable last_reviewed value: {last_reviewed!r}"
                )
                continue

        if isinstance(last_reviewed, date) and last_reviewed < cutoff:
            days_old = (date.today() - last_reviewed).days
            issues.append(
                f"[STALE] '{doc_id}' was last reviewed {days_old} days ago (last_reviewed: {last_reviewed})."
            )

    return issues


def main() -> None:
    docs = load_all_docs()

    if not docs:
        print(f"No documents found under {DOCS_DIR}.")
        sys.exit(0)

    print(f"Checking {len(docs)} documents...\n")

    missing = check_missing_docs(docs)
    stale = check_stale_reviews(docs)
    all_issues = missing + stale

    if not all_issues:
        print("All checks passed — no missing docs or stale reviews.")
        sys.exit(0)

    print(f"Found {len(all_issues)} issue(s):\n")
    for issue in all_issues:
        print(f"  {issue}")

    sys.exit(1)


if __name__ == "__main__":
    main()
