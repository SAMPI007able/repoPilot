# Production previews with Railway Sandboxes

Production preview execution uses Railway Sandboxes, not the local Docker
provider. A Sandbox is an isolated temporary VM and receives a Railway-managed
HTTPS domain for the manifest's public port.

## Security boundary

Create a dedicated Railway project and environment for preview sandboxes. It
must contain no PostgreSQL, Redis, API, worker, storage, or other private
service. Published Sandbox domains require `PRIVATE` networking, so targeting
the application production environment would allow repository code to reach
production services over private DNS.

Use a least-privileged Railway API token that can create and destroy Sandboxes
only in that dedicated environment. Store the token only on the preview worker;
do not expose it to the API, frontend, or generated application.

## Railway services

The application production environment needs three backend services built from
`backend/Dockerfile`:

1. **API** — default image command.
2. **preview-worker** — `rq worker previews --url "$REDIS_URL"`.
3. **preview-reconciler** — `python -m app.workers.preview_reconciler`.

All three use the same production PostgreSQL and Redis. The API and worker use
the same S3 artifact bucket so preview logs written by the worker are readable
by the API. Do not attach a Docker socket to any production service.

## API variables

```dotenv
APP_ENV=production
PREVIEW_PRODUCTION_ENABLED=true
PREVIEW_PROVIDER=railway-sandbox
PREVIEW_TRUSTED_LOCAL_EXECUTION=false
PREVIEW_RECONCILE_SECONDS=15
PREVIEW_JOB_TIMEOUT=40m
ARTIFACT_STORE=s3
```

Keep the existing production `DATABASE_URL`, `REDIS_URL`, S3, OIDC, CORS, and
rate-limit variables. The API does not need `RAILWAY_API_TOKEN`.

## Preview worker variables

```dotenv
APP_ENV=production
PREVIEW_PROVIDER=railway-sandbox
PREVIEW_TRUSTED_LOCAL_EXECUTION=false
PREVIEW_JOB_TIMEOUT=40m

RAILWAY_API_TOKEN=<secret, worker only>
RAILWAY_SANDBOX_ENVIRONMENT_ID=<dedicated empty environment id>
PREVIEW_RAILWAY_ACKNOWLEDGE_DEDICATED_ENVIRONMENT=true

# Five minutes works on Trial/Free. Hobby/Pro may raise this to 30.
PREVIEW_RAILWAY_MAX_IDLE_MINUTES=5
PREVIEW_RAILWAY_MAX_LIFETIME_MINUTES=60

ARTIFACT_STORE=s3
ARTIFACT_S3_BUCKET=<bucket>
ARTIFACT_S3_REGION=<region>
ARTIFACT_S3_ACCESS_KEY_ID=<secret>
ARTIFACT_S3_SECRET_ACCESS_KEY=<secret>
```

The worker also needs the shared production `DATABASE_URL`, `REDIS_URL`, and
any S3 endpoint setting used by the API. The current Railway environment ID and
the sandbox target environment ID must differ; the environment checker rejects
an accidental match.

Validate the worker before enabling the feature:

```shell
python -m app.scripts.check_environment --target preview-worker
```

## Reconciler variables

The reconciler needs `DATABASE_URL`, `REDIS_URL`, and
`PREVIEW_RECONCILE_SECONDS`. It does not need the Railway API token because it
queues cleanup work for the preview worker.

## Enablement order

1. Deploy the API, preview worker, and reconciler with the preview database
   migrations applied.
2. Confirm the worker preflight command passes.
3. Confirm the `previews` RQ worker is connected to Redis.
4. In the administrator feature-flags screen, enable `preview`.
5. Test a small public repository first, then a connected private repository.
6. Verify start, public HTTPS access, manual stop, expiry cleanup, and log
   redaction before inviting beta users.

The API has a separate `PREVIEW_PRODUCTION_ENABLED` kill switch. Turning the
database feature flag on without this variable still returns a disabled-feature
response. To stop new previews immediately, disable the database feature flag;
keep the worker and reconciler running until existing Sandboxes are removed.

## Repository and runtime limits

- Repository URLs must be HTTPS and credential-free.
- Direct URL entry remains limited to public GitHub repositories.
- Connected GitHub, GitLab, and Bitbucket repositories can use their existing
  OAuth clone token. The token is passed only through the short-lived RQ job and
  clone command environment, is never embedded in the URL, and is included in
  log redaction.
- The approved runtime manifest currently supports Node.js 20/22 and exactly
  one public service.
- Install and build commands have 15-minute limits. Preview processes are
  wrapped with a maximum lifetime even if the reconciler is unavailable.
- Keep the per-user concurrency limit at one for the initial beta and raise it
  only after observing cost and cleanup behavior.

Railway documents Sandboxes as isolated VMs suitable for production code
execution and supports temporary public HTTPS domains. Review the current
limits and pricing before increasing concurrency:

- https://docs.railway.com/sandboxes
