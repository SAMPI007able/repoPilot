# Launch readiness — Phase 0 assessment

## Existing architecture

TestForge is a compact Vue/FastAPI monorepo. `backend/app/main.py` is the composition root and HTTP surface. Pydantic models define API contracts; service classes contain orchestration; SQLAlchemy supports SQLite locally and PostgreSQL in Docker/production. `Base.metadata.create_all` supports development while numbered SQL files are the production migration record. Large repository indexes and preview logs use local or S3-compatible artifact storage.

Workspace indexing uses a bounded in-process executor. It validates public GitHub HTTPS URLs, clones into a temporary checkout, resolves the checked-out SHA, indexes in parallel, persists and verifies a compressed artifact, and deletes the checkout. Realtime preview uses PostgreSQL for lifecycle truth and Redis/RQ for jobs. Only the preview worker has the Docker socket. Preview clone/build/start resources are labelled and cleaned idempotently.

The Vue application uses Pinia and Axios but currently has a single effective route. Native `EventSource` cannot attach bearer tokens and must be replaced by an authenticated stream client when preview routes are protected.

## Files inspected

- Root/backend/frontend READMEs, Compose, environment examples, package manifests and TypeScript configuration.
- All documents and ADRs under `docs/realtime-preview`.
- FastAPI routes, request validation and error envelopes in `backend/app/main.py`.
- SQLAlchemy rows, database/session handling and migrations 001–003.
- Workspace persistence/building, repository validation/cloning, preview persistence/queue/workers/sandbox, artifact storage and secret redaction.
- Vue router, application shell, Axios client, API types, and workspace/preview Pinia stores.
- Backend tests and frontend build configuration.

## Baseline

- Backend: 34 tests passed, one Docker integration test skipped.
- Frontend: Dockerized `vue-tsc` and Vite production build passed.
- Host `npm run build` failed before changes because the host npm installation points at a missing roaming `npm-cli.js`.
- No formatter, backend type checker, frontend test, or lint script is configured.

## Patterns to preserve

1. FastAPI remains the control plane; repository execution stays out of request handlers.
2. Pydantic API/domain models and SQLAlchemy persistence services remain explicit boundaries.
3. PostgreSQL is durable truth; Redis is coordination/cache only.
4. Immutable commit SHAs are recorded before execution.
5. High-volume payloads remain in object storage, not relational JSON rows.
6. Existing public repository import remains available, but becomes authenticated and owned.
7. Stable error envelopes include a correlation ID.

## Current gaps and blockers

- No identity, tenant ownership, authorization, role, quota, audit, provider connection, or encrypted-secret model exists.
- Existing workspaces are unowned. Migration adds nullable ownership; operators must explicitly assign or remove legacy rows. They are never automatically exposed to the first user.
- Hand-authored migrations have no runner or version table and are not currently reversible. Phase 1 supplies paired up/down SQL; adopting Alembic remains launch work.
- The local `.env` contains an apparent provider credential. It is ignored by Git, but should be rotated if genuine and moved to an operator secret store.
- Production OIDC issuer/client configuration and a GitHub App do not yet exist.
- Docker is explicitly a trusted-local preview boundary, not production hostile-code isolation.

## Phase 1 file plan

- Add internal user/auth-identity rows and nullable workspace owner FK plus reversible migration 004.
- Add identity Pydantic models, OIDC/JWKS and explicit local-development verifiers, identity persistence, and FastAPI principal dependencies.
- Add `/me`; protect workspace, manifest, preview, AI and impact routes; enforce workspace/preview ownership server-side.
- Add a Pinia auth store, OIDC redirect/callback/sign-in pages, bearer-token injection, route guards, and authenticated SSE consumption.
- Update Compose and environment documentation for local-only development auth and production OIDC.

## Later phases

Phase 2 implements the quota schema/service/reservations and preview integration. Phase 3 implements GitHub App installations, repository selection, immutable ref resolution and short-lived private clone credentials. Phase 4 expands quota/rate-limit coverage. Phase 5 adds administrative controls, audit/deletion workflows and launch hardening. Phase 6 exposes provider-neutral GitLab/Bitbucket extension interfaces without incomplete UI.
