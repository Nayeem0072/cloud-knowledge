---
id: feature-billing
type: feature
service: payments-service
depends_on:
  - feature-user-accounts
  - feature-subscriptions
related_to:
  - feature-promo-codes
owned_by: payments-team
status: stable
last_reviewed: 2026-05-21
---

## What it does

The billing feature handles all monetary transactions for the platform. It creates and manages invoices, charges payment methods via Stripe, retries failed payments according to a configurable dunning schedule, and emits events that downstream services (notifications, subscriptions) react to. Every charge is tied to a user account and, where applicable, a subscription plan.

## Business rules

1. A user must have a verified email before any charge can be initiated.
2. A payment method must be attached to the user account before invoicing.
3. Invoices are immutable once finalised — corrections require a credit note and a new invoice.
4. Failed payments are retried at 1, 3, and 7 days; after the third failure the subscription is suspended.
5. Refunds may only be issued within 30 days of the original charge.
6. Promo code discounts are applied at invoice creation time and cannot be retroactively added.
7. All amounts are stored and processed in the smallest currency unit (e.g. cents).

## Connections

- **feature-user-accounts** (`depends_on`): User identity and verified email are required before a charge can be created. Billing reads user details from the accounts service.
- **feature-subscriptions** (`depends_on`): Subscription plan and billing cycle determine invoice amounts and renewal dates.
- **feature-promo-codes** (`related_to`): Promo codes reduce invoice totals; the billing feature calls the promo service to validate and apply codes at invoice creation.

## Data model

| Entity | Key fields |
|--------|-----------|
| `Invoice` | `id`, `user_id`, `subscription_id`, `amount_cents`, `currency`, `status` (`draft`/`open`/`paid`/`void`), `due_date`, `paid_at` |
| `PaymentMethod` | `id`, `user_id`, `stripe_pm_id`, `type` (`card`/`bank`), `is_default`, `created_at` |
| `Charge` | `id`, `invoice_id`, `stripe_charge_id`, `amount_cents`, `status`, `attempted_at` |
| `DunningAttempt` | `id`, `invoice_id`, `attempt_number`, `scheduled_at`, `result` |

## Events emitted

| Event | Payload | Consumers |
|-------|---------|-----------|
| `billing.invoice.paid` | `{ invoice_id, user_id, amount_cents }` | notifications-service, subscriptions-service |
| `billing.invoice.payment_failed` | `{ invoice_id, user_id, attempt_number }` | notifications-service |
| `billing.subscription.suspended` | `{ subscription_id, user_id }` | subscriptions-service |
| `billing.refund.issued` | `{ invoice_id, refund_amount_cents }` | notifications-service |

## Known limitations

- Stripe webhook idempotency is enforced via `stripe_event_id` deduplication but there is a ~500 ms window at startup where duplicate events could slip through if the service restarts during a webhook burst.
- Multi-currency invoices (single invoice spanning multiple currencies) are not supported; each invoice is single-currency.
- Dunning schedule intervals are hardcoded in config — there is no per-plan override yet.
