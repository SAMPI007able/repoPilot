# ADR 0002: Separate local Docker and production Kubernetes sandbox providers

- Status: Accepted
- Date: 2026-07-31

## Decision

Define one `SandboxProvider` contract. Implement Local Docker only for trusted development repositories and Kubernetes with gVisor for production hostile workloads. Production fails closed if required isolation controls are absent unless an administrator explicitly enables a documented fallback.

FastAPI never invokes repository processes and never receives the Docker socket. Provider calls happen in isolated RQ workers.

## Consequences

- Local Docker must display an explicit security warning and still apply non-root execution, dedicated networks, CPU/memory/PID/time limits, and cleanup.
- Kubernetes resources are labelled by workspace/preview, use restricted service accounts, deny privilege escalation, drop capabilities, apply seccomp, resource limits, network policies, deadlines, and TTLs.
- Provider request models must remain infrastructure-neutral and prohibit arbitrary Kubernetes or Docker options.
