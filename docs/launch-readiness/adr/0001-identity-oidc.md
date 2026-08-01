# ADR 0001: Vendor-neutral OIDC with internal identities

- Status: Accepted for Phase 1
- Date: 2026-08-01

Use standards-based OIDC. The backend independently verifies signed access tokens against issuer JWKS, audience, expiry and allowed asymmetric algorithms. `(issuer, subject)` maps to `auth_identities`; all domain ownership uses the internal `users.id`, never a vendor subject or frontend user ID.

New identities require an email claim. Verification state is retained; expensive operations require an active, verified user. Roles are stored internally and are not accepted from token claims. Docker Compose may enable an explicit static development bearer identity, but this mode is fail-closed unless deliberately enabled and is forbidden in production.

The frontend uses Authorization Code with PKCE through `oidc-client-ts`. It never decides authorization. Access tokens are held by the OIDC client and attached to API/SSE requests.
