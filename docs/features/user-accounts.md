---
id: feature-user-accounts
type: feature
service: auth-service
depends_on: []
related_to:
  - feature-billing
  - feature-subscriptions
owned_by: identity-team
status: stable
last_reviewed: 2026-05-21
---

## What it does

The user accounts feature manages the full lifecycle of a platform user: registration, email verification, profile management, password reset, and soft deletion. It is the root identity source that all other features depend on. The auth service issues JWTs on successful login; downstream services validate tokens against the public JWKS endpoint.

## Business rules

1. Email addresses must be unique across all accounts (including soft-deleted ones).
2. A user cannot perform any billable action until their email is verified.
3. Passwords must be at least 12 characters and pass the zxcvbn strength check (score ≥ 3).
4. Accounts are soft-deleted — hard deletion requires a separate GDPR erasure job.
5. A user may have at most one active session per device (tracked by device fingerprint).
6. Password reset tokens expire after 1 hour and are single-use.
7. After 5 consecutive failed login attempts the account is locked for 15 minutes.

## Connections

- No hard dependencies on other features — this is the foundational identity service.
- **feature-billing** (`related_to`): Billing reads `user_id`, `email`, and `email_verified` from this service before initiating charges.
- **feature-subscriptions** (`related_to`): Subscriptions are scoped to a `user_id` from this service.

## Data model

| Entity | Key fields |
|--------|-----------|
| `User` | `id` (UUID), `email`, `email_verified` (bool), `password_hash`, `status` (`active`/`locked`/`deleted`), `created_at`, `deleted_at` |
| `EmailVerificationToken` | `id`, `user_id`, `token_hash`, `expires_at`, `used_at` |
| `PasswordResetToken` | `id`, `user_id`, `token_hash`, `expires_at`, `used_at` |
| `Session` | `id`, `user_id`, `device_fingerprint`, `jwt_jti`, `expires_at`, `revoked_at` |
| `LoginAttempt` | `id`, `user_id`, `ip`, `success` (bool), `attempted_at` |

## Events emitted

| Event | Payload | Consumers |
|-------|---------|-----------|
| `accounts.user.created` | `{ user_id, email }` | notifications-service |
| `accounts.user.email_verified` | `{ user_id }` | billing-service, subscriptions-service |
| `accounts.user.deleted` | `{ user_id }` | billing-service, subscriptions-service, notifications-service |
| `accounts.user.locked` | `{ user_id, locked_until }` | notifications-service |

## Known limitations

- The JWKS key rotation currently requires a rolling restart of all services that cache the public key — there is no push-based key invalidation.
- Device fingerprinting relies on `User-Agent` + IP; it is not reliable for users on mobile networks with rotating IPs.
- GDPR erasure job runs nightly in batch — there can be up to 24 hours between deletion request and actual data removal.
