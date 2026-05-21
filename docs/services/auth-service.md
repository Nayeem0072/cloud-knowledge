---
id: service-auth
type: service
service: auth-service
depends_on: []
related_to:
  - service-payments
owned_by: identity-team
status: stable
last_reviewed: 2026-05-21
---

## What it does

The auth service is the platform's identity provider. It manages user registration, authentication, session management, and token issuance. All other services trust its JWTs to identify callers. It exposes a public JWKS endpoint (`/.well-known/jwks.json`) used by downstream services to validate tokens without making a network call to the auth service on every request.

## Business rules

1. JWTs are signed with RS256; the key pair is rotated every 90 days with a 24-hour overlap window.
2. Access tokens expire in 15 minutes; refresh tokens expire in 30 days.
3. Refresh tokens are single-use — each refresh issues a new pair and invalidates the old refresh token.
4. The service validates email ownership before marking the account as verified (see `feature-user-accounts`).
5. Rate limiting: max 10 token requests per IP per minute; max 5 password reset requests per email per hour.
6. All authentication events (login, logout, token refresh, failed attempts) are written to an immutable audit log.

## Connections

- No upstream service dependencies at runtime — the auth service is the root of the trust chain.
- **service-payments** (`related_to`): The payments service validates JWTs issued by this service on every inbound API call.

## Data model

Core tables: `users`, `sessions`, `email_verification_tokens`, `password_reset_tokens`, `login_attempts`, `audit_log`.

See `feature-user-accounts` for detailed field lists.

## Events emitted

All events are published to the `accounts.*` topic. See `feature-user-accounts` for the full event catalogue.

## Known limitations

- JWKS is cached in-memory by downstream services with a 5-minute TTL — there is up to a 5-minute window where a revoked key is still accepted after rotation.
- The audit log is append-only in the database but is not shipped to an external SIEM yet — forensic queries require direct DB access.
- There is no support for SAML or OIDC federation — all auth is username/password or OAuth2 (Google, GitHub).
