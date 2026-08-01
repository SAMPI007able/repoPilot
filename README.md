# TestForge AI

TestForge AI is a developer-focused assistant for generating tests, exploring repositories, and running AI-powered analysis against indexed codebases. It provides a FastAPI backend and a Vite + Vue frontend.

Key features

- Index GitHub repositories into durable, restorable workspaces
- Run multiple builds and parser batches concurrently
- Generate unit and integration tests
- Ask free-form questions against an indexed repository
- Explore repository dependencies and impact analysis
- Analyze, approve, and run temporary trusted-development web previews in Realtime Preview Lab

Repository layout

- `backend/`: FastAPI backend, indexing services, and persistence
- `backend/workspace/checkouts/`: temporary clones removed after indexing
- `backend/workspace/artifacts/`: compressed repository-index artifacts in local development
- `frontend/`: Vite + Vue frontend

Getting started

Prerequisites:

- Python 3.10+
- Node.js 16+
- Git

Backend

Create a virtual environment, install dependencies, and run the API from the repository root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
$env:PYTHONPATH="backend"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Key endpoints:

- `GET /health` — health check
- `POST /workspaces/index` — start an asynchronous repository build
- `GET /workspaces/index/{job_id}` — inspect build and parallel stage progress
- `GET /workspaces` — list persisted workspaces for the sidebar
- `GET /workspaces/{workspace_id}` — restore a persisted repository index
- `DELETE /workspaces/{workspace_id}` — remove workspace metadata and artifacts
- `POST /ai/query` — chat or test generation
- `POST /workspaces/impact-analysis` — analyze a target's impact

Authentication

Production uses OIDC Authorization Code with PKCE. Configure `OIDC_ISSUER` and
`OIDC_AUDIENCE` on the backend and matching `VITE_OIDC_*` frontend settings.
The backend independently verifies token signature, issuer, audience and
lifetime, then maps `(issuer, subject)` to an internal TestForge user. Docker
Compose uses an explicitly enabled local-only development identity.

Migration 004 leaves pre-authentication workspaces unowned and invisible. After
the intended owner signs in once, assign legacy rows explicitly:

```powershell
docker compose exec api python -m app.scripts.assign_legacy_workspaces --email developer@testforge.local
```

Persistence

A checkout exists only while a build is running. After the compressed repository-index artifact is uploaded and checksum-verified, the temporary checkout is removed.

Realtime Preview Lab

Phase 2 adds out-of-process RQ execution, durable lifecycle events, a constrained local Docker adapter, real health checks, preview URLs, redacted logs, manual stop, extension, and automatic expiry. FastAPI remains a control plane and never executes repository commands.

See the [Phase 0 architecture assessment](docs/realtime-preview/phase-0-assessment.md), [Phase 2 local execution guide](docs/realtime-preview/phase-2-trusted-local-execution.md), [threat model](docs/realtime-preview/threat-model.md), [runtime-manifest v1 specification](docs/realtime-preview/runtime-manifest-v1.md), and [architecture decisions](docs/realtime-preview/adr/).

> **Security warning:** ordinary Docker isolation is not sufficient for arbitrary hostile public repositories in production. Production execution is intentionally deferred until the Kubernetes/gVisor, network-policy, identity, routing, quota, and reconciliation controls described in Phase 3 exist.

Local development uses SQLite and local compressed artifacts by default. For cloud deployment, set `DATABASE_URL` to PostgreSQL and configure S3-compatible object storage using [backend/.env.example](backend/.env.example). `WORKSPACE_BUILD_JOBS` controls concurrent repository builds, while `WORKSPACE_PARSE_WORKERS` controls parser batches within each build.

Legacy checkout migration

Existing clones under `backend/workspace/repositories` can be persisted without deleting them:

```powershell
$env:PYTHONPATH="backend"
python -m app.scripts.migrate_workspaces
```

After validating the restored workspaces in the UI, explicitly request cleanup:

```powershell
python -m app.scripts.migrate_workspaces --delete-after-persist
```

Each clone is deleted only after its artifact has been uploaded, downloaded, checksum-verified, and committed to the database.

Frontend

```powershell
cd frontend
npm install
npm run dev
```

The frontend expects the backend at `http://localhost:8000`. The sidebar refreshes persisted workspace status every two seconds and restores ready workspaces on selection.

Trusted local preview stack

With Docker Desktop running, start PostgreSQL, Redis, the API, RQ worker, expiry reconciler, and frontend together:

```powershell
docker compose up --build
```

Then open `http://127.0.0.1:5173`. This mode is for trusted development repositories only; keep `PREVIEW_TRUSTED_LOCAL_EXECUTION=false` outside this local stack until the production sandbox phase is complete.

Testing

From the repository root:

```powershell
$env:PYTHONPATH="backend"
python -m unittest discover -s backend/tests -v
cd frontend
npm run build
```
