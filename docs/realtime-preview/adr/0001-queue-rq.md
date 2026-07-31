# ADR 0001: Use Redis Queue for preview orchestration

- Status: Accepted for Phase 2
- Date: 2026-07-31

## Decision

Use Redis Queue (RQ) with separate worker processes for preview orchestration. PostgreSQL remains lifecycle truth; Redis carries jobs and short-lived coordination only.

## Rationale

The current Python service is synchronous, compact, and service-oriented. RQ provides explicit jobs, retries, timeouts, registries, and simple operational behavior without Celery's larger configuration surface. It also removes execution from the FastAPI process, unlike the current indexing thread pool.

## Consequences

- Workers must make every job and cleanup operation idempotent.
- Durable state is written before and after queue submission to survive Redis loss.
- Scheduled reconciliation requires `rq-scheduler` or a dedicated scheduler process.
- If workflow complexity later requires DAGs or high-scale routing, this ADR must be revisited rather than hiding orchestration in job functions.
