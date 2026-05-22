# Workflow Guide

End-to-end walkthrough of how the knowledge base works — from writing a doc to Claude Code using it.

---

## How it all fits together

```
You write/edit a .md file in docs/
  └─► git push to main
        └─► GitHub Action (ingest.yml) fires
              └─► scripts/ingest.py upsert <file>
                    └─► LightRAG /insert (OCI VM)
                          ├─► vector index updated
                          └─► graph triples extracted
                                └─► MCP server (OCI VM)
                                      └─► Claude Code queries it
```

Claude Code never reads this repo directly. It talks to the MCP server, which talks to LightRAG.

---

## 1. Writing a document

Every file under `docs/` must follow the schema. Here is a minimal example:

**`docs/features/notifications.md`**
```markdown
---
id: feature-notifications
type: feature
service: notifications-service
depends_on:
  - feature-user-accounts
related_to:
  - feature-billing
owned_by: platform-team
status: stable
last_reviewed: 2026-05-22
---

## What it does

Sends transactional emails and push notifications to users. Triggered exclusively
by events from other services — it has no user-facing API of its own.

## Business rules

1. Notifications are fire-and-forget — delivery failures are logged but do not
   propagate errors back to the emitting service.
2. A user can opt out of non-critical notifications via account preferences.
3. Critical notifications (payment failure, security alerts) ignore opt-out settings.

## Connections

- **feature-user-accounts** (`depends_on`): User email and preferences are read
  from the accounts service before dispatch.
- **feature-billing** (`related_to`): Listens to `billing.invoice.paid` and
  `billing.invoice.payment_failed` events.

## Data model

| Entity | Key fields |
|--------|-----------|
| `NotificationLog` | `id`, `user_id`, `type`, `channel` (`email`/`push`), `sent_at`, `status` |

## Events emitted

None — this service only consumes events.

## Known limitations

- Email delivery is synchronous in the critical path; under high load this can
  add up to 200 ms latency to the emitting service's response time.
- Push notifications require a valid FCM/APNs token; stale tokens are not
  automatically pruned.
```

**Rules to follow:**
- `id` must be kebab-case and globally unique across all docs
- All six H2 sections must be present, in order
- `depends_on` = hard dependency (breaking the contract breaks this feature)
- `related_to` = soft relationship (informational, not a hard dependency)

---

## 2. Getting a document into the index

### Automatically (normal path)

Push or merge to `main`. The `ingest.yml` workflow detects which `docs/**/*.md`
files were added, modified, or deleted and calls `ingest.py` for each one.

```
git add docs/features/notifications.md
git commit -m "feat: add notifications feature doc"
git push origin main
# GitHub Action runs ingest.py upsert automatically
```

### Manually (first-time seed or re-index)

```bash
pip install requests python-frontmatter

export LIGHTRAG_URL=https://<your-domain>/lightrag
export LIGHTRAG_API_KEY=<your-lightrag-api-key>

# Single file
python scripts/ingest.py upsert docs/features/notifications.md

# All files
for f in docs/features/*.md docs/services/*.md; do
  python scripts/ingest.py upsert "$f"
done
```

### Deleting a document

Delete the file and push. The Action calls `ingest.py delete` automatically.
Or manually:

```bash
python scripts/ingest.py delete docs/features/old-feature.md
```

---

## 3. What ingest.py does internally

For each file it:

1. Parses the YAML frontmatter
2. Converts frontmatter fields into explicit graph triples, e.g.:

   ```
   RELATION: feature-notifications depends_on feature-user-accounts
   RELATION: feature-notifications related_to feature-billing
   RELATION: feature-notifications owned_by_service notifications-service
   ENTITY_TYPE: feature-notifications is_type feature
   ```

3. Prepends those triples to the Markdown body
4. POSTs the combined content to `POST /insert` on LightRAG

LightRAG then runs an LLM pass to extract additional entities and edges, and
updates both the vector index and the NetworkX graph. The explicit triples in
step 2 guarantee that frontmatter relationships always appear in the graph even
if the LLM extraction misses them.

---

## 4. How Claude Code queries the knowledge base

Claude Code talks to the MCP server via three tools:

### `query_knowledge_base` — open-ended questions

Use this for anything that requires reasoning across multiple docs.

```
query: "what services does the billing feature depend on?"
mode: "hybrid"   # default — graph + vector combined
```

```
query: "what breaks if I change the user account schema?"
mode: "global"   # full graph traversal — best for impact analysis
```

```
query: "how does invoice payment retry work?"
mode: "local"    # nearest-neighbour — best for narrow, specific questions
```

**Modes at a glance:**

| Mode | Best for |
|------|----------|
| `hybrid` | General questions — combines graph and vector |
| `global` | Impact analysis — "what is affected by X?" |
| `local` | Narrow lookups — details about one feature |
| `naive` | Pure vector search, no graph — last resort |

### `get_feature` — fetch a specific doc

```
get_feature(feature_id="feature-billing")
```

Returns the feature node and its immediate graph edges. Use this when you already
know which feature you're looking at.

### `list_features` — discover what's indexed

```
list_features()                          # all features
list_features(service="payments-service") # filtered by service
```

---

## 5. Example: adding a new feature that touches billing

**Scenario:** You're building a refund portal. Before writing code, Claude Code
should query the knowledge base:

```
query_knowledge_base("refund flow, billing rules, payment methods")
→ Returns: billing business rules, 30-day refund window, immutable invoices,
           credit note requirement, events emitted by billing

get_feature("feature-billing")
→ Returns: full billing doc including depends_on, events, data model
```

Claude Code now knows:
- Refunds must be issued within 30 days (business rule 5)
- Invoices are immutable — a credit note is required (business rule 3)
- `billing.refund.issued` event must be emitted with `{ invoice_id, refund_amount_cents }`
- `notifications-service` is a downstream consumer of that event

After implementing, you write a doc:

**`docs/features/refund-portal.md`**
```markdown
---
id: feature-refund-portal
type: feature
service: payments-service
depends_on:
  - feature-billing
  - feature-user-accounts
related_to:
  - feature-subscriptions
owned_by: payments-team
status: beta
last_reviewed: 2026-05-22
---
...
```

Push it — the Action ingests it automatically, and the graph now includes
`feature-refund-portal depends_on feature-billing`.

---

## 6. Staleness checks

Every Monday at 09:00 UTC, `staleness.yml` runs `scripts/staleness_check.py`.
It fails the job (exit code 1) if it finds:

- A `depends_on` or `related_to` reference pointing to an `id` that has no
  corresponding document
- A document whose `last_reviewed` date is more than 90 days ago

**Example output when issues are found:**

```
Checking 5 documents...

Found 2 issue(s):

  [MISSING DOC] 'feature-billing' depends_on 'feature-subscriptions' but no document with that id exists.
  [STALE] 'feature-user-accounts' was last reviewed 97 days ago (last_reviewed: 2026-02-14).
```

**To fix a stale doc:** update the content if needed, bump `last_reviewed` to
today, and push.

**To run it manually:**

```bash
pip install python-frontmatter
python scripts/staleness_check.py
```

---

## 7. Adding a new service

1. Create one or more docs under `docs/services/` and/or `docs/features/`
2. Update the services list in `CLAUDE.md`:
   ```
   - `notifications-service` — transactional email and push notifications
   ```
3. Push — the Action ingests everything automatically

---

## 8. Updating an existing document

Edit the file, bump `last_reviewed` to today, push. The Action detects the
modified file and re-ingests it (upsert replaces the existing index entry).

```bash
# Check which docs are stale before editing
python scripts/staleness_check.py
```
