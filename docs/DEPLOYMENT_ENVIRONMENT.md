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

## Railway or Fly backend variables

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

GEMINI_API_KEY=...
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
