# ADR 0002: GitHub App for private repository access

- Status: Accepted for Phase 3 design
- Date: 2026-08-01

Implement a provider-neutral `SourceControlProvider` boundary and a GitHub App adapter first. Request read-only metadata and contents for selected repositories. Persist connection/installation identifiers and state, never installation access tokens. Mint short-lived installation tokens only at list/resolve/clone time.

Every installation and provider repository ID is resolved through the authenticated user's connection. Branches are resolved to immutable SHAs before workspace creation. Workers receive an opaque repository reference and obtain an ephemeral credential; credentials use an askpass/header mechanism, are redacted, never enter clone URLs, artifacts, job results, or frontend responses, and are discarded immediately.

GitLab and Bitbucket implement the same interface later; no buttons ship before their adapters are complete.
