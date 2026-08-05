from collections import Counter
from datetime import datetime, timezone
import hashlib
import logging
import threading
import time
from typing import Callable, Iterable

from redis import Redis
from redis.exceptions import RedisError

from app.config.rate_limit_settings import RateLimitSettings
from app.models.rate_limit_models import AdminResetResult, ConcurrencyResult, RateLimitResult


logger = logging.getLogger(__name__)


RATE_LIMIT_SCRIPT = """
-- testforge:rate-limit
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local limit = tonumber(ARGV[1])
local reset_at = tonumber(ARGV[2])
if current >= limit then
  return {0, current}
end
current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIREAT', KEYS[1], reset_at)
end
return {1, current}
"""

ACQUIRE_SCRIPT = """
-- testforge:concurrency-acquire
if redis.call('SISMEMBER', KEYS[1], ARGV[2]) == 1 then
  return {1, redis.call('SCARD', KEYS[1]), 1}
end
local active = redis.call('SCARD', KEYS[1])
if active >= tonumber(ARGV[1]) then
  return {0, active, 0}
end
redis.call('SADD', KEYS[1], ARGV[2])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return {1, active + 1, 0}
"""

RELEASE_SCRIPT = """
-- testforge:concurrency-release
local removed = redis.call('SREM', KEYS[1], ARGV[1])
if redis.call('SCARD', KEYS[1]) == 0 then redis.call('DEL', KEYS[1]) end
return removed
"""

REPLACE_SCRIPT = """
-- testforge:concurrency-replace
redis.call('SREM', KEYS[1], ARGV[1])
redis.call('SADD', KEYS[1], ARGV[2])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return redis.call('SCARD', KEYS[1])
"""

RECONCILE_SCRIPT = """
-- testforge:concurrency-reconcile
redis.call('DEL', KEYS[1])
for index = 2, #ARGV do redis.call('SADD', KEYS[1], ARGV[index]) end
if #ARGV > 1 then redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1])) end
return math.max(0, #ARGV - 1)
"""


class RateLimitBackendUnavailable(RuntimeError):
    pass


class RateLimitService:
    def __init__(
        self,
        settings: RateLimitSettings,
        redis_client=None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self.redis = redis_client or Redis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2,
        )
        self.clock = clock
        self._rate_script = self.redis.register_script(RATE_LIMIT_SCRIPT)
        self._acquire_script = self.redis.register_script(ACQUIRE_SCRIPT)
        self._release_script = self.redis.register_script(RELEASE_SCRIPT)
        self._replace_script = self.redis.register_script(REPLACE_SCRIPT)
        self._reconcile_script = self.redis.register_script(RECONCILE_SCRIPT)
        self._metrics: Counter[str] = Counter()
        self._metrics_lock = threading.Lock()

    def check_and_consume(self, user_id: str, action: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = int(self.clock())
        bucket = now // window_seconds
        reset_epoch = (bucket + 1) * window_seconds
        key = f"rate-limit:{self._subject(user_id)}:{action}:{bucket}"
        try:
            allowed_raw, current_raw = self._rate_script(keys=[key], args=[limit, reset_epoch])
        except RedisError as exc:
            self._record(f"redis_error:{action}")
            logger.error("Rate-limit Redis operation failed", extra={"action": action, "errorType": type(exc).__name__})
            raise RateLimitBackendUnavailable("The quota service is temporarily unavailable.") from exc
        current = int(current_raw)
        allowed = bool(int(allowed_raw))
        self._record(f"{'allowed' if allowed else 'rejected'}:{action}")
        logger.info("Rate-limit decision", extra={"action": action, "allowed": allowed, "current": current, "limit": limit})
        return RateLimitResult(
            allowed=allowed,
            limit=limit,
            current=current,
            remaining=max(0, limit - current),
            reset_at=datetime.fromtimestamp(reset_epoch, tz=timezone.utc),
        )

    def acquire_concurrency_slot(self, user_id: str, resource: str, limit: int, resource_id: str) -> ConcurrencyResult:
        key = self._concurrency_key(user_id, resource)
        try:
            allowed, active, existing = self._acquire_script(
                keys=[key], args=[limit, resource_id, self.settings.concurrency_ttl_seconds],
            )
        except RedisError as exc:
            self._record(f"redis_error:concurrency:{resource}")
            logger.error("Concurrency Redis operation failed", extra={"resource": resource, "errorType": type(exc).__name__})
            raise RateLimitBackendUnavailable("The resource quota service is temporarily unavailable.") from exc
        result = ConcurrencyResult(bool(int(allowed)), limit, int(active), bool(int(existing)))
        if not result.allowed:
            self._record(f"concurrency_rejected:{resource}")
            logger.warning("Concurrency limit rejected", extra={"resource": resource, "active": result.active, "limit": limit})
        return result

    def replace_concurrency_slot(self, user_id: str, resource: str, old_id: str, new_id: str) -> int:
        try:
            return int(self._replace_script(
                keys=[self._concurrency_key(user_id, resource)],
                args=[old_id, new_id, self.settings.concurrency_ttl_seconds],
            ))
        except RedisError as exc:
            logger.error("Concurrency replacement failed", extra={"resource": resource, "errorType": type(exc).__name__})
            raise RateLimitBackendUnavailable("The resource quota service is temporarily unavailable.") from exc

    def release_concurrency_slot(self, user_id: str, resource: str, resource_id: str) -> None:
        try:
            self._release_script(keys=[self._concurrency_key(user_id, resource)], args=[resource_id])
        except RedisError as exc:
            self._record(f"release_failure:{resource}")
            logger.error("Concurrency release failed", extra={"resource": resource, "errorType": type(exc).__name__})
            raise RateLimitBackendUnavailable("The resource quota service is temporarily unavailable.") from exc

    def reconcile_concurrency(self, user_id: str, resource: str, active_resource_ids: Iterable[str]) -> int:
        resource_ids = list(dict.fromkeys(active_resource_ids))
        try:
            return int(self._reconcile_script(
                keys=[self._concurrency_key(user_id, resource)],
                args=[self.settings.concurrency_ttl_seconds, *resource_ids],
            ))
        except RedisError as exc:
            logger.error("Concurrency reconciliation failed", extra={"resource": resource, "errorType": type(exc).__name__})
            raise RateLimitBackendUnavailable("The resource quota service is temporarily unavailable.") from exc

    def clear_user(self, user_id: str) -> AdminResetResult:
        try:
            subject = self._subject(user_id)
            request_keys = list(self.redis.scan_iter(match=f"rate-limit:{subject}:*", count=100))
            concurrency_keys = [
                self._concurrency_key(user_id, "preview"),
                self._concurrency_key(user_id, "browser-session"),
            ]
            concurrency_entries = sum(int(self.redis.scard(key)) for key in concurrency_keys)
            keys = [*request_keys, *concurrency_keys]
            if keys:
                self.redis.delete(*keys)
        except RedisError as exc:
            logger.error("Administrator quota reset failed", extra={"errorType": type(exc).__name__})
            raise RateLimitBackendUnavailable("The quota service is temporarily unavailable.") from exc
        logger.info("Administrator cleared user quota state", extra={"requestKeys": len(request_keys), "concurrencyEntries": concurrency_entries})
        return AdminResetResult(len(request_keys), concurrency_entries)

    def metrics_snapshot(self) -> dict[str, int]:
        with self._metrics_lock:
            return dict(self._metrics)

    def _record(self, name: str) -> None:
        with self._metrics_lock:
            self._metrics[name] += 1

    @staticmethod
    def _subject(user_id: str) -> str:
        return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:32]

    def _concurrency_key(self, user_id: str, resource: str) -> str:
        return f"concurrency:{self._subject(user_id)}:{resource}"
