---
id: feature-subscriptions
type: feature
service: payments-service
depends_on:
  - feature-user-accounts
  - feature-billing
related_to:
  - feature-promo-codes
owned_by: payments-team
status: stable
last_reviewed: 2026-05-21
---

## What it does

The subscriptions feature manages recurring plan membership for users. It tracks which plan a user is on, when their current period ends, and coordinates with billing to trigger renewal invoices. It enforces plan-level feature flags (what the user is allowed to do given their tier) and handles plan upgrades, downgrades, and cancellations including proration.

## Business rules

1. A user may have at most one active subscription at a time.
2. Plan downgrades take effect at the end of the current billing period; upgrades take effect immediately with proration.
3. A cancelled subscription remains active until the period end date — it is never terminated mid-period.
4. Suspended subscriptions (due to billing failure) block access to paid features but are not cancelled.
5. Trial periods are capped at 14 days and are available only once per user (not once per plan).
6. Plan changes must be reflected in the billing invoice within 5 seconds (synchronous call to billing service).

## Connections

- **feature-user-accounts** (`depends_on`): A subscription must be linked to a verified user account.
- **feature-billing** (`depends_on`): Billing creates and collects renewal invoices; subscriptions react to `billing.invoice.paid` and `billing.subscription.suspended` events.
- **feature-promo-codes** (`related_to`): Promo codes can grant extended trials or discounted first periods — the subscriptions service validates eligibility with the promo service.

## Data model

| Entity | Key fields |
|--------|-----------|
| `Subscription` | `id`, `user_id`, `plan_id`, `status` (`trialing`/`active`/`past_due`/`suspended`/`cancelled`), `current_period_start`, `current_period_end`, `cancel_at_period_end` (bool) |
| `Plan` | `id`, `name`, `price_cents`, `currency`, `interval` (`month`/`year`), `trial_days`, `feature_flags` (jsonb) |
| `SubscriptionEvent` | `id`, `subscription_id`, `type` (`created`/`upgraded`/`downgraded`/`cancelled`/`suspended`/`reactivated`), `occurred_at`, `metadata` (jsonb) |

## Events emitted

| Event | Payload | Consumers |
|-------|---------|-----------|
| `subscriptions.subscription.created` | `{ subscription_id, user_id, plan_id }` | notifications-service |
| `subscriptions.subscription.upgraded` | `{ subscription_id, from_plan_id, to_plan_id }` | notifications-service |
| `subscriptions.subscription.cancelled` | `{ subscription_id, user_id, ends_at }` | notifications-service |
| `subscriptions.subscription.expired` | `{ subscription_id, user_id }` | notifications-service, billing-service |

## Known limitations

- Proration calculation uses a simple day-count ratio and does not account for months with varying lengths — can be off by a few cents on monthly plans.
- There is no support for seat-based (per-user) pricing — all plans are flat-rate.
- The feature flags jsonb column has no schema validation — bad values fail silently at the application layer.
