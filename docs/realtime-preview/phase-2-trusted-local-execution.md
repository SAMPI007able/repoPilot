# Phase 2: trusted local preview execution

Phase 2 adds a real, temporary preview for trusted development repositories. It does not claim that ordinary Docker is a safe boundary for arbitrary hostile code. Production enablement remains gated on Phase 3's Kubernetes/gVisor controls.

## Runtime path

1. The FastAPI control plane validates an approved manifest and writes a `queued` preview plus its first durable event.
2. FastAPI submits an idempotent RQ job. It never clones, installs, builds, or starts repository code.
3. A separate worker clones the workspace's persisted immutable commit into a random Docker volume.
4. Install and build run in short-lived, constrained Node containers.
5. The web process runs as the non-root `node` user with a read-only root filesystem, dropped capabilities, PID/CPU/memory limits, a dedicated runtime bridge, and only its declared port published on `127.0.0.1`.
6. A real HTTP health check moves the durable lifecycle to `ready` and exposes the random local URL.
7. Manual stop or the reconciler removes the container, networks, and volume idempotently.

Lifecycle transitions are stored in `preview_events`; bounded console output is stored in the artifact store. Environment values are not persisted in PostgreSQL or artifacts. They live only in the short-lived RQ payload and container environment, and RQ result/failure retention is disabled. Logs redact both common credential forms and exact injected values.

## Start locally

Docker Desktop must be running and Linux containers must be enabled.

```powershell
docker compose up --build
```

Open `http://127.0.0.1:5173`, select a ready workspace, analyze and approve its runtime manifest, provide any required environment values, and choose **Start preview**. The UI receives real Server-Sent Events and displays the preview URL only after the health check succeeds.

The stack contains:

- `api`: control plane only; it has no Docker socket.
- `preview-worker`: RQ execution plane; it alone has the Docker socket.
- `preview-reconciler`: retries expiry cleanup from durable state.
- PostgreSQL, Redis, the frontend, and a shared log-artifact volume.

Set `PREVIEW_TRUSTED_LOCAL_EXECUTION=true` only on the local execution worker. Keep it false in any production API deployment until Phase 3 is complete.

## API

- `POST /workspaces/{workspaceId}/previews` with `Idempotency-Key`
- `GET /workspaces/{workspaceId}/previews/latest`
- `GET /previews/{previewId}`
- `GET /previews/{previewId}/events` (SSE)
- `GET /previews/{previewId}/logs`
- `POST /previews/{previewId}/extend` with `Idempotency-Key`
- `POST /previews/{previewId}/stop` with `Idempotency-Key`

## Current limits and Phase 3 gate

- Only the approved Node 20/22 single-public-service manifest subset is executable.
- Repository authentication is not yet brokered; Phase 2 is intended for public trusted repositories.
- Build containers have outbound access for Git and package installation. The running app has a dedicated bridge but still has outbound access in this trusted-local phase; default-deny runtime egress requires Phase 3 network policy.
- Local ports are bound to loopback and are not suitable for remote multi-user routing.
- Docker tags are configurable for development. Production manifests must use allowlisted digest-pinned images.
- No hostile public repository should be executed until namespace isolation, gVisor, default-deny network policy, workload identity separation, quotas, admission policy, and orphan reconciliation have passed the Phase 3 integration suite.

## Verification

Automated coverage checks idempotent creation, legal state transitions, expiry caps, environment validation, secret redaction, and existing application regressions. The fixture in `backend/tests/fixtures/vite-basic` is the real adapter smoke test when Docker is available.
