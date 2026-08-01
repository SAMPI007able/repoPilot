# ADR 0004: PostgreSQL-authoritative atomic quota reservations

- Status: Accepted for Phase 2 design
- Date: 2026-08-01

All expensive operations call one `QuotaService`. A PostgreSQL transaction locks the principal usage account, evaluates entitlements plus active reservations, and creates an idempotent `RESERVED` row before job submission. Job success commits measured usage; failure releases unused capacity. Expired reservations are reconciled from durable rows.

Redis may accelerate rate limits and concurrent counters, but Redis loss cannot grant durable capacity or erase accounting. PostgreSQL constraints on `(principal, resource, idempotency_key)` prevent duplicate reservations. Free-beta limits are configuration-seeded entitlements, not route constants.
