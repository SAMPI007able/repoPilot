# Runtime Manifest v1

The runtime manifest is declarative configuration. It is never interpreted as arbitrary Docker or Kubernetes configuration, and Phase 1 never executes it.

## Supported matrix

- Runtime: Node.js 20 and 22
- Package managers: npm, pnpm, Yarn
- Primary framework support: Vite with Vue or React
- Limited support: single-process Node web applications with explicit package scripts
- One public HTTP web service
- Existing Dockerfiles are not enabled in Phase 1

## Example

```yaml
version: "1"
runtime:
  family: node
  version: "22"
repository:
  branch: main
install:
  command: npm ci
build:
  command: npm run build
services:
  - name: web
    command: npm run dev -- --host 0.0.0.0
    port: 5173
    public: true
    healthcheck:
      path: /
      timeoutSeconds: 180
      intervalSeconds: 3
environment:
  required:
    - VITE_API_URL
  optional: []
resources:
  cpuRequest: 250m
  cpuLimit: "1"
  memoryRequest: 256Mi
  memoryLimit: 1Gi
lifecycle:
  idleTimeoutMinutes: 20
  maximumLifetimeMinutes: 60
```

## Analysis order

1. Read deterministic indexed signals: package scripts/dependencies/engines, lock/config filenames, parsed environment references, and documentation filenames.
2. If required fields remain unresolved and fallback is enabled, request only schema-bounded hints from the existing AI provider.
3. Validate the AI response against a restrictive hints schema.
4. Construct and validate the complete manifest with Pydantic.
5. Apply command/resource/platform policy.
6. Present evidence, confidence, warnings, and unsupported reasons.
7. Require user review and explicit approval.

No command executes in these steps. Secret values are not manifest fields and are not sent to AI.

## Command policy

Commands are limited to known package-manager forms:

- Install: `npm ci`, `npm install`, `pnpm install --frozen-lockfile`, `yarn install --frozen-lockfile`, or `yarn install --immutable`
- Build/start: package script invocations through npm, pnpm, or Yarn

Shell operators, interpolation, pipes, redirection, command substitution, arbitrary binaries, images, mounts, capabilities, and infrastructure configuration are rejected. Future workers must convert validated commands to argument arrays inside the sandbox.

## Safe editable fields

- Node version
- Branch
- Allowlisted install/build/start commands
- Public port and health path
- Environment-variable names (never values)
- Allowlisted CPU/memory profiles
- Bounded idle and maximum lifetime

Updates use an expected revision. Stale writes return `RUNTIME_MANIFEST_REVISION_CONFLICT`. Editing invalidates previous approval.

## APIs

```text
POST /workspaces/{workspaceId}/runtime-manifest/analyze
GET  /workspaces/{workspaceId}/runtime-manifest
PUT  /workspaces/{workspaceId}/runtime-manifest
POST /workspaces/{workspaceId}/runtime-manifest/approve
```

Errors from these endpoints use:

```json
{
  "code": "RUNTIME_MANIFEST_POLICY_REJECTED",
  "message": "The runtime manifest violates preview policy.",
  "retryable": false,
  "details": { "violations": [] },
  "correlationId": "..."
}
```

## Existing workspaces

Existing version-1 repository artifacts remain readable because new repository-signal and package-engine fields are additive and default to empty values. Re-indexing improves package-manager/config evidence. An existing workspace can still receive a conservative proposal and edit it during review.
