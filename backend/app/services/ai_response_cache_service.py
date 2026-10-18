import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict

from redis import Redis
from redis.exceptions import RedisError


logger = logging.getLogger(__name__)


class AIResponseCacheService:
    """Short-lived exact-prompt cache. It never blocks an AI request when Redis is unavailable."""

    def __init__(self, redis_url: str | None = None, redis_client=None) -> None:
        self.enabled = os.getenv("AI_RESPONSE_CACHE_ENABLED", "true").lower() == "true"
        self.ttl_seconds = max(60, int(os.getenv("AI_RESPONSE_CACHE_TTL_SECONDS", "21600")))
        self.max_memory_entries = max(10, int(os.getenv("AI_RESPONSE_CACHE_MEMORY_ENTRIES", "200")))
        self.redis = redis_client or Redis.from_url(
            redis_url or os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
            decode_responses=True, socket_connect_timeout=1, socket_timeout=1,
        )
        self._memory: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def key(*parts: str) -> str:
        encoded = json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return "ai-response:" + hashlib.sha256(encoded).hexdigest()

    def get(self, key: str) -> str | None:
        if not self.enabled:
            return None
        try:
            value = self.redis.get(key)
            if value is not None:
                return value
        except RedisError as exc:
            logger.warning(
                "AI response cache Redis read failed; using process cache",
                extra={"errorType": type(exc).__name__},
            )
        now = time.time()
        with self._lock:
            item = self._memory.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._memory.pop(key, None)
                return None
            self._memory.move_to_end(key)
            return value

    def set(self, key: str, value: str) -> None:
        if not self.enabled or not value:
            return
        try:
            self.redis.setex(key, self.ttl_seconds, value)
        except RedisError as exc:
            logger.warning(
                "AI response cache Redis write failed; using process cache",
                extra={"errorType": type(exc).__name__},
            )
        with self._lock:
            self._memory[key] = (time.time() + self.ttl_seconds, value)
            self._memory.move_to_end(key)
            while len(self._memory) > self.max_memory_entries:
                self._memory.popitem(last=False)
