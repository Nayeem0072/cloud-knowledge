---
id: service-payments
type: service
service: payments-service
depends_on:
  - service-auth
related_to: []
owned_by: payments-team
status: stable
last_reviewed: 2026-05-21
---

## What it does

The payments service is the financial backbone of the platform. It owns all billing and subscription logic, integrates with Stripe as the payment processor, and is the authoritative source of truth for plan membership and invoice state. It exposes a REST API consumed by the frontend and by other backend services, and publishes domain events to the internal event bus.

## Business rules

1. All writes to Stripe are idempotent — every API call includes an `Idempotency-Key` derived from the internal resource ID.
2. Stripe webhook delivery is the only mechanism for updating charge and refund status — polling is not used.
3. The service must not store raw card numbers or CVVs at any point; PCI scope is limited to Stripe tokens.
4. Database transactions wrap both the local state update and the event publish — events are stored in an outbox table before being relayed to the bus.
5. All financial calculations use integer arithmetic in the smallest currency unit; floating-point is never used for money.

## Connections

- **service-auth** (`depends_on`): Every inbound API request is authenticated by validating the JWT against the auth service JWKS endpoint.

## Data model

Core tables: `invoices`, `charges`, `dunning_attempts`, `subscriptions`, `plans`, `subscription_events`, `payment_methods`, `outbox_events`.

See feature-specific docs (`feature-billing`, `feature-subscriptions`) for detailed field lists.

## Events emitted

All events are published to the `payments.*` topic on the internal event bus. See `feature-billing` and `feature-subscriptions` for the full event catalogue.

## Known limitations

- The service is a monolith — billing and subscriptions share a single database and deploy unit. Splitting them requires a non-trivial data migration.
- There is no read replica; all reads hit the primary database, which becomes a bottleneck during invoice generation batches (end of month).
- Stripe test-mode and live-mode keys are selected via an environment variable — there is no runtime safeguard preventing accidental test-mode charges in production.
