# Deployment environment contract

TestForge uses one canonical variable contract: [`.env.example`](../.env.example).
The file contains names and safe defaults only. Never commit a populated `.env`.

## Source-of-truth policy

| Context | Source of values | Notes |
|---|---|---|
| Local direct development | repository-root `.env` | Vite reads the parent directory; start Uvicorn with `--env-file .env`. |
| Local Docker Compose | repository-root `.env` | Compose also reads `backend/.env` as a temporary compatibility fallback; root values win. |
| Vercel frontend | Vercel project environment variables | Add only `VITE_*` values. They are public and embedded in the browser bundle. |
| Railway/Fly backend | service secrets/environment variables | Add backend values only. Do not add `VITE_*` variables. |
| Neon | supplies `DATABASE_URL` | Use the pooled PostgreSQL connection string and require TLS. |
| Upstash Redis | supplies `REDIS_URL` | Use the TLS `rediss://` URL where available. |
| AWS S3 | supplies `ARTIFACT_S3_*` | Use a private bucket and a least-privilege IAM principal. |

The old `frontend/.env.example`, `frontend/.env.docker`, and
`backend/.env.example` files were removed because they had become separate,
drifting contracts. Existing ignored `frontend/.env` and `backend/.env` files
are not deleted automatically because they may contain credentials. Move their
values into the root `.env`, verify the application, then delete those local
legacy files.

## Local setup

```powershell
Copy-Item .env.example .env
```

Fill in secrets in `.env`. For direct development from the repository root:

```powershell
$env:PYTHONPATH="backend"
uvicorn app.main:app --env-file .env --reload --host 127.0.0.1 --port 8000
Set-Location frontend
npm run dev
```

For Docker Compose, run `docker compose up --build`. During migration, Compose
loads `backend/.env` first and the root `.env` second, so the canonical root
value wins if a name exists in both places.

## Vercel frontend variables

Set these for Production and Preview as appropriate:

```dotenv
VITE_API_BASE_URL=https://api.example.com
VITE_AUTH_MODE=oidc
VITE_OIDC_AUTHORITY=https://YOUR_TENANT.auth0.com/
VITE_OIDC_CLIENT_ID=YOUR_AUTH0_SPA_CLIENT_ID
VITE_OIDC_AUDIENCE=https://api.example.com
VITE_OIDC_REDIRECT_URI=https://app.example.com/auth/callback
VITE_OIDC_SCOPE=openid profile email
VITE_OIDC_CONNECTION_PARAMETER=connection
VITE_OIDC_GITHUB_CONNECTION=github
VITE_OIDC_GOOGLE_CONNECTION=google-oauth2
VITE_OIDC_EMAIL_CONNECTION=Username-Password-Authentication
VITE_POSTHOG_API_KEY=YOUR_PUBLIC_POSTHOG_PROJECT_KEY
VITE_POSTHOG_HOST=https://us.i.posthog.com
```

Do not put database, Redis, AWS, Gemini, encryption, OAuth client-secret, or
other backend credentials in a `VITE_*` variable.

## Railway backend variables

The repository root contains a production backend `Dockerfile`, so an existing
Railway service connected to the monorepo root will use Docker instead of asking
Railpack to guess between Python and Node. Leave **Root Directory** empty (`/`)
and redeploy. Alternatively, set **Root Directory** to `/backend`; Railway will
then detect `backend/Dockerfile`. Clear custom build/start overrides in Railway;
the root image includes `start.sh`, starts Uvicorn, and binds to Railway's
injected `PORT`.

Start from the backend sections of `.env.example`. At minimum for the proposed
production stack, configure:

```dotenv
APP_ENV=production
FRONTEND_URL=https://app.example.com
OAUTH_CALLBACK_BASE_URL=https://api.example.com
CORS_ORIGINS=https://app.example.com

AI_PROVIDER=gemini
AI_PROVIDER_TIMEOUT_SECONDS=120
AI_CHAT_MAX_INPUT_TOKENS=30000
AI_GENERATION_MAX_INPUT_TOKENS=60000
AI_CHAT_MAX_FILES=300
AI_CHAT_MAX_RELATIONSHIPS=500
AI_CHAT_MAX_QUERY_CHARACTERS=4000
AI_CHAT_MAX_DOCUMENTATION_CHARACTERS=6000
AI_CHAT_MAX_PACKAGE_CHARACTERS=4000
AI_CHAT_MAX_HISTORY_MESSAGES=6
AI_CHAT_MAX_HISTORY_CHARACTERS=8000
AI_CHAT_MAX_MESSAGE_CHARACTERS=3000

GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_FALLBACK_MODELS=
GEMINI_CHAT_THINKING_LEVEL=minimal
GEMINI_GENERATION_THINKING_LEVEL=low
DATABASE_URL=postgresql://...neon.../testforge?sslmode=require
REDIS_URL=rediss://...upstash...

ARTIFACT_STORE=s3
ARTIFACT_S3_BUCKET=...
ARTIFACT_S3_REGION=...
ARTIFACT_S3_ACCESS_KEY_ID=...
ARTIFACT_S3_SECRET_ACCESS_KEY=...

AUTH_MODE=oidc
OIDC_ISSUER=https://YOUR_TENANT.auth0.com/
OIDC_AUDIENCE=https://api.example.com
OIDC_JWKS_URL=https://YOUR_TENANT.auth0.com/.well-known/jwks.json

OAUTH_TOKEN_ENCRYPTION_KEY=...
POSTHOG_API_KEY=...
POSTHOG_HOST=https://us.i.posthog.com
PREVIEW_TRUSTED_LOCAL_EXECUTION=false
```

The Gemini values above are the recommended free-tier configuration. Chat
context is relevance-ranked and bounded, then checked with Gemini's tokenizer
before generation. A Gemini `429 RESOURCE_EXHAUSTED` is not retried or sent to
fallback models: the API returns a typed retryable error and honors the
provider's `RetryInfo` delay. After moving to a paid plan, increase the input
ceilings only after checking that plan's tokens-per-minute quota.

### Selecting OpenAI or Qwen

Use one provider for both capabilities by setting `AI_PROVIDER`, or split them
with `AI_CHAT_PROVIDER` and `AI_GENERATION_PROVIDER`. Blank capability overrides
must be removed rather than left empty.

OpenAI configuration:

```dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-luna
OPENAI_CHAT_REASONING_EFFORT=low
OPENAI_GENERATION_REASONING_EFFORT=low
```

Qwen 3.7 Flash purchased through OpenRouter must use OpenRouter's key, endpoint,
and author/model slug. Do not send an `sk-or-...` key to a DashScope URL:

```dotenv
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=qwen/qwen3.7-flash
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_SITE_URL=https://app.example.com
OPENROUTER_APP_NAME=TestForge
```

Direct Alibaba Model Studio Qwen configuration:

```dotenv
AI_PROVIDER=qwen
QWEN_API_KEY=...
QWEN_MODEL=qwen3.7-flash
QWEN_BASE_URL=https://YOUR_WORKSPACE_ID.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1
QWEN_CHAT_ENABLE_THINKING=false
QWEN_GENERATION_ENABLE_THINKING=false
```

`QWEN_BASE_URL` and the API key must belong to the same Alibaba Model Studio
region. The example is Singapore; use the workspace endpoint shown in Model
Studio for Virginia, Frankfurt, Tokyo, Beijing, or Hong Kong. The shared
Singapore compatibility URL remains the local default for existing keys, but a
workspace-specific URL is recommended for production.

Support tickets email every active user whose role is `ADMIN` on
submission and email the requester when an admin marks a ticket In Progress or
Completed. Configure SMTP for this; without `SMTP_HOST` and `SMTP_FROM`, tickets
are still stored but emails are skipped with a log warning:

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM=TestForge Support <support@example.com>
API_PUBLIC_URL=https://api.example.com
```

Apply `backend/migrations/007_support_tickets.sql` before deploying this
release.

For AI result history, also apply `backend/migrations/008_ai_history.sql` before
deploying. Generated tests are stored per user and workspace; existing chat
messages continue to use the `chat_sessions` and `chat_messages` tables.

AI responses use an exact-prompt, user/workspace-scoped ephemeral cache. The
prompt hash includes indexed repository context, provider, and model, so a
changed index or model does not reuse stale output.

```dotenv
AI_RESPONSE_CACHE_ENABLED=true
AI_RESPONSE_CACHE_TTL_SECONDS=21600
AI_RESPONSE_CACHE_MEMORY_ENTRIES=200
```

Redis is the shared cache across Railway instances. If Redis is briefly
unavailable, requests fail open to a bounded per-process cache rather than
blocking AI generation.

Keep the rate-limit and concurrency variables from `.env.example`; the defaults
are deliberately conservative. `PORT` is supplied by Railway and honored by
the backend image. Fly may expose a fixed internal port instead.

Run the secret-safe preflight check in the deployed backend environment:

```shell
python -m app.scripts.check_environment --target backend
```

The command prints missing variable names and configuration warnings, but never
prints their values.

## Auth0 alignment

The following pairs must match exactly:

- `VITE_OIDC_AUTHORITY` ↔ `OIDC_ISSUER`
- `VITE_OIDC_AUDIENCE` ↔ `OIDC_AUDIENCE`
- the Vercel callback URL ↔ Auth0 Allowed Callback URLs
- the Vercel origin ↔ Auth0 Allowed Web Origins and `CORS_ORIGINS`
- the Vercel logout origin ↔ Auth0 Allowed Logout URLs

Auth0 social-login credentials are separate from the GitHub/GitLab/Bitbucket
OAuth applications used to access repositories.

## Secret rotation

- Rotating `OAUTH_TOKEN_ENCRYPTION_KEY` invalidates stored source-control tokens
  unless they are re-encrypted first.
- Rotate AWS, Gemini, Neon, and Upstash credentials in their provider and then
  update the backend host without changing frontend variables.
- PostHog project keys are intended for ingestion; never expose a personal API
  key in either frontend or backend configuration.
