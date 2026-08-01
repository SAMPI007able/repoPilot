# Launch-readiness threat model

| Threat | Phase controls |
|---|---|
| Account takeover/token replay | Managed OIDC, asymmetric signature/audience/issuer/time validation, short token lifetime, provider MFA policy, no passwords in TestForge. |
| Email/subject confusion | Identity key is exact `(issuer, subject)`; email never authenticates or automatically links identities. |
| CSRF/OAuth state interception | Authorization Code + PKCE, cryptographic one-use state, exact callbacks and redirect allowlist in the OIDC client/provider. Bearer APIs do not use ambient auth cookies. |
| IDOR/cross-user repository access | Internal principal is injected server-side; every workspace, preview, installation and repository lookup includes owner scope. Unauthorized resources return not found. |
| Provider credential theft | GitHub App least privilege, KMS-backed secret references, ephemeral installation tokens, no credentialed URLs, redaction and bounded logs. |
| Access after revocation | Recheck installation/repository authorization before resolve/clone/rebuild; invalidate caches on disconnect/webhook lifecycle events. |
| SSRF/DNS rebinding | Public import permits policy-approved HTTPS hosts only, rejects credentials/IP/internal targets and revalidates redirect/DNS destinations before clone. |
| Quota races/Redis loss | PostgreSQL row locking and idempotent durable reservations; Redis is never sole truth; reconciliation releases leaks. |
| Resource/AI exhaustion | Per-user/IP/category rate limits, configurable hard limits, reservations before enqueue, time/disk/process/network limits and admin kill switches. |
| Admin endpoint exposure | Internal roles, explicit server-side dependencies, audit events and no reliance on hidden routes. |
| Credential exposure to sandboxes | Workers broker short-lived clone credentials outside repository manifests; workloads receive no control-plane/service credentials. |
| Multiple-account/IP rotation abuse | Verified identity requirements, conservative free limits, risk signals and administrative blocks; IP limits supplement rather than replace user limits. |

Residual risks after Phase 1: no quota enforcement, GitHub private access, audit ledger, provider revocation, production sandbox, or administrative controls yet. Public deployment remains gated on later phases.
