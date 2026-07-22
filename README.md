# TestForge AI

TestForge AI is a developer-focused assistant for generating tests, exploring repositories, and running AI-powered analysis against indexed codebases. It provides a FastAPI backend that integrates AI capabilities and a Vite + Vue frontend for interacting with repositories and results.

Key features
- Index GitHub repositories into a local workspace for analysis
- Generate tests (unit/integration) for target files or classes
- Free-form chat-style queries against an indexed repository
- Impact analysis for code targets

Repository layout
- backend/: Python FastAPI backend and services
- frontend/: Vite + Vue frontend app
- workspace/repositories/: local clones of indexed repos

Getting started
Prerequisites
- Python 3.10+ (recommended)
- Node.js 16+ and npm or pnpm
- Git

Backend (Python)
1. Create and activate a virtual environment:

```
python -m venv .venv
source .venv/bin/activate    # macOS / Linux
.venv\\Scripts\\Activate.ps1  # Windows PowerShell
```

2. Install Python dependencies:

```
pip install -r backend/requirements.txt
```

3. Run the backend (development):

```
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend serves a small API. Key endpoints exposed by the backend (see [backend/app/main.py](backend/app/main.py#L1-L400)):
- `GET /health` — simple health check
- `POST /workspaces/index` — index a GitHub repo (multipart form or JSON payload)
- `POST /ai/query` — unified AI query for `type=chat` or `type=test_generation`
- `POST /workspaces/impact-analysis` — run impact analysis for a target

Notes
- The backend stores indexed repositories under `workspace/repositories/`.
- AI provider credentials and configuration (if required) should be set as environment variables according to the chosen provider implementation in `backend/app/services/ai/`.

Frontend
1. Install dependencies and run the dev server:

```
cd frontend
npm install
npm run dev
```

2. The frontend expects the backend to be running at `http://localhost:8000` (CORS allows `http://localhost:5173`). Adjust the API base URL in `frontend/src/services/api.ts` if needed.

Testing
- Backend tests: from the repo root run:

```
pip install -r backend/requirements.txt
pytest -q
```

- Frontend tests (if present) can be run via your chosen test runner configured in `frontend/package.json`.

Development notes
- To index a repository, POST to `/workspaces/index` with a `githubUrl` form field or JSON payload. Uploaded project documents may be included via `project_docs` multipart files.
- Use the `/ai/query` endpoint with `type=chat` to ask questions against an indexed workspace, or `type=test_generation` to generate tests for a target.
- Inspect `backend/app/main.py` for the full route definitions and request/response models.

Contributing
- Feel free to open issues or PRs for bugs, feature requests, or improvements.
- Run linters and tests before submitting changes.

License
- This repository does not include a license file. Add a `LICENSE` if you want to clarify reuse terms.

Contact
- For questions or help, open an issue in this repository.

