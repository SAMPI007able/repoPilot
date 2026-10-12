# Rate limiting and beta quotas

TestForge uses Redis-backed, per-user fixed-window request quotas and exact-ID concurrency sets. The authenticated internal user ID is hashed before it is included in a Redis key. Tokens, repository credentials, document contents, and raw user IDs are never logged or stored in quota keys.

## Protected operations

| Action | Routes | Default |
| --- | --- | --- |
| `repository_index` | `POST /workspaces/index`, `POST /integrations/{provider}/repos/import` | 5/day |
| `document_upload` | `/workspaces/index` when project documents are attached | 10/day |
| `project_chat` | `POST /ai/query` with `type=chat` | 60/day |
| `ai_generation` | `POST /ai/query` with `type=test_generation`, legacy `POST /ai/generate-tests` | 30/day |
| `preview_creation` | `POST /workspaces/{workspaceId}/previews` | 5/day |
| `preview_extension` | `POST /previews/{previewId}/extend` | 20/day |

One active preview is allowed per user by default. Idempotent preview-create retries do not consume another request or concurrency slot. Slots are released on manual stop, expiry, startup failure, validation failure, and worker failure. Every create request first reconciles Redis with active preview records, which removes stale entries after Redis loss or process failure.

Browser-session and screenshot policies are configured but are not attached because this repository does not yet expose browser-session or screenshot-generation routes.

## Redis failure policy

Preview creation and extension fail closed with `RATE_LIMIT_UNAVAILABLE` because they can allocate or prolong infrastructure. Repository indexing and AI/document operations fail open during a Redis outage so an early-beta Redis incident does not make the full product unavailable. All failures are logged with action/resource identifiers and exception types, never sensitive payloads.

## Responses

Rejected requests use the standard error envelope and HTTP 429. Request quotas include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, and `Retry-After`. Concurrent-resource responses include the resource, limit, and active count. The frontend displays the server message and reset time and does not retry automatically.

## Configuration

All variables and defaults are listed in the repository-root `.env.example`. Windows may be customized per action with `<LIMIT_VARIABLE>_WINDOW_SECONDS`; otherwise `RATE_LIMIT_WINDOW_SECONDS` is used. `RATE_LIMIT_ENABLED=false` is rejected unless `APP_ENV` is `development`, `local`, or `test`.

## Administrator reset

An active `ADMIN` may call:

```http
DELETE /admin/rate-limits/{userId}
```

This removes the user's request counters and preview/browser concurrency entries. The endpoint never returns Redis keys.

## Metrics

The centralized service maintains process-local counters for allowed/rejected decisions, concurrency rejections, Redis failures, and release failures, and emits structured logs. These counters are intentionally lightweight for beta; a future metrics exporter can consume `RateLimitService.metrics_snapshot()` without changing route code.
