# ADR 0004: Gateway abstraction and isolated preview domain

- Status: Accepted for Phase 3
- Date: 2026-07-31

## Decision

Introduce `PreviewGateway`. Production uses Kubernetes Gateway API when available, with an Ingress implementation as a compatibility adapter. Preview hostnames contain cryptographically random identifiers under a registrable domain isolated from the authenticated TestForge application.

Routes require signed expiring access by default, support WebSockets/TLS, add preview-security headers, and are revoked during stop/expiry cleanup. Predictable IDs and control-plane cookies are forbidden on preview hosts.

## Consequences

DNS wildcard and cert-manager-compatible TLS are deployment prerequisites. Preview URLs are sensitive and must not appear in logs or tracing attributes.
