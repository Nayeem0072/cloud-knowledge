# Knowledge Base

Before implementing any new feature or making changes that touch multiple services, query the centralised knowledge base:

1. Call `query_knowledge_base` with a plain-English description of what you are about to build or change.
2. If you know a specific feature is involved, call `get_feature` with its id (e.g. `feature-billing`, `feature-user-accounts`, `feature-subscriptions`).
3. For impact analysis ("what does changing X affect?"), call `query_knowledge_base` with `mode: global`.

Pay close attention to:

- **depends_on relationships** — these are hard dependencies; breaking the contract will break the dependent feature.
- **Events emitted** — downstream consumers react to these events; changing the payload or removing an event is a breaking change.
- **Business rules** — these are non-negotiable constraints that must be preserved in any implementation.
- **Known limitations** — be aware of existing tech debt before adding code that relies on the affected area.

## Services covered by the knowledge base

- `auth-service` — identity, authentication, JWT issuance
- `payments-service` — billing, invoicing, subscriptions

> Keep this list in sync with what is actually indexed. Update it whenever you add a new service's documents to the repository.
