# Realtime Preview Lab Threat Model

## Trust boundaries

1. **User to control plane:** repository URLs, instructions, manifests, environment names, lifecycle requests.
2. **Control plane to queue/worker:** validated declarative jobs only.
3. **Worker to sandbox provider:** immutable commit and policy-approved manifest.
4. **Sandbox to network:** repository code is hostile and may attempt exfiltration, scanning, persistence, or denial of service.
5. **Browser runner to preview:** preview content is hostile to the browser context.
6. **Artifact retrieval:** logs/screenshots/traces may contain sensitive application output.

## Principal threats and controls

| Threat | Required control |
|---|---|
| SSRF or cloning local/private targets | Allowlisted HTTPS Git hosts initially; reject credentials, IP literals, localhost, and private/link-local/reserved resolution results before worker submission. Revalidate after redirects/DNS resolution. |
| Command injection | Manifest is typed data. Phase 1 allows only known package-manager command shapes and rejects shell metacharacters. Workers use argument arrays. No AI output executes directly. |
| Container escape | Production requires non-privileged, non-root gVisor workloads; no host namespaces, Docker socket, hostPath, added capabilities, or privilege escalation; runtime-default seccomp. Fail closed without the configured RuntimeClass. |
| Credential theft | Do not mount service-account tokens or platform credentials. Resolve user secrets outside AI prompts and inject only into the target workload. Block metadata endpoints. |
| Cross-tenant data leakage | Namespace/label all resources, isolate cache keys by immutable dependency fingerprint and tenant, use per-preview artifact prefixes and signed authorization. |
| Network abuse/exfiltration | Deny-by-default NetworkPolicy, limited DNS and approved install egress, stricter runtime egress, block cluster/control-plane/private ranges. |
| Resource exhaustion | Repository, clone, build, startup, process, CPU, memory, disk, network, log, artifact, preview-lifetime, session-lifetime, and tenant-concurrency limits. |
| Persistent malicious workload | Immutable checkout, ephemeral filesystems/volumes, maximum lifetime, manual stop, TTLs, and idempotent reconciliation. |
| Preview-domain attacks | Separate registrable preview domain, TLS, signed expiring access, security headers, no control-plane cookies, route revocation on stop. |
| Browser-session compromise | Separate runner service, fresh context, bounded lifetime/resources, no persisted cookies by default, artifact authorization, automatic cleanup. |
| Secret leakage in logs/telemetry | Structured allowlisted fields, redaction, bounded logs, never log environment values, tokens, credentials, or signed preview URLs. |
| CSRF/replay/lifecycle races | Authenticated CSRF-protected mutations, idempotency keys, optimistic versions, centralized lifecycle transitions, audit metadata. |
| Supply-chain attacks | Pinned internal images by digest, immutable commit SHA, lockfile-aware install commands, policy-gated Dockerfiles, isolated caches, dependency-install egress controls. |

## Phase 1 security properties

- Performs no repository command execution.
- Reads only persisted indexed metadata.
- Rejects manifest shell operators, unsupported runtimes/package managers, unsafe ports, excessive limits, and invalid lifecycle settings.
- Stores required environment-variable names only; no values or secrets.
- Requires explicit approval after validation before a future execution API may accept the manifest.

## Residual risk

Deterministic analysis is not proof that a repository is safe. A valid manifest only means the configuration conforms to platform policy. Execution remains prohibited until Phase 2 locally and Phase 3 for hostile production repositories provide the required isolation and cleanup controls.
