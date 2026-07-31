# ADR 0005: Store secret references, never recoverable plaintext

- Status: Accepted for Phase 2+
- Date: 2026-07-31

## Decision

Runtime manifests contain environment-variable names, never values. Secret submissions use a dedicated endpoint and an environment-specific secret provider. Production stores envelope-encrypted values or Kubernetes Secret references backed by a managed secret system. Database rows retain only opaque references and audit metadata.

The UI never receives a persisted value after submission. Secrets are excluded from AI prompts, logs, events, errors, screenshots metadata, and OpenTelemetry attributes. Local development may use process-memory or an explicitly local encrypted store, with a visible non-production warning.

## Consequences

Secret rotation and deletion are independent lifecycle operations. Redaction is defense in depth, not permission to log broad environment/process payloads.
