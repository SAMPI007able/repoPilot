# ADR 0005: Append-only durable usage ledger

- Status: Accepted for Phase 2 design
- Date: 2026-08-01

`usage_events` is an append-only PostgreSQL ledger of measured resource quantities with user, workspace/preview/session attribution and safe metadata. Corrections are compensating events, never updates. Materialized `usage_counters` may accelerate summaries but are rebuildable from the ledger.

Window boundaries are calculated in UTC and summaries include usage, hard limit, remaining quantity, reset time and active reservations. Billing is outside scope; plan and entitlement records remain independent of a payment provider.
