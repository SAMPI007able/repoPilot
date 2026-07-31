# TestForge AI

TestForge AI is a developer-focused assistant for generating tests, exploring repositories, and running AI-powered analysis against indexed codebases. It provides a FastAPI backend and a Vite + Vue frontend.

Key features

- Index GitHub repositories into durable, restorable workspaces
- Run multiple builds and parser batches concurrently
- Generate unit and integration tests
- Ask free-form questions against an indexed repository
- Explore repository dependencies and impact analysis

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

Persistence

A checkout exists only while a build is running. After the compressed repository-index artifact is uploaded and checksum-verified, the temporary checkout is removed.

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

Testing

From the repository root:

```powershell
$env:PYTHONPATH="backend"
python -m unittest discover -s backend/tests -v
cd frontend
npm run build
```
